"""
web/api.py — FastAPI web tracker: read-only view of vacancy pipeline state.

Standalone: uvicorn web.api:app --reload
Does not require ANTHROPIC_API_KEY or TELEGRAM_BOT_TOKEN.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import os
import re
from collections import Counter
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote as _url_quote, urlparse

import httpx
import markdown as md_lib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from contracts.pipeline import AnalysisJson
from db import database
from web.reader import build_vacancy_view

log = logging.getLogger(__name__)

_DB_PATH = Path(os.getenv("DB_PATH", "db/agent.db"))
_CANDIDATE_NAME = os.getenv("CANDIDATE_NAME", "Candidate")
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _vacancies_root() -> Path:
    """Resolve the vacancies dir at call time (not import time).

    Reading VACANCIES_PATH lazily lets tests monkeypatch it to a temp dir —
    an import-time constant would already be bound to the real project folder,
    causing pytest to litter vacancies/inbox/ with throwaway user folders.
    """
    return Path(os.getenv("VACANCIES_PATH", "vacancies"))

_TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
_TEMPLATES.env.filters["markdown"] = lambda text: md_lib.markdown(
    text or "", extensions=["tables", "fenced_code"]
)


# Read at request time (not import time) so test fixtures can set env vars reliably.
def _vapid_public_key() -> str:
    return os.getenv("VAPID_PUBLIC_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.configure(_DB_PATH)
    await database.init_db()
    from core import push as _push
    _push.configure(
        private_key=os.getenv("VAPID_PRIVATE_KEY", ""),
        claims_email=os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com"),
    )
    yield


app = FastAPI(title="Career Agent Tracker", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def tracker_page(
    request: Request,
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 500,
):
    rows = await database.list_vacancies(status=status, user_id=user_id, limit=limit)
    vacancies = [build_vacancy_view(row, _CANDIDATE_NAME) for row in rows]

    # Sort: date DESC → source ASC → recommended first within source group
    def _sort_key(v):
        date_int = int(v.date.replace("-", "")) if v.date else 0
        rec_order = 0 if v.rec_class == "rec-yes" else (2 if v.rec_class == "rec-no" else 1)
        return (-date_int, (v.site or "zzz").lower(), rec_order)

    vacancies.sort(key=_sort_key)

    users = await database.list_users()
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="tracker.html",
        context={
            "vacancies": vacancies,
            "total": len(vacancies),
            "users": [dict(u) for u in users],
            "selected_user_id": user_id,
        },
    )


def _rec_label(rec: str) -> str:
    """Generate recommendation_label from recommendation value for legacy data."""
    return {"apply": "apply — strong match", "take_a_chance": "take a chance — worth trying", "decline": "decline — not worth the effort"}.get(rec, rec)


_ROLE_TAG_MAP: dict[str, str] = {
    "discovery": "#discovery",
    "strategy": "#strategy",
    "execution": "#delivery",
    "ops": "#ops",
    "coordination": "#coord",
}


def _role_tags(role_balance: dict) -> list[str]:
    """Derive 1–2 role hashtags from role_balance dict (values are percentages summing to 100).

    Takes all dimensions >= 25%. If none reach 25%, takes top-1. Capped at 2 tags.
    Rationale: <25% is background noise; >2 tags clutters the card.
    """
    if not role_balance:
        return []
    candidates = sorted(
        [(v, k) for k, v in role_balance.items() if isinstance(v, (int, float)) and v >= 25],
        reverse=True,
    )
    if not candidates:
        try:
            top = max(role_balance.items(), key=lambda kv: kv[1])
            candidates = [(top[1], top[0])]
        except ValueError:
            return []
    return [_ROLE_TAG_MAP[k] for _, k in candidates[:2] if k in _ROLE_TAG_MAP]


def _parse_quick_scan_field(markdown_path: str | None, field: str) -> str:
    """Extract **Field:** value from ## Quick Scan section of JD_analysis.md."""
    if not markdown_path:
        return ""
    analysis_file = (_PROJECT_ROOT / markdown_path).parent / "JD_analysis.md"
    if not analysis_file.exists():
        return ""
    try:
        text = analysis_file.read_text(encoding="utf-8")
        m = re.search(r"## Quick Scan\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
        if not m:
            return ""
        field_m = re.search(rf"\*\*{re.escape(field)}:\*\*\s*(.+)", m.group(1))
        return field_m.group(1).strip() if field_m else ""
    except Exception:
        return ""


def _legacy_fit_dims(raw: dict) -> dict:
    """Map old fit_dimensions keys (domain/execution/...) to new snake_case + compute overall."""
    mapping = {"domain": "domain_fit", "execution": "execution_fit", "strategy": "strategy_fit", "systems": "systems_fit", "stakeholder": "stakeholder_fit"}
    out = {v: float(raw.get(k, 0)) for k, v in mapping.items()}
    vals = list(out.values())
    out["overall_fit"] = round(sum(vals) / len(vals), 1) if vals else 0.0
    return out


def _legacy_analysis_dict(raw: dict) -> dict:
    """Convert pre-B1 analysis_json to Flutter-compatible structure."""
    result: dict = {}
    p1 = raw.get("p1")
    p2 = raw.get("p2")
    if p1:
        result["p1"] = {
            "role": "",
            "company": "",
            "north_star": "",
            "primary_archetype": p1.get("role_archetype", ""),
            "company_type": p1.get("company_type", "product"),
            "role_balance": p1.get("role_balance", {}),
            "dominant_culture": p1.get("dominant_culture", ""),
            "vacscore_dims": p1.get("vacancy_dims", {}),
            "vacancy_score": p1.get("vacancy_score", 0.0),
        }
    if p2:
        rec = p2.get("recommendation", "")
        result["p2"] = {
            "fit_score": p2.get("fit_score", 0),
            "recommendation": rec,
            "recommendation_label": p2.get("recommendation_label") or _rec_label(rec),
            "category": p2.get("category", ""),
            "who_they_want": p2.get("who_they_want", ""),
            "key_barriers": p2.get("key_barriers", []),
            "hidden_risks": p2.get("hidden_risks", []),
            "warnings": p2.get("warnings", []),
            "why_apply": p2.get("why_apply", []),
            "why_not_apply": p2.get("why_not_apply", []),
            "fit_dimensions": _legacy_fit_dims(p2.get("fit_dimensions", {})),
        }
    return result


def _parse_analysis_summary(analysis_json_str: str | None) -> dict:
    """Extract list-card fields from analysis_json for GET /api/vacancies response.

    Handles both new (B1+) and legacy (pre-B1) analysis_json formats.
    Returns partial dict — missing keys absent when phase not yet run.
    """
    if not analysis_json_str:
        return {}
    try:
        aj = AnalysisJson.model_validate_json(analysis_json_str)
        out: dict = {}
        if aj.p2:
            out["fit_score"] = aj.p2.fit_score
            out["recommendation"] = aj.p2.recommendation
            out["recommendation_label"] = aj.p2.recommendation_label
            out["key_barriers"] = aj.p2.key_barriers
            out["warnings"] = aj.p2.warnings
            out["category"] = aj.p2.category
        if aj.p1:
            out["vacancy_score"] = aj.p1.vacancy_score
            out["primary_archetype"] = aj.p1.primary_archetype
            out["role"] = aj.p1.role
            out["company"] = aj.p1.company
            out["role_tags"] = _role_tags(aj.p1.role_balance)
        return out
    except Exception:
        pass
    # Legacy pre-B1 format fallback
    try:
        raw = json.loads(analysis_json_str)
        p2 = raw.get("p2", {})
        p1 = raw.get("p1", {})
        out = {}
        if p2:
            rec = p2.get("recommendation", "")
            out["fit_score"] = p2.get("fit_score")
            out["recommendation"] = rec
            out["recommendation_label"] = _rec_label(rec)
            _kb = p2.get("key_barriers", [])
            out["key_barriers"] = _kb if isinstance(_kb, list) else ([_kb] if _kb else [])
            _w = p2.get("warnings", [])
            out["warnings"] = _w if isinstance(_w, list) else ([_w] if _w else [])
            out["category"] = p2.get("category", "")
        if p1:
            out["vacancy_score"] = p1.get("vacancy_score")
            out["primary_archetype"] = p1.get("role_archetype", "")
            out["role_tags"] = _role_tags(p1.get("role_balance", {}))
        return out
    except Exception:
        return {}


@app.get("/api/health")
async def api_health(request: Request):
    worker = getattr(request.app.state, "analysis_worker", None)
    return {"status": "ok", "worker_available": worker is not None}


@app.get("/api/vacancies")
async def api_vacancies(
    status: str | None = None,
    user_id: int | None = None,
    since: str | None = None,
    limit: int = 200,
):
    """List vacancies with parsed analysis fields for Flutter list cards.

    since: ISO 8601 datetime (e.g. 2026-06-20T12:00:00) — returns only rows
           updated after this timestamp. Used by Flutter polling (A5b).
    """
    rows = await database.list_vacancies(status=status, user_id=user_id, since=since, limit=limit)
    result = []
    for row in rows:
        item = dict(row)
        item["applied"] = bool(item.get("applied"))
        item["starred"] = bool(item.get("starred"))
        db_company = item.get("company") or ""
        parsed = _parse_analysis_summary(item.pop("analysis_json", None))
        # Prefer analysis company (post-JD parse) over RSS company, but keep RSS as fallback
        if not parsed.get("company"):
            parsed["company"] = db_company
        item.update(parsed)
        # Pass analysis_error through (None when no error)
        if 'analysis_error' not in item:
            item['analysis_error'] = None
        # folder_path: parent dir of JD.md — used by Flutter to open folder in Explorer
        md_path = item.get("markdown_path")
        item["folder_path"] = str(Path(md_path).parent) if md_path else None
        result.append(item)
    return result


@app.get("/api/users")
async def api_users():
    rows = await database.list_users()
    return [dict(row) for row in rows]


@app.get("/api/users/{user_id}/progressive_profile")
async def api_user_progressive_profile(user_id: int):
    """Return progressive_profile JSON for a user (EPIC-24 T8).

    Returns the full structured DB profile with roles[], meta.
    Empty object with roles=[] when profile not yet seeded.
    """
    row = await database.get_user_by_id(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    pp_str = row["progressive_profile"] if "progressive_profile" in row.keys() else None
    if not pp_str:
        return {"meta": {}, "roles": []}
    try:
        return json.loads(pp_str)
    except Exception:
        raise HTTPException(status_code=500, detail="Profile data corrupted")


_VALID_EFFORTS = {"off", "low", "medium", "high", "xhigh", "max"}
_VALID_PROVIDERS = {"claude_api", "ollama_api", "claude_cli"}


def _env_model_for(provider: str) -> str:
    """Default model from env for a given provider."""
    if provider == "ollama_api":
        return os.getenv("OLLAMA_MODEL", "qwen2.5:32b")
    return os.getenv("LLM_MODEL", "claude-opus-4-5")

# Fallback list used when network fetch fails
_FALLBACK_MODELS: dict[str, list[str]] = {
    "claude_api": ["claude-opus-4-5", "claude-sonnet-4-6", "claude-haiku-4-5"],
    "claude_cli": ["claude-sonnet-4-6", "claude-opus-4-5", "claude-haiku-4-5"],
}

_MODELS_CACHE_TTL_HOURS = 24


async def _fetch_anthropic_models(api_key: str) -> list[str]:
    """Fetch model IDs from Anthropic /v1/models. Returns [] on error."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if "id" in m]
            # Sort: newest first (descending by id string — works for claude-* naming)
            return sorted(models, reverse=True)
    except Exception as exc:
        log.warning("Failed to fetch Anthropic models: %s", exc)
        return []


async def _fetch_ollama_models(base_url: str) -> list[str]:
    """Fetch model tags from Ollama /api/tags. Returns [] on error."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", []) if "name" in m]
    except Exception as exc:
        log.warning("Failed to fetch Ollama models: %s", exc)
        return []


