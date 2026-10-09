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
                 "retry": "fetch", "code": "fetch_gave_up"}


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
    assert set(f) == {"kind", "target", "reason", "at", "retry", "code"}
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
    (_client_ctx(exc=httpx.ReadTimeout("slow")), "pdf_service_unreachable"),
    (_client_ctx(exc=httpx.HTTPError("weird")), "pdf_service_unreachable"),
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
