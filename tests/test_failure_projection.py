"""
tests/test_failure_projection.py - the unified `failure` shape and the failure codes.

Covers core/failure_codes.py, core/failure_projection.py, the codes assigned where failures are
recorded (core/generation_failure.py, the workers, adapters/cv_adapter.py, tools/cv_generate.py).
The HTTP side (`failure` in the vacancy APIs) is in tests/test_web_api.py.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from adapters.cv_adapter import CVAdapter, CVAdapterError
from core import failure_codes
from core.cover_worker import CoverWorker
from core.cv_worker import CVWorker
from core.failure_projection import build_failure
from core.generation_failure import SoftFailure, exception_code, soft_failure, soft_failure_code
from core.llm_client import LLMError, LLMUnavailableError
from db import database


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test.db"
    database.configure(path)
    await database.init_db()
    return path


# ── the vocabulary ────────────────────────────────────────────────────────────

def test_normalize_keeps_known_codes_and_maps_anything_else_to_unknown():
    assert failure_codes.normalize("pdf_invalid") == "pdf_invalid"
    assert failure_codes.normalize("something_new") == failure_codes.UNKNOWN
    assert failure_codes.normalize(None) == failure_codes.UNKNOWN
    assert failure_codes.normalize(7) == failure_codes.UNKNOWN


def test_every_code_is_listed_once_and_is_a_lowercase_identifier():
    assert len(set(failure_codes.ALL_CODES)) == len(failure_codes.ALL_CODES)
    assert all(c == c.lower() and c.replace("_", "").isalpha() for c in failure_codes.ALL_CODES)


# ── the projection ────────────────────────────────────────────────────────────

def _gen(kind, target=None, code="llm_error", reason="boom", at="2026-10-09T10:00:00Z"):
    return {"kind": kind, "target": target, "reason": reason, "code": code, "at": at}


def test_fetch_failed_projects_to_a_fetch_failure():
    f = build_failure(status="fetch_failed", analysis_error="Fetch failed 5x", updated_at="2026-10-09T09:00:00Z",
                      generation_failure=None)
    assert f == {"kind": "fetch", "target": None, "reason": "Fetch failed 5x", "at": "2026-10-09T09:00:00Z",
                 "retry": "fetch", "code": "fetch_gave_up", "lang": None}


def test_analysis_failed_projects_to_an_analysis_failure():
    f = build_failure(status="analysis_failed", analysis_error="timeout", updated_at="2026-10-09T09:00:00Z",
                      generation_failure=None)
    assert (f["kind"], f["retry"], f["code"], f["reason"]) == ("analysis", "analyze", "analysis_failed", "timeout")


@pytest.mark.parametrize("kind,target,retry", [("cv", None, "cv"), ("cover", None, "cover"), ("pdf", "cover", "pdf")])
def test_a_stored_generation_failure_keeps_its_own_fields_and_names_the_retry(kind, target, retry):
    f = build_failure(status="analyzed", analysis_error=None, updated_at="x",
                      generation_failure=_gen(kind, target, code="pdf_invalid"))
    assert (f["kind"], f["target"], f["retry"], f["code"]) == (kind, target, retry, "pdf_invalid")
    assert f["at"] == "2026-10-09T10:00:00Z" and f["reason"] == "boom"


def test_a_status_based_failure_wins_over_a_stored_generation_failure():
    f = build_failure(status="analysis_failed", analysis_error="x", updated_at="u", generation_failure=_gen("cv"))
    assert f["kind"] == "analysis"


def test_no_failure_gives_none():
    assert build_failure(status="analyzed", analysis_error=None, updated_at="u", generation_failure=None) is None
    assert build_failure(status=None, analysis_error="stale text", updated_at=None, generation_failure=None) is None


@pytest.mark.parametrize("stored_code", [None, "", "a_code_from_the_future"])
def test_an_old_or_unknown_stored_code_is_shown_as_unknown(stored_code):
    f = build_failure(status="analyzed", analysis_error=None, updated_at="u",
                      generation_failure=_gen("cv", code=stored_code))
    assert f["code"] == "unknown"


def test_the_shape_has_exactly_the_agreed_keys():
    f = build_failure(status="fetch_failed", analysis_error="", updated_at=None, generation_failure=None)
    assert set(f) == {"kind", "target", "reason", "at", "retry", "code", "lang"}
    assert f["reason"] == "" and f["at"] is None


# ── the codes assigned to generation failures ─────────────────────────────────

@pytest.mark.parametrize("text,code", [
    ("Файл JD.md не найден: vacancies/x/JD.md", "jd_missing"),
    ("JD_analysis.md не найден. Сначала запусти анализ для вакансии #5.", "analysis_missing"),
    ("CV не найден в папке вакансии. Сначала сгенерируй CV для вакансии #5.", "cv_missing"),
    ("Ошибка Claude на фазе 4: rate limit", "llm_error"),
    ("Ошибка Claude на фазе 4: claude CLI timed out after 120s", "llm_timeout"),
    ("Вакансия #5 не найдена в базе.", "generation_failed"),
    ("something nobody has seen", "generation_failed"),
])
def test_the_tools_warning_texts_get_a_code(text, code):
    assert soft_failure_code(text) == code


def test_soft_failure_wraps_a_warning_text_and_ignores_success():
    failure = soft_failure("⚠️ Файл JD.md не найден:\n<code>x/JD.md</code>")
    assert isinstance(failure, SoftFailure) and failure.code == "jd_missing"
    assert str(failure) == "Файл JD.md не найден: x/JD.md"
    assert soft_failure("✅ CV готов") is None


@pytest.mark.parametrize("exc,code", [
    (LLMError("Claude API error 500"), "llm_error"),
    (LLMUnavailableError("Ollama request timed out after 600s"), "llm_timeout"),
    (TimeoutError(), "llm_timeout"),
    (asyncio.TimeoutError(), "llm_timeout"),
    (ValueError("anything else"), "generation_failed"),
    (CVAdapterError("x", code="pdf_invalid"), "pdf_invalid"),
    (CVAdapterError("x", code="not_in_the_vocabulary"), "generation_failed"),
])
def test_exceptions_get_a_code(exc, code):
    assert exception_code(exc) == code


def _worker(cls):
    return cls(deps=MagicMock(), settings=MagicMock(), llm_sem=asyncio.Semaphore(1))


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,code", [
    (LLMError("provider down"), "llm_error"),
    (LLMUnavailableError("claude CLI timed out after 120s"), "llm_timeout"),
    ("⚠️ Файл JD.md не найден:\n<code>x</code>", "jd_missing"),
])
async def test_the_workers_store_the_code_with_the_failure(db_path, outcome, code):
    cv = await database.insert_vacancy(url="https://djinni.co/jobs/fc1/", status="cv_generating")
    cover = await database.insert_vacancy(url="https://djinni.co/jobs/fc2/", status="cover_generating")
    tool = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)

    with patch("tools.cv_generate.cv_generate", tool):
        await _worker(CVWorker)._execute(cv, "auto")
    with patch("tools.cv_cover.cv_cover", tool):
        await _worker(CoverWorker)._execute(cover)

    for vid in (cv, cover):
        stored = database.decode_generation_failure((await database.get_vacancy_by_id(vid))["last_generation_failure"])
        assert stored["code"] == code


# ── the codes of PDF errors ───────────────────────────────────────────────────

def _client_ctx(response=None, exc=None):
    client = AsyncMock()
    client.post = AsyncMock(return_value=response, side_effect=exc)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _response(status=200, content=b"%PDF-1.4\n" + b"0" * 400):
    return MagicMock(status_code=status, content=content, text="body")


@pytest.mark.asyncio
@pytest.mark.parametrize("ctx,code", [
    (_client_ctx(exc=httpx.ConnectError("down")), "pdf_service_unreachable"),
    (_client_ctx(exc=httpx.ConnectTimeout("no answer")), "pdf_service_unreachable"),
    # the service is up but the exchange failed: must not say "start the service"
    (_client_ctx(exc=httpx.ReadTimeout("slow")), "pdf_service_error"),
    (_client_ctx(exc=httpx.RemoteProtocolError("cut off")), "pdf_service_error"),
    (_client_ctx(exc=httpx.HTTPError("weird")), "pdf_service_error"),
    (_client_ctx(response=_response(500)), "pdf_service_error"),
    (_client_ctx(response=_response(200, b"<html>")), "pdf_invalid"),
    (_client_ctx(response=_response(200, b"%PDF-1.4")), "pdf_invalid"),
])
async def test_the_adapter_errors_carry_a_code(tmp_path, ctx, code):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=ctx):
        with pytest.raises(CVAdapterError) as info:
            await CVAdapter("http://x").generate_pdf(md)

    assert info.value.code == code


@pytest.mark.asyncio
async def test_a_write_error_carries_its_code(tmp_path):
    md = tmp_path / "CV.md"
    md.write_text("# CV", encoding="utf-8")

    with patch("adapters.cv_adapter.httpx.AsyncClient", return_value=_client_ctx(response=_response())):
        with pytest.raises(CVAdapterError) as info:
            await CVAdapter("http://x").generate_pdf(md, tmp_path / "no_such_dir" / "CV.pdf")

    assert info.value.code == "pdf_write_failed"


# ── review follow-up: no stale failure during a run, one code in both fields, real tool texts ──

from core.failure_projection import IN_PROGRESS_STATUSES  # noqa: E402


def test_in_progress_statuses_match_the_api_active_statuses():
    from web.api import _ACTIVE_STATUSES
    assert IN_PROGRESS_STATUSES == _ACTIVE_STATUSES


@pytest.mark.parametrize("status", sorted(IN_PROGRESS_STATUSES))
def test_a_stored_failure_is_not_projected_while_a_run_is_in_progress(status):
    assert build_failure(status=status, analysis_error=None, updated_at="u", generation_failure=_gen("cv")) is None


@pytest.mark.parametrize("status", ["analyzed", "cv_generated", "cover_generated", "fetched", "declined"])
def test_a_stored_failure_is_projected_when_no_run_is_in_progress(status):
    assert build_failure(status=status, analysis_error=None, updated_at="u", generation_failure=_gen("cv"))["kind"] == "cv"


# Real tool responses, not copies of their texts: the code must follow the tools if they are reworded.

def _tool_ctx(tmp_path, llm=None):
    ctx = MagicMock()
    ctx.deps.skill_type = "pm"
    ctx.deps.user_id = 1
    ctx.deps.get_llm = AsyncMock(return_value=llm)
    ctx.deps.vacancies_path = tmp_path
    return ctx


def _tool_db(row):
    db = MagicMock()
    db.get_vacancy_by_id = AsyncMock(return_value=row)
    db.insert_pipeline_run = AsyncMock(return_value=1)
    db.update_pipeline_run = AsyncMock()
    db.update_vacancy_status = AsyncMock()
    db.insert_llm_usage = AsyncMock()
    return db


def _folder(tmp_path, *, jd=True, analysis=True, cv=True):
    d = tmp_path / "v"
    d.mkdir(exist_ok=True)
    if jd:
        (d / "JD.md").write_text("# jd", encoding="utf-8")
    if analysis:
        (d / "JD_analysis.md").write_text("analysis", encoding="utf-8")
    if cv:
        (d / "Name_CV.md").write_text("# cv", encoding="utf-8")
    return {"id": 1, "title": "PM", "markdown_path": str(d / "JD.md"), "url": "https://x/1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,missing,code", [
    ("cv_generate", {"jd": False}, "jd_missing"),
    ("cv_generate", {"analysis": False}, "analysis_missing"),
    ("cv_cover", {"jd": False}, "jd_missing"),
    ("cv_cover", {"analysis": False}, "analysis_missing"),
    ("cv_cover", {"cv": False}, "cv_missing"),
])
async def test_the_real_tool_texts_map_to_their_codes(tmp_path, tool_name, missing, code):
    import tools.cv_cover as cover_tool
    import tools.cv_generate as generate_tool
    module = generate_tool if tool_name == "cv_generate" else cover_tool
    tool = getattr(module, tool_name)
    row = _folder(tmp_path, **missing)

    with patch.object(module, "database", _tool_db(row)):
        result = await tool(_tool_ctx(tmp_path), 1)

    failure = soft_failure(result)
    assert failure is not None and failure.code == code


@pytest.mark.asyncio
async def test_the_real_cover_llm_error_text_maps_to_llm_error(tmp_path):
    import tools.cv_cover as cover_tool
    llm = MagicMock()
    llm.complete = AsyncMock(side_effect=LLMError("rate limit"))
    row = _folder(tmp_path)

    with patch.object(cover_tool, "database", _tool_db(row)):
        result = await cover_tool.cv_cover(_tool_ctx(tmp_path, llm), 1)

    failure = soft_failure(result)
    assert failure is not None and failure.code == "llm_error"
    assert "rate limit" in str(failure)


@pytest.mark.asyncio
async def test_a_missing_vacancy_row_is_a_failure_without_a_specific_code(tmp_path):
    import tools.cv_generate as generate_tool

    with patch.object(generate_tool, "database", _tool_db(None)):
        result = await generate_tool.cv_generate(_tool_ctx(tmp_path), 999)

    assert soft_failure(result).code == "generation_failed"


# ── the language of the failed CV run, so a retry repeats it ──────────────────

def test_language_codes_are_the_inverse_of_the_api_language_map():
    from core.generation_failure import LANGUAGE_CODES
    from web.api import _LANGUAGE_MAP
    assert LANGUAGE_CODES == {name: code for code, name in _LANGUAGE_MAP.items()}


@pytest.mark.asyncio
@pytest.mark.parametrize("language,lang", [("English", "en"), ("Ukrainian", "uk"), ("both", "both"), ("auto", "auto")])
async def test_the_cv_worker_stores_the_requested_language_with_the_failure(db_path, language, lang):
    vid = await database.insert_vacancy(url=f"https://djinni.co/jobs/lang-{lang}/", status="cv_generating")

    with patch("tools.cv_generate.cv_generate", AsyncMock(side_effect=LLMError("boom"))):
        await _worker(CVWorker)._execute(vid, language)

    stored = database.decode_generation_failure((await database.get_vacancy_by_id(vid))["last_generation_failure"])
    assert stored["lang"] == lang


@pytest.mark.asyncio
async def test_a_cover_failure_stores_no_language(db_path):
    vid = await database.insert_vacancy(url="https://djinni.co/jobs/lang-cover/", status="cover_generating")

    with patch("tools.cv_cover.cv_cover", AsyncMock(side_effect=LLMError("boom"))):
        await _worker(CoverWorker)._execute(vid)

    stored = database.decode_generation_failure((await database.get_vacancy_by_id(vid))["last_generation_failure"])
    assert stored["lang"] is None


def test_lang_is_projected_for_a_cv_failure_only():
    cv = build_failure(status="analyzed", analysis_error=None, updated_at="u",
                       generation_failure={**_gen("cv"), "lang": "uk"})
    cover = build_failure(status="cv_generated", analysis_error=None, updated_at="u",
                          generation_failure={**_gen("cover"), "lang": "uk"})
    pdf = build_failure(status="cv_generated", analysis_error=None, updated_at="u",
                        generation_failure={**_gen("pdf", "cv"), "lang": "uk"})
    old = build_failure(status="analyzed", analysis_error=None, updated_at="u", generation_failure=_gen("cv"))

    assert cv["lang"] == "uk"
    assert cover["lang"] is None and pdf["lang"] is None      # nothing to repeat
    assert old["lang"] is None                                # a row recorded before lang existed