async def _get_available_models(provider: str, force: bool = False) -> list[str]:
    """Return available models for provider, using 24h DB cache.

    force=True bypasses the cache and re-fetches from the provider (manual
    "Refresh models" action — needed for local Ollama where models change often).
    """
    import datetime

    cache_key = f"models:{provider}"
    cached_value, updated_at = await database.get_kv(cache_key)

    if not force and cached_value and updated_at:
        try:
            age = datetime.datetime.utcnow() - datetime.datetime.fromisoformat(updated_at)
            if age.total_seconds() < _MODELS_CACHE_TTL_HOURS * 3600:
                return json.loads(cached_value)
        except Exception:
            pass  # bad cache entry — refetch

    # Cache miss or expired — fetch fresh
    if provider == "claude_api":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        models = await _fetch_anthropic_models(api_key) if api_key else []
        if not models:
            models = _FALLBACK_MODELS.get(provider, [])
    elif provider == "ollama_api":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        models = await _fetch_ollama_models(base_url)
    else:
        models = _FALLBACK_MODELS.get(provider, [])

    if models:
        await database.set_kv(cache_key, json.dumps(models))

    return models


@app.get("/api/config")
async def api_config():
    """Return active LLM config for Flutter Settings (EPIC-23 T4).

    env vars = global defaults; user_settings DB row for user_id=1 overrides.
    available_models fetched from Anthropic/Ollama API, cached 24h in system_kv.
    """
    db_settings = await database.get_user_settings(1)
    provider = (db_settings.get("llm_provider") or os.getenv("LLM_PROVIDER", "claude_api")).lower()
    model = db_settings.get("llm_model") or _env_model_for(provider)
    thinking_effort = db_settings.get("thinking_effort", "off") or "off"
    available_models = await _get_available_models(provider)

    return {
        "llm_provider": provider,
        "model": model,
        "thinking_effort": thinking_effort,
        "analysis_mode": os.getenv("ANALYSIS_MODE", "inbox_first").lower(),
        "available_models": available_models,
        "valid_providers": sorted(_VALID_PROVIDERS),
    }


