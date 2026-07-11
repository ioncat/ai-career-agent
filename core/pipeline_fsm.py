"""core/pipeline_fsm.py — Vacancy pipeline state machine.

VacancyState enum + VALID_TRANSITIONS + fsm_transition().
Pure validation layer: does not orchestrate, schedule, or notify.
Callers (pipeline_runner, workers, API) set the target state;
this module validates the edge and writes to DB.
"""

from __future__ import annotations

from enum import StrEnum

from db import database


# ── States ────────────────────────────────────────────────────────────────────


class VacancyState(StrEnum):
    QUEUED           = "queued"
    FETCHING         = "fetching"
    FETCHED          = "fetched"
    ANALYSIS_QUEUED  = "analysis_queued"
    ANALYZING        = "analyzing"
    ANALYZED         = "analyzed"
    ANALYSIS_FAILED  = "analysis_failed"
    CV_QUEUED        = "cv_queued"
    CV_GENERATING    = "cv_generating"
    CV_GENERATED     = "cv_generated"
    COVER_GENERATING = "cover_generating"
    COVER_GENERATED  = "cover_generated"
    DECLINED         = "declined"
    SKIPPED          = "skipped"        # legacy alias for declined
    DONE             = "done"           # legacy terminal
    ERROR            = "error"          # legacy terminal


# ── Valid transitions ─────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[VacancyState, frozenset[VacancyState]] = {
    VacancyState.QUEUED: frozenset({
        VacancyState.FETCHING,
        VacancyState.DECLINED,
    }),
    VacancyState.FETCHING: frozenset({
        VacancyState.FETCHED,
        VacancyState.QUEUED,           # reset on fetch failure → auto-retry
    }),
    VacancyState.FETCHED: frozenset({
        VacancyState.ANALYSIS_QUEUED,
        VacancyState.DECLINED,
    }),
    VacancyState.ANALYSIS_QUEUED: frozenset({
        VacancyState.ANALYZING,
        VacancyState.DECLINED,
    }),
    VacancyState.ANALYZING: frozenset({
        VacancyState.ANALYZED,
        VacancyState.ANALYSIS_FAILED,
    }),
    VacancyState.ANALYSIS_FAILED: frozenset({
        VacancyState.ANALYSIS_QUEUED,  # retry
        VacancyState.DECLINED,
    }),
    VacancyState.ANALYZED: frozenset({
        VacancyState.CV_QUEUED,
        VacancyState.ANALYSIS_QUEUED,  # re-analyze
        VacancyState.DECLINED,
    }),
    VacancyState.CV_QUEUED: frozenset({
        VacancyState.CV_GENERATING,
        VacancyState.ANALYZED,         # cancel / dequeue
    }),
    VacancyState.CV_GENERATING: frozenset({
        VacancyState.CV_GENERATED,
        VacancyState.ANALYZED,         # rollback on failure
    }),
    VacancyState.CV_GENERATED: frozenset({
        VacancyState.COVER_GENERATING,
        VacancyState.CV_QUEUED,        # re-generate CV
        VacancyState.ANALYSIS_QUEUED,  # re-analyze from scratch
        VacancyState.DECLINED,
    }),
    VacancyState.COVER_GENERATING: frozenset({
        VacancyState.COVER_GENERATED,
        VacancyState.CV_GENERATED,     # rollback on failure
    }),
    VacancyState.COVER_GENERATED: frozenset({
        VacancyState.COVER_GENERATING, # re-generate cover
        VacancyState.CV_QUEUED,        # re-generate CV
        VacancyState.ANALYSIS_QUEUED,  # full re-analysis
        VacancyState.DECLINED,
    }),
    VacancyState.DECLINED: frozenset({
        VacancyState.FETCHED,          # restore — no analysis
        VacancyState.ANALYZED,         # restore — analysis_json present
    }),
    VacancyState.SKIPPED: frozenset({
        VacancyState.FETCHED,
        VacancyState.ANALYZED,
    }),
    # Legacy terminal states — allow re-entry
    VacancyState.DONE: frozenset({
        VacancyState.ANALYSIS_QUEUED,
    }),
    VacancyState.ERROR: frozenset({
        VacancyState.FETCHED,
        VacancyState.ANALYSIS_QUEUED,
    }),
}


# ── Exception ─────────────────────────────────────────────────────────────────


class FSMError(Exception):
    """Invalid or disallowed state transition."""


# ── Public API ────────────────────────────────────────────────────────────────


async def fsm_transition(vacancy_id: int, target: VacancyState) -> None:
    """Validate and apply a vacancy state transition.

    Reads current status from DB, checks against VALID_TRANSITIONS,
    then calls update_vacancy_status. Raises FSMError on invalid edge.
    """
    row = await database.get_vacancy_by_id(vacancy_id)
    if row is None:
        raise FSMError(f"Vacancy #{vacancy_id} not found")

    current_str = row["status"] or "fetched"
    try:
        current = VacancyState(current_str)
    except ValueError:
        raise FSMError(
            f"Vacancy #{vacancy_id} has unknown status {current_str!r}"
        )

    allowed = VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise FSMError(
            f"Vacancy #{vacancy_id}: {current!r} → {target!r} not allowed. "
            f"Allowed from {current!r}: {sorted(s.value for s in allowed)}"
        )

    await database.update_vacancy_status(vacancy_id, target.value)


def get_allowed_transitions(current: VacancyState) -> frozenset[VacancyState]:
    """Return the set of states reachable from current. Empty if unknown."""
    return VALID_TRANSITIONS.get(current, frozenset())
