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


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.configure(_DB_PATH)
    await database.init_db()
    yield


app = FastAPI(title="Career Agent Tracker", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def tracker_page(
    request: Request,
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 200,
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


@app.get("/api/vacancies")
async def api_vacancies(
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 200,
):
    rows = await database.list_vacancies(status=status, user_id=user_id, limit=limit)
    return [dict(row) for row in rows]


@app.get("/api/users")
async def api_users():
    rows = await database.list_users()
    return [dict(row) for row in rows]


class NewVacancyRequest(BaseModel):
    url: str
    title: str | None = None
    feed_name: str | None = None
    user_id: int | None = None
    published_at: str | None = None


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
            user_id=req.user_id,
            status="queued",
            published_at=req.published_at,
        )
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=409, detail="duplicate")
        raise
    log.info("api/new-vacancy: queued vacancy_id=%d url=%s", vacancy_id, req.url)
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