class ConfigPatch(BaseModel):
    llm_provider: str | None = None
    model: str | None = None
    thinking_effort: str | None = None


@app.patch("/api/config")
async def patch_config(body: ConfigPatch):
    """Update LLM provider, model and/or thinking effort for user_id=1 (admin action).

    Stored in user_settings table — overrides env defaults. Workers rebuild their LLM
    from this row before each task, so a change applies to the next queued vacancy
    without a backend restart. Switching provider resets the model to the new
    provider's env default (a model of one provider is invalid for another).
    """
    db_settings = await database.get_user_settings(1)
    current_provider = (db_settings.get("llm_provider") or os.getenv("LLM_PROVIDER", "claude_api")).lower()
    current_model = db_settings.get("llm_model")
    current_effort = db_settings.get("thinking_effort", "off") or "off"

    # Provider — validate; switching it invalidates the stored model
    provider_switched = False
    new_provider = current_provider
    if body.llm_provider is not None:
        new_provider = body.llm_provider.lower()
        if new_provider not in _VALID_PROVIDERS:
            raise HTTPException(status_code=422, detail=f"llm_provider must be one of {sorted(_VALID_PROVIDERS)}")
        provider_switched = new_provider != current_provider

    new_effort = body.thinking_effort if body.thinking_effort is not None else current_effort
    if new_effort not in _VALID_EFFORTS:
        raise HTTPException(status_code=422, detail=f"thinking_effort must be one of {sorted(_VALID_EFFORTS)}")

    # Model — on provider switch, drop the stored model (falls back to new provider's default);
    # otherwise honour explicit model, validated against the (new) provider's catalog
    if provider_switched:
        new_model = None
    elif body.model is not None:
        new_model = body.model
    else:
        new_model = current_model

    allowed = await _get_available_models(new_provider)
    if new_model and allowed and new_model not in allowed:
        raise HTTPException(status_code=422, detail=f"model not valid for provider {new_provider!r}")

    # Store provider override only when it diverges from env (keeps NULL = env default)
    provider_to_store = new_provider if new_provider != os.getenv("LLM_PROVIDER", "claude_api").lower() else None
    await database.set_user_settings(
        1, llm_provider=provider_to_store, llm_model=new_model, thinking_effort=new_effort
    )

    return {
        "llm_provider": new_provider,
        "model": new_model or _env_model_for(new_provider),
        "thinking_effort": new_effort,
        "analysis_mode": os.getenv("ANALYSIS_MODE", "inbox_first").lower(),
        "available_models": allowed,
        "valid_providers": sorted(_VALID_PROVIDERS),
    }


