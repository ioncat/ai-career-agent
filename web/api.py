"""
web/api.py — FastAPI web tracker: read-only view of vacancy pipeline state.

Standalone: uvicorn web.api:app --reload
Does not require ANTHROPIC_API_KEY or TELEGRAM_BOT_TOKEN.
"""

import json
import logging
import os
import re
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import markdown as md_lib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
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
        return out
    except Exception:
        return {}


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
        result.append(item)
    return result


@app.get("/api/users")
async def api_users():
    rows = await database.list_users()
    return [dict(row) for row in rows]


@app.get("/api/config")
async def api_config():
    """Return active LLM provider, model, and analysis mode for Flutter Settings screen (EPIC-23 T4)."""
    return {
        "llm_provider": os.getenv("LLM_PROVIDER", "claude_api").lower(),
        "model": os.getenv("LLM_MODEL", "claude-opus-4-5"),
        "analysis_mode": os.getenv("ANALYSIS_MODE", "inbox_first").lower(),
    }


def _site_from_url(url: str) -> str | None:
    netloc = urlparse(url).netloc.lower()
    if "djinni" in netloc:
        return "djinni"
    if "dou.ua" in netloc:
        return "dou"
    if "linkedin" in netloc:
        return "linkedin"
    return None


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


@app.post("/api/vacancies/{vacancy_id}/generate-cv")
async def api_vacancy_generate_cv(vacancy_id: int):
    """Flutter Generate CV button — queues vacancy for CV generation pipeline.

    Does not call LLM directly. Pipeline picks up cv_queued status.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    await database.update_vacancy_status(vacancy_id, "cv_queued")
    return {"id": vacancy_id, "status": "cv_queued"}


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

    cv_files = sorted(folder.glob("*_CV.md"))
    if cv_files:
        result["cv_md"] = cv_files[-1].read_text(encoding="utf-8")

    cover_files = sorted(folder.glob("*Cover.md"))
    if cover_files:
        result["cover_md"] = cover_files[-1].read_text(encoding="utf-8")

    return result


@app.post("/api/vacancies/{vacancy_id}/analyze", status_code=202)
async def api_vacancy_analyze(vacancy_id: int):
    """Queue vacancy for Phase 1+2 analysis (Flutter Analyze button, EPIC-22 B7).

    Sets status to analysis_queued and returns 202.
    RSSWatcher in agent.py picks up analysis_queued vacancies and runs cv_analyze.
    Status transitions: analysis_queued → analyzing → analyzed → Web Push fires.
    409 if vacancy is already queued or being analyzed.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    current_status = row["status"] if "status" in row.keys() else None
    if current_status in ("analysis_queued", "analyzing"):
        raise HTTPException(status_code=409, detail=f"Already in progress: {current_status}")
    await database.update_vacancy_status(vacancy_id, "analysis_queued")
    # Clear previous error when re-queuing
    await database.clear_analysis_error(vacancy_id)
    return {"id": vacancy_id, "status": "analysis_queued"}


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
