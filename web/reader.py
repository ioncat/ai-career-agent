"""
web/reader.py — Read JD_analysis.md and build VacancyView for the web tracker.

Parses Quick Scan fields (fit score, recommendation, category, warnings, blockers)
from JD_analysis.md via regex. Full markdown passed to template for client-side
rendering via marked.js.

All parsing is best-effort: missing fields return empty strings, never raises.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Regexes for Quick Scan fields ────────────────────────────────────────────
_FIT_RE   = re.compile(r"\*\*Fit score:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_REC_RE   = re.compile(r"\*\*Recommendation:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_CAT_RE   = re.compile(r"\*\*Category:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_WARN_RE  = re.compile(r"\*\*Warnings:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
_BLOCK_RE = re.compile(r"\*\*Key Barriers:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)

# Statuses that imply the given artifact exists
_STATUS_ORDER = ["fetched", "analyzed", "cv_generated", "cover_generated"]


def _status_gte(status: str, threshold: str) -> bool:
    """Return True if status is at or after threshold in pipeline order."""
    try:
        return _STATUS_ORDER.index(status) >= _STATUS_ORDER.index(threshold)
    except ValueError:
        return False


@dataclass
class VacancyView:
    """All display data for one vacancy row in the web tracker."""
    id: int
    title: str
    url: str
    site: str
    status: str
    date: str               # "YYYY-MM-DD" from created_at
    fit_score: str          # "8/10" or "—"
    recommendation: str     # "подавать" / "не подавать" / ""
    category: str           # "AI Product · Remote" or ""
    warnings: str           # raw semicolon-separated warnings
    blockers: str           # raw blockers text
    has_analysis: bool
    has_cv: bool
    has_cover: bool
    has_pdf: bool
    cv_pdf_url: str = ""    # "/files/vacancies/..." — empty string if no PDF
    analysis_md: str = ""   # full JD_analysis.md content for marked.js rendering
    salary: str = ""         # "$4500" or "" if unknown
    applied: bool = False   # True if CV was submitted to this vacancy
    starred: bool = False   # True if marked as favourite
    vacancy_score: str = "—"  # "7.2" or "—" — attractiveness score from p1

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def rec_class(self) -> str:
        """CSS class for row left-border colour.

        Canonical values: apply → rec-yes, decline → rec-no, take a chance → rec-consider.
        Also handles legacy Russian/Ukrainian values for backward compatibility.
        """
        rec = self.recommendation.lower().strip()
        # Negative — decline
        if rec == "decline" or "не подавать" in rec or "не підавати" in rec or "not apply" in rec:
            return "rec-no"
        # Consider — take a chance (must check before generic "подавать" which is a substring)
        if rec == "take a chance" or "рассмотреть" in rec or "розглянути" in rec:
            return "rec-consider"
        # Positive — apply
        if rec == "apply" or "подавать" in rec or "підавати" in rec:
            return "rec-yes"
        return ""

    @property
    def barriers_list(self) -> list[str]:
        """Split Key Barriers text into individual chip items.

        Supports two formats:
        - New (semicolon): "A/B testing; consumer product; PSP/POS"
        - Legacy (sentences): "No A/B testing. No consumer product."
        """
        raw = (self.blockers or "").strip()
        if not raw or raw.lower() in ("нет", "none", "—", "-"):
            return []
        if ";" in raw:
            items = [i.strip().rstrip(".") for i in raw.split(";")]
        else:
            items = re.split(r"\.\s+", raw)
            items = [i.strip().rstrip(".") for i in items]
        return [i for i in items if i and len(i) > 3 and i.lower() not in ("нет", "none", "—", "-")]

    @property
    def warn_count(self) -> int:
        """Number of distinct warnings (split by ';')."""
        if not self.warnings or self.warnings.strip() in ("нет", "none", "—", "-"):
            return 0
        return len([w for w in self.warnings.split(";") if w.strip()])

    @property
    def warn_text_escaped(self) -> str:
        """Warnings with single quotes escaped for inline onclick='showWarn(...)'."""
        return self.warnings.replace("'", "\\'").replace('"', "&quot;")

    @property
    def site_display(self) -> str:
        """Human-readable source label for display in tracker."""
        _LABELS = {"djinni": "Djinni", "dou": "DOU", "linkedin": "LinkedIn"}
        s = (self.site or "").lower()
        return _LABELS.get(s, self.site.capitalize() if self.site else "Other")


def build_vacancy_view(row: object, candidate_name: str = "Candidate") -> VacancyView:
    """Build VacancyView from a DB row (aiosqlite.Row or dict-like).

    Reads JD_analysis.md from disk if available. All errors are silently ignored.
    """
    vacancy_id: int = row["id"]  # type: ignore[index]
    title: str      = row["title"] or "Без названия"  # type: ignore[index]
    url: str        = row["url"] or ""  # type: ignore[index]
    site: str       = row["site"] or "?"  # type: ignore[index]
    status: str     = row["status"] or "fetched"  # type: ignore[index]
    created_at: str = row["created_at"] or ""  # type: ignore[index]
    markdown_path: str | None = row["markdown_path"]  # type: ignore[index]
    db_warnings: str = row["warnings"] if "warnings" in row.keys() else ""  # type: ignore[index]
    db_salary: str = row["salary"] if "salary" in row.keys() and row["salary"] else ""  # type: ignore[index]
    db_analysis_json: str | None = row["analysis_json"] if "analysis_json" in row.keys() else None  # type: ignore[index]
    db_applied: bool = bool(row["applied"]) if "applied" in row.keys() else False  # type: ignore[index]
    db_starred: bool = bool(row["starred"]) if "starred" in row.keys() else False  # type: ignore[index]

    date = created_at[:10]  # "YYYY-MM-DD"

    # ── Artifact paths ────────────────────────────────────────────────────────
    folder = Path(markdown_path).parent if markdown_path else None
    analysis_path = folder / "JD_analysis.md" if folder else None

    # Scan folder for CV/cover/PDF files — do NOT rely on candidate_name/env var.
    # Matches any file ending in _CV.md, _CV.pdf, _Cover.md regardless of name prefix.
    cv_md_files  = list(folder.glob("*_CV.md"))  if folder and folder.exists() else []
    cv_pdf_files = list(folder.glob("*_CV.pdf")) if folder and folder.exists() else []
    cover_files  = list(folder.glob("*_Cover.md")) if folder and folder.exists() else []

    cv_pdf_path = cv_pdf_files[0] if cv_pdf_files else None

    has_analysis = bool(analysis_path and analysis_path.exists())
    has_cv       = bool(cv_md_files)
    has_cover    = bool(cover_files)
    has_pdf      = bool(cv_pdf_files)
    cv_pdf_url   = ("/files/" + str(cv_pdf_path).replace("\\", "/")) if cv_pdf_path else ""

    # ── Parse analysis fields ─────────────────────────────────────────────────
    analysis_md = ""
    fit_score = "—"
    recommendation = ""
    category = ""
    warnings = ""
    blockers = ""

    if has_analysis and analysis_path:
        try:
            analysis_md = analysis_path.read_text(encoding="utf-8")
            fit_score    = _extract(analysis_md, _FIT_RE) or "—"
            recommendation = _extract(analysis_md, _REC_RE)
            category     = _extract(analysis_md, _CAT_RE)
            warnings     = _extract(analysis_md, _WARN_RE)
            blockers     = _extract(analysis_md, _BLOCK_RE)
        except OSError:
            pass

    # Fallback: use DB warnings if JD_analysis.md didn't have the field
    if not warnings and db_warnings:
        warnings = db_warnings

    # Primary source for blockers: analysis_json DB column (p2.key_barriers)
    # Overrides file-parsed blockers when DB data is available
    vacancy_score_str = "—"
    if db_analysis_json:
        try:
            aj = json.loads(db_analysis_json)
            p2 = aj.get("p2", {})
            kb = p2.get("key_barriers", [])
            if kb:
                if isinstance(kb, list):
                    blockers = "; ".join(str(b) for b in kb if b)
                elif isinstance(kb, str):
                    blockers = kb
            if not db_salary and p2.get("salary"):
                db_salary = p2["salary"]
            p1 = aj.get("p1", {})
            vs = p1.get("vacancy_score")
            if vs is not None:
                vacancy_score_str = str(vs)
        except Exception:
            pass  # keep file-parsed values

    return VacancyView(
        id=vacancy_id,
        title=title,
        url=url,
        site=site,
        status=status,
        date=date,
        fit_score=fit_score,
        recommendation=recommendation,
        category=category,
        warnings=warnings,
        blockers=blockers,
        has_analysis=has_analysis,
        has_cv=has_cv,
        has_cover=has_cover,
        has_pdf=has_pdf,
        cv_pdf_url=cv_pdf_url,
        analysis_md=analysis_md,
        salary=db_salary,
        applied=db_applied,
        starred=db_starred,
        vacancy_score=vacancy_score_str,
    )


def _extract(text: str, pattern: re.Pattern) -> str:
    """Return first capture group stripped, or empty string."""
    m = pattern.search(text)
    return m.group(1).strip() if m else ""