@app.post("/api/config/refresh-models")
async def refresh_models():
    """Force-refresh the available-models list for the active provider (manual button).

    Bypasses the 24h cache and re-fetches from the provider, then persists.
    Needed for local Ollama, where models are pulled/removed between runs.
    """
    db_settings = await database.get_user_settings(1)
    provider = (db_settings.get("llm_provider") or os.getenv("LLM_PROVIDER", "claude_api")).lower()
    models = await _get_available_models(provider, force=True)
    return {"llm_provider": provider, "available_models": models}


def _site_from_url(url: str) -> str | None:
    netloc = urlparse(url).netloc.lower()
    if "djinni" in netloc:
        return "djinni"
    if "dou.ua" in netloc:
        return "dou"
    if "linkedin" in netloc:
        return "linkedin"
    return None


# Statuses where work is in flight — a re-publish must not disturb them.
_ACTIVE_STATUSES = frozenset(
    {"queued", "fetching", "analysis_queued", "analyzing", "cv_queued", "cv_generating", "cover_generating"}
)


class NewVacancyRequest(BaseModel):
    url: str
    title: str | None = None
    feed_name: str | None = None
    user_id: int | None = None
    published_at: str | None = None
    company: str | None = None
    salary: str | None = None


@app.post("/api/new-vacancy", status_code=201)
async def api_new_vacancy(req: NewVacancyRequest):
    """Webhook endpoint for job-monitor: queue a new vacancy for fetching.

    Returns 201 on success, 409 if URL already exists in DB.
    career-agent's RSSWatcher polls for status='queued' and triggers cv_fetch_jd.
    """
    existing = await database.get_vacancy_by_url(req.url)
    if existing is not None:
        # Re-publish detection: employer bumped the posting → it reappears in RSS
        # with a newer published_at. Two responses depending on prior state:
        #   declined/skipped → reopen (status→fetched, republished badge)
        #   settled (analyzed/fetched/failed/cv_*) → bump published_at so it rises
        #     in the date-sorted inbox; no status change, no badge
        #   active (analyzing/queued/generating) → leave untouched
        status = existing["status"]
        if req.published_at and req.published_at > (existing["published_at"] or ""):
            if status in ("declined", "skipped"):
                await database.on_vacancy_republished(existing["id"], req.published_at)
                log.info("api/new-vacancy: republished v#%d url=%s", existing["id"], req.url)
                return {"vacancy_id": existing["id"], "status": "republished"}
            if status not in _ACTIVE_STATUSES:
                await database.bump_published_at(existing["id"], req.published_at)
                log.info("api/new-vacancy: bumped v#%d url=%s", existing["id"], req.url)
                return {"vacancy_id": existing["id"], "status": "bumped"}
        raise HTTPException(status_code=409, detail="duplicate")
    try:
        vacancy_id = await database.insert_vacancy(
            url=req.url,
            title=req.title,
            site=_site_from_url(req.url),
            user_id=req.user_id,
            status="queued",
            published_at=req.published_at,
            company=req.company,
        )
        if req.salary:
            await database.update_vacancy_fields(vacancy_id, salary=req.salary)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=409, detail="duplicate")
        raise
    log.info("api/new-vacancy: queued vacancy_id=%d url=%s company=%s", vacancy_id, req.url, req.company)
    return {"vacancy_id": vacancy_id, "status": "queued"}


_MAX_IMPORT_BYTES = 200_000
_SAFE_NAME_RE = re.compile(r'[<>:"/\\|?*]')

_SITE_PATTERNS: list[tuple[str, str]] = [
    ("djinni.co", "djinni"),
    ("jobs.dou.ua", "dou"),
    ("dou.ua", "dou"),
    ("work.ua", "work"),
    ("linkedin.com", "linkedin"),
    ("hh.ua", "hh"),
    ("hh.ru", "hh"),
    ("rabota.ua", "rabota"),
    ("jobs.ua", "jobs"),
    ("grc.ua", "grc"),
    ("nofluffjobs.com", "nofluffjobs"),
    ("robota.ua", "robota"),
]

def _detect_site(content: str) -> str:
    """Extract first http(s) URL from content and map hostname to a site slug."""
    for match in re.finditer(r'https?://[^\s<>"\'()]+', content):
        host = urlparse(match.group()).hostname or ""
        for pattern, slug in _SITE_PATTERNS:
            if pattern in host:
                return slug
    return "manual"


