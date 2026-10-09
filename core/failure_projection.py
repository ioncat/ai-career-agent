"""core/failure_projection.py — one read-only `failure` shape for every failure on a vacancy.

Three sources keep a failure today, in three formats:
  - status `fetch_failed`  + `analysis_error`   (the fetch retry cap was reached),
  - status `analysis_failed` + `analysis_error` (the analysis run failed),
  - `last_generation_failure` JSON               (a CV / cover generation or a PDF render failed).

`build_failure()` projects them into one object the client renders with one widget:

    {"kind": "fetch" | "analysis" | "cv" | "cover" | "pdf",
     "target": "cv" | "cover" | None,     # only for kind "pdf": which document
     "reason": str,                       # technical detail, shown as-is
     "at": ISO 8601 UTC with Z | None,    # see below
     "retry": "fetch" | "analyze" | "cv" | "cover" | "pdf",
     "code": str,                         # core.failure_codes; the client picks its text from it
     "lang": "en" | "uk" | "both" | "auto" | None}   # kind "cv" only: the language of the failed run,
                                                      # so a retry repeats it; None otherwise and on old rows

Nothing is stored or changed: the vacancy keeps its status and its own fields, this is a
view. When a status-based failure and a stored generation failure coexist, the status wins
(the vacancy is in that state now).

A stored generation failure is NOT projected while the vacancy is in an in-progress status
(a retry or another run is under way): the old failure is superseded, and showing it would keep
a red mark and a live retry button that could queue a duplicate run. If the new run fails, a new
failure replaces the old one; if it succeeds, the failure is cleared.

`at`: a stored generation failure has its own time. The status-based failures have no stored
failure time, so `at` is the vacancy's `updated_at`, which is when the status was last written
(approximate: any later write moves it).

`retry` names the client action; the client maps it to an endpoint:
  fetch   -> PATCH /api/vacancies/{id}/restore
  analyze -> POST  /api/vacancies/{id}/analyze
  cv      -> POST  /api/vacancies/{id}/generate-cv
  cover   -> POST  /api/vacancies/{id}/generate-cover
  pdf     -> POST  /api/vacancies/{id}/render-pdf   with {"target": <target>}
"""

from __future__ import annotations

from core import failure_codes

# Statuses in which a run is queued or running. Same set as web.api._ACTIVE_STATUSES (a test keeps
# them equal).
IN_PROGRESS_STATUSES = frozenset(
    {"queued", "fetching", "analysis_queued", "analyzing", "cv_queued", "cv_generating", "cover_generating"}
)

_RETRY = {
    "fetch": "fetch",
    "analysis": "analyze",
    "cv": "cv",
    "cover": "cover",
    "pdf": "pdf",
}


def _shape(kind: str, target: str | None, reason: str, at: str | None, code: str, lang: str | None = None) -> dict:
    return {
        "kind": kind,
        "target": target,
        "reason": reason or "",
        "at": at,
        "retry": _RETRY[kind],
        "code": failure_codes.normalize(code),
        "lang": lang if kind == "cv" else None,
    }


def build_failure(
    *,
    status: str | None,
    analysis_error: str | None,
    updated_at: str | None,
    generation_failure: dict | None,
) -> dict | None:
    """The failure of this vacancy, or None when nothing is wrong.

    `generation_failure` is the decoded stored failure (database.decode_generation_failure)
    with `at` already normalised, or None.
    """
    if status == "fetch_failed":
        return _shape("fetch", None, analysis_error or "", updated_at, failure_codes.FETCH_GAVE_UP)
    if status == "analysis_failed":
        return _shape("analysis", None, analysis_error or "", updated_at, failure_codes.ANALYSIS_FAILED)
    if generation_failure and status not in IN_PROGRESS_STATUSES:
        return _shape(
            generation_failure["kind"],
            generation_failure.get("target"),
            generation_failure.get("reason") or "",
            generation_failure.get("at"),
            generation_failure.get("code") or failure_codes.UNKNOWN,
            generation_failure.get("lang"),
        )
    return None