def _extract_title_and_company(content: str, site: str) -> tuple[str, str]:
    """Parse JD content → (clean_role_title, company). Both may be empty string."""
    h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    h1 = h1_match.group(1).strip() if h1_match else ""

    if site == "work":
        # work.ua format: "Вакансія {role}, {location}, компанія {company}"
        m = re.match(r'(?:Вакансія\s+)?(.+?),.*?компані[яї]\s+(.+)', h1, re.IGNORECASE)
        if m:
            return m.group(1).strip(), m.group(2).strip()

    # Generic: "компанія/компания X" anywhere in H1
    if h1:
        m = re.search(r'компані[яї]\s+([^\n,]+)', h1, re.IGNORECASE)
        if m:
            company = m.group(1).strip()
            role = re.sub(r',?\s*компані[яї]\s+.+', '', h1, flags=re.IGNORECASE).strip()
            role = re.sub(r'^(?:Вакансія|Вакансия)\s+', '', role, flags=re.IGNORECASE).strip()
            return role, company
        # No company in H1 — strip "Вакансія" prefix and return clean title
        role = re.sub(r'^(?:Вакансія|Вакансия)\s+', '', h1, flags=re.IGNORECASE).strip()
        return role, ""

    return "", ""


class ImportJdRequest(BaseModel):
    content: str
    filename: str
    user_id: int = 1


@app.post("/api/vacancies/import-jd", status_code=201)
async def api_import_jd(req: ImportJdRequest):
    """Import a JD from uploaded file content (no URL required).

    Returns 201 {vacancy_id, title} on success.
    Returns 409 if content already exists (content_hash collision).
    Returns 413 if file exceeds 200 KB.
    Returns 422 if content is empty.
    """
    stripped = req.content.strip()
    if not stripped:
        raise HTTPException(status_code=422, detail="content is empty")
    if len(req.content.encode()) > _MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 200 KB)")

    norm = re.sub(r"\s+", " ", req.content.lower())
    content_hash = hashlib.sha256(norm.encode()).hexdigest()

    dup_id = await database.find_duplicate(req.user_id, content_hash, None, None)
    if dup_id is not None:
        raise HTTPException(status_code=409, detail=f"duplicate of #{dup_id}")

    # Filename → fallback title (stripped extension + sanitized)
    fallback_title = req.filename
    for ext in (".md", ".txt"):
        if fallback_title.lower().endswith(ext):
            fallback_title = fallback_title[: -len(ext)]
    fallback_title = _SAFE_NAME_RE.sub("", fallback_title).strip(". ").strip() or "Vacancy"

    detected_site = _detect_site(req.content)
    extracted_title, extracted_company = _extract_title_and_company(req.content, detected_site)
    title = extracted_title or fallback_title

    url = f"import://{content_hash}"
    try:
        vacancy_id = await database.insert_vacancy(
            url=url,
            title=title,
            site=detected_site,
            user_id=req.user_id,
            status="fetched",
            published_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            company=extracted_company or None,
        )
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=409, detail="duplicate")
        raise

    await database.set_content_hash(vacancy_id, content_hash)

    safe_folder = _SAFE_NAME_RE.sub("", f"{vacancy_id} — {title}").strip(". ")[:80]
    vacancy_dir = _vacancies_root() / "inbox" / str(req.user_id) / safe_folder
    try:
        vacancy_dir.mkdir(parents=True, exist_ok=True)
        jd_path = vacancy_dir / "JD.md"
        jd_path.write_text(f"# {title}\n\n---\n\n{req.content}", encoding="utf-8")
    except OSError as exc:
        log.error("import-jd: failed to write JD.md: %s", exc)
        raise HTTPException(status_code=500, detail="failed to write file")

    await database.update_vacancy_fields(vacancy_id, markdown_path=str(jd_path))
    log.info("api/import-jd: vacancy_id=%d title=%r user=%d", vacancy_id, title, req.user_id)
    return {"vacancy_id": vacancy_id, "title": title}


_BARRIER_FILE_RE = re.compile(r"\*\*Key Barriers:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)


@app.get("/stats/barriers", response_class=HTMLResponse)
async def stats_barriers(request: Request):
    """Aggregate Key Barriers frequency across all analyzed vacancies.

    Primary source: analysis_json DB column (p2.key_barriers).
    Fallback: file-parse JD_analysis.md for vacancies without DB JSON.
    """
    rows = await database.list_vacancies(limit=500)
    counter: Counter = Counter()
    total_with_data = 0

    def _add_barriers(raw_items) -> bool:
        """Add barriers from list or semicolon string. Returns True if any added."""
        items: list[str] = []
        if isinstance(raw_items, list):
            items = [str(b).strip() for b in raw_items if b]
        elif isinstance(raw_items, str):
            if raw_items.lower() in ("нет", "none", "—", "-", ""):
                return False
            items = [i.strip().rstrip(".") for i in raw_items.split(";")] if ";" in raw_items \
                else [i.strip().rstrip(".") for i in re.split(r"\.\s+", raw_items)]
        added = False
        for item in items:
            if item and len(item) > 3 and item.lower() not in ("нет", "none", "—", "-"):
                counter[item] += 1
                added = True
        return added

    for row in rows:
        # Primary: DB analysis_json
        aj_str = row["analysis_json"] if "analysis_json" in row.keys() else None
        if aj_str:
            try:
                aj = json.loads(aj_str)
                kb = aj.get("p2", {}).get("key_barriers")
                if kb and _add_barriers(kb):
                    total_with_data += 1
                    continue
            except Exception:
                pass

        # Fallback: file parse
        path = row["markdown_path"]
        if not path:
            continue
        analysis = Path(path).parent / "JD_analysis.md"
        if not analysis.exists():
            continue
        try:
            text = analysis.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _BARRIER_FILE_RE.search(text)
        if not m:
            continue
        raw = m.group(1).strip()
        if _add_barriers(raw):
            total_with_data += 1

    rows_html = "".join(
        f"<tr><td style='color:#9ca3af;font-size:11px'>{i + 1}</td>"
        f"<td><span style='display:inline-block;padding:2px 8px;border-radius:8px;"
        f"background:#ede9fe;color:#5b21b6;border:1px solid #c4b5fd;font-size:12px'>{item}</span></td>"
        f"<td style='font-weight:600;color:#1d4ed8'>{count}</td></tr>"
        for i, (item, count) in enumerate(counter.most_common())
    ) or "<tr><td colspan='3' style='color:#9ca3af'>Нет данных — нужны проанализированные вакансии</td></tr>"

    html = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<title>Key Barriers — Stats</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:13px;background:#f4f4f5;padding:24px}}
.wrap{{max-width:700px;margin:0 auto}}h1{{font-size:16px;font-weight:600;margin-bottom:6px}}
.sub{{color:#6b7280;font-size:12px;margin-bottom:18px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:7px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
th{{background:#18181b;color:#fff;padding:8px 12px;text-align:left;font-size:12px;font-weight:500}}
td{{padding:7px 12px;border-bottom:1px solid #f0f0f0}}tr:last-child td{{border-bottom:none}}
.back{{margin-top:16px;font-size:12px}}.back a{{color:#1d4ed8;text-decoration:none}}</style>
</head><body><div class="wrap">
<h1>Key Barriers — Market Stats</h1>
<p class="sub">Проанализировано вакансий: {total_analyzed} · Уникальных барьеров: {len(counter)}</p>
<table><thead><tr><th>#</th><th>Барьер / Gap</th><th>Вакансий</th></tr></thead>
<tbody>{rows_html}</tbody></table>
<p class="back"><a href="/">← Трекер</a></p>
</div></body></html>"""
    return HTMLResponse(html)


@app.get("/files/{filepath:path}")
async def serve_file(filepath: str):
    """Serve files from project root (vacancies/, etc.). Used for PDF links in tracker."""
    full_path = (_PROJECT_ROOT / filepath).resolve()
    # Path traversal guard
    if not str(full_path).startswith(str(_PROJECT_ROOT)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


# ── Web Push endpoints ────────────────────────────────────────────────────────

class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_id: int = 1


@app.post("/api/push/subscribe", status_code=201)
async def api_push_subscribe(req: PushSubscribeRequest, request: Request):
    """Register or refresh a Web Push subscription.

    Called by browser after PushManager.subscribe(). The subscription object
    contains endpoint URL + ECDH keys (p256dh, auth) for encrypted delivery.
    On re-subscribe (same endpoint, rotated keys): updates keys in DB.
    """
    await database.upsert_push_subscription(
        user_id=req.user_id,
        endpoint=req.endpoint,
        p256dh=req.p256dh,
        auth=req.auth,
        user_agent=request.headers.get("user-agent"),
    )
    log.info("push/subscribe: user_id=%d endpoint=%.40s", req.user_id, req.endpoint)
    return {"status": "subscribed"}


@app.delete("/api/push/subscribe", status_code=200)
async def api_push_unsubscribe(endpoint: str):
    """Remove a push subscription. Called on browser unsubscribe."""
    await database.delete_push_subscription(endpoint)
    return {"status": "unsubscribed"}


@app.get("/api/push/vapid-public-key")
async def api_vapid_public_key():
    """Return VAPID public key for browser PushManager.subscribe() applicationServerKey."""
    key = _vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Web Push not configured — set VAPID_PUBLIC_KEY")
    return {"publicKey": key}


@app.patch("/api/vacancies/{vacancy_id}/decline")
async def api_vacancy_decline(vacancy_id: int):
    """Flutter Decline button — moves vacancy to archive folder."""
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    await database.update_vacancy_status(vacancy_id, "declined")
    return {"id": vacancy_id, "status": "declined"}


@app.patch("/api/vacancies/{vacancy_id}/restore")
async def api_vacancy_restore(vacancy_id: int):
    """Flutter Restore button — moves declined vacancy back to inbox.

    Restores to 'analyzed' if analysis_json exists, otherwise 'fetched'.
    Preserves all analysis data — only status changes.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    restore_status = "analyzed" if row["analysis_json"] else "fetched"
    await database.update_vacancy_status(vacancy_id, restore_status)
    return {"id": vacancy_id, "status": restore_status}


_LANGUAGE_MAP = {"en": "English", "uk": "Ukrainian", "both": "both", "auto": "auto"}

@app.post("/api/vacancies/{vacancy_id}/generate-cv")
async def api_vacancy_generate_cv(vacancy_id: int, request: Request):
    """Start Phase 3+3.5 CV generation immediately (Flutter Generate CV button).

    Accepts optional JSON body: {"language": "en"|"uk"|"both"} (default: "en").
    Enqueues into CVWorker — processing starts without polling delay.
    Status transitions: cv_generating → cv_generated.
    Falls back to DB-only status when running without agent.py (standalone tracker).
    """
    body = {}
    with contextlib.suppress(Exception):
        body = await request.json()
    lang_code = body.get("language", "en")
    language = _LANGUAGE_MAP.get(lang_code, "English")

    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    current_status = row["status"] if "status" in row.keys() else None
    if current_status == "cv_generating":
        raise HTTPException(status_code=409, detail="CV generation already in progress")
    worker = getattr(request.app.state, "cv_worker", None)
    if worker is not None:
        await worker.enqueue(vacancy_id, language)
        return {"id": vacancy_id, "status": "cv_generating", "language": language}
    # Standalone fallback
    await database.update_vacancy_status(vacancy_id, "cv_queued")
    return {"id": vacancy_id, "status": "cv_queued"}


@app.post("/api/vacancies/{vacancy_id}/generate-cover")
async def api_vacancy_generate_cover(vacancy_id: int, request: Request):
    """Start Phase 4 cover letter generation immediately (Flutter Generate Cover button).

    Enqueues into CoverWorker — requires CV to already exist (status cv_generated or cover_generated).
    Status transitions: cover_generating → cover_generated.
    Falls back to DB-only status when running without agent.py (standalone tracker).
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    current_status = row["status"] if "status" in row.keys() else None
    if current_status == "cover_generating":
        raise HTTPException(status_code=409, detail="Cover generation already in progress")
    worker = getattr(request.app.state, "cover_worker", None)
    if worker is not None:
        await worker.enqueue(vacancy_id)
        return {"id": vacancy_id, "status": "cover_generating"}
    await database.update_vacancy_status(vacancy_id, "cover_generating")
    return {"id": vacancy_id, "status": "cover_generating"}


@app.get("/api/vacancies/{vacancy_id}/analysis")
async def api_vacancy_analysis(vacancy_id: int):
    """Return full AnalysisJson for a vacancy (Flutter detail screen).

    Parses vacancies.analysis_json into structured Pydantic model.
    Returns empty object {} when analysis not yet run (phase keys absent).
    404 when vacancy_id not found.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    aj_str = row["analysis_json"] if "analysis_json" in row.keys() else None
    md_path = row["markdown_path"] if "markdown_path" in row.keys() else None
    try:
        aj = AnalysisJson.model_validate_json(aj_str or "{}")
        result = aj.model_dump(exclude_none=True)
    except Exception:
        # Legacy pre-B1 format fallback
        try:
            result = _legacy_analysis_dict(json.loads(aj_str)) if aj_str else {}
        except Exception:
            result = {}
    # Populate who_they_want from Quick Scan markdown when JSON field absent
    p2 = result.get("p2")
    if p2 is not None and not p2.get("who_they_want"):
        who = _parse_quick_scan_field(md_path, "Who they want")
        if who:
            p2["who_they_want"] = who
    return result


@app.get("/api/vacancies/{vacancy_id}/cv")
async def api_vacancy_cv(vacancy_id: int):
    """Return CV and cover markdown for a vacancy (Flutter CV preview + PDF download trigger).

    Searches vacancy folder for *_CV.md and Cover.md files.
    markdown_path column points to JD.md; CV/Cover files are siblings in the same folder.
    Returns {"cv_md": "...", "cover_md": "..."} — missing keys absent if not yet generated.
    404 when vacancy_id not found.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    md_path = row["markdown_path"] if "markdown_path" in row.keys() else None
    if not md_path:
        return {}

    folder = (_PROJECT_ROOT / md_path).parent
    if not folder.exists():
        return {}

    result: dict = {}

    cv_files = sorted(folder.glob("*_CV*.md"))
    if cv_files:
        result["cv_md"] = cv_files[-1].read_text(encoding="utf-8")

    cover_files = sorted(folder.glob("*Cover*.md"))
    if cover_files:
        result["cover_md"] = cover_files[-1].read_text(encoding="utf-8")

    return result


async def _render_doc_pdf(vacancy_id: int, glob_pattern: str, not_found_msg: str) -> Response:
    """Shared helper: find a markdown doc in the vacancy folder, render via pdf-service, return bytes."""
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    md_path = row["markdown_path"] if "markdown_path" in row.keys() else None
    if not md_path:
        raise HTTPException(status_code=404, detail=not_found_msg)

    folder = (_PROJECT_ROOT / md_path).parent
    files = sorted(folder.glob(glob_pattern))
    if not files:
        raise HTTPException(status_code=404, detail=not_found_msg)

    md_file = files[-1]
    markdown_text = md_file.read_text(encoding="utf-8")
    pdf_name = md_file.stem + ".pdf"

    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://localhost:8002")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{pdf_service_url}/render", json={"markdown": markdown_text})
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(status_code=503, detail=f"pdf-service unavailable: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"pdf-service error {resp.status_code}")

    pdf_name_encoded = _url_quote(pdf_name.encode("utf-8"), safe="")
    return Response(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{pdf_name_encoded}"},
    )


@app.get("/api/vacancies/{vacancy_id}/cv-pdf")
async def api_vacancy_cv_pdf(vacancy_id: int):
    """Render CV.md to PDF via pdf-service and return for Save As download.

    Always re-renders from latest *_CV.md so PDF is always fresh.
    503 if pdf-service is down. 404 if CV not yet generated.
    """
    return await _render_doc_pdf(vacancy_id, "*_CV*.md", "CV not yet generated")


@app.get("/api/vacancies/{vacancy_id}/cover-pdf")
async def api_vacancy_cover_pdf(vacancy_id: int):
    """Render Cover.md to PDF via pdf-service and return for Save As download.

    Always re-renders from latest *Cover.md so PDF is always fresh.
    503 if pdf-service is down. 404 if Cover not yet generated.
    """
    return await _render_doc_pdf(vacancy_id, "*Cover.md", "Cover not yet generated")


@app.post("/api/vacancies/{vacancy_id}/analyze", status_code=202)
async def api_vacancy_analyze(vacancy_id: int, request: Request):
    """Start Phase 1+2 analysis immediately (Flutter Analyze button).

    Enqueues into AnalysisWorker — processing starts without polling delay.
    Status transitions: analyzing → analyzed → Web Push fires.
    409 if vacancy is already being analyzed.
    Falls back to DB-only status when running without agent.py (standalone tracker).
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    current_status = row["status"] if "status" in row.keys() else None
    if current_status == "analyzing":
        raise HTTPException(status_code=409, detail="Already analyzing")
    await database.clear_analysis_error(vacancy_id)
    worker = getattr(request.app.state, "analysis_worker", None)
    if worker is not None:
        await worker.enqueue(vacancy_id)
        return {"id": vacancy_id, "status": "analyzing"}
    # Standalone fallback (no agent.py running)
    await database.update_vacancy_status(vacancy_id, "analysis_queued")
    return {"id": vacancy_id, "status": "analysis_queued"}


@app.post("/api/vacancies/{vacancy_id}/reset", status_code=200)
async def api_vacancy_reset(vacancy_id: int):
    """Reset a stuck vacancy back to 'fetched' so the user can re-analyze.

    Allowed for: analyzing, analysis_queued, analysis_failed.
    Clears any stored error. 400 if status is not resettable.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    current_status = row["status"] if "status" in row.keys() else None
    resettable = {"analyzing", "analysis_queued", "analysis_failed"}
    if current_status not in resettable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reset vacancy in status '{current_status}'",
        )
    await database.clear_analysis_error(vacancy_id)
    await database.update_vacancy_status(vacancy_id, "fetched")
    return {"id": vacancy_id, "status": "fetched"}


@app.get("/api/vacancies/{vacancy_id}/jd")
async def api_vacancy_jd(vacancy_id: int):
    """Return JD markdown for a vacancy (Flutter detail screen — inbox-first JD view, EPIC-22 B6).

    404 when vacancy not found or JD file missing on disk.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    md_path = row["markdown_path"] if "markdown_path" in row.keys() else None
    if not md_path:
        raise HTTPException(status_code=404, detail="JD not found")

    jd_file = Path(md_path) if Path(md_path).is_absolute() else _PROJECT_ROOT / md_path
    if not jd_file.exists():
        raise HTTPException(status_code=404, detail="JD not found")

    return {"jd_md": jd_file.read_text(encoding="utf-8")}


@app.get("/api/vacancies/{vacancy_id}")
async def api_vacancy(vacancy_id: int):
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    return dict(row)


@app.get("/api/vacancies/{vacancy_id}/activity")
async def api_vacancy_activity(vacancy_id: int):
    """Return full activity log for a vacancy: pipeline_runs + llm_usage.

    Used by Flutter Activity tab to show both phase execution status
    (pipeline_runs) and LLM call details (llm_usage) in one request.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    runs, entries = await asyncio.gather(
        database.get_vacancy_pipeline_runs(vacancy_id),
        database.get_vacancy_activity(vacancy_id),
    )
    return {"vacancy_id": vacancy_id, "pipeline_runs": runs, "entries": entries}


class AppliedUpdate(BaseModel):
    applied: bool


@app.patch("/api/vacancies/{vacancy_id}/applied")
async def api_set_applied(vacancy_id: int, req: AppliedUpdate):
    """Toggle applied flag for a vacancy. applied=true → CV submitted."""
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    await database.set_vacancy_applied(vacancy_id, req.applied)
    return {"vacancy_id": vacancy_id, "applied": req.applied}


class StarredUpdate(BaseModel):
    starred: bool


@app.patch("/api/vacancies/{vacancy_id}/starred")
async def api_set_starred(vacancy_id: int, req: StarredUpdate):
    """Toggle starred/favourite flag for a vacancy."""
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    await database.set_vacancy_starred(vacancy_id, req.starred)
    return {"vacancy_id": vacancy_id, "starred": req.starred}


class SalaryUpdate(BaseModel):
    salary: str  # free-form text, e.g. "$4500" or "3000–4500 USD"; empty string clears


@app.patch("/api/vacancies/{vacancy_id}/salary")
async def api_set_salary(vacancy_id: int, req: SalaryUpdate):
    """Set user-entered salary for a vacancy. Empty string clears the field."""
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    await database.set_vacancy_salary(vacancy_id, req.salary)
    return {"vacancy_id": vacancy_id, "salary": req.salary}


# ── Notifications (EPIC-21 C5) ────────────────────────────────────────────────

@app.get("/api/notifications")
async def api_notifications(
    user_id: int = 1,
    since: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
):
    """Return pipeline event notifications for a user.

    Used by Flutter NotificationProvider (polls every 30s).
    Params:
      user_id: user to fetch notifications for (default 1).
      since: ISO 8601 datetime — return only notifications created after this.
      unread_only: if true, return only unread notifications.
      limit: max rows (default 50, max 200).
    """
    limit = min(limit, 200)
    rows = await database.list_notifications(
        user_id=user_id, since=since, unread_only=unread_only, limit=limit
    )
    return rows


@app.post("/api/notifications/{notification_id}/read", status_code=200)
async def api_mark_notification_read(notification_id: int):
    """Mark a single notification as read."""
    await database.mark_notification_read(notification_id)
    return {"id": notification_id, "read": True}


@app.post("/api/notifications/read-all", status_code=200)
async def api_mark_all_notifications_read(user_id: int = 1):
    """Mark all unread notifications for a user as read."""
    await database.mark_all_notifications_read(user_id)
    return {"ok": True}
