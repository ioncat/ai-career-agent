"""
core/vacancy_stage.py — single source of truth for the 5-stage vacancy taxonomy
(Inbox / Analyzed / Processed / Applied / Archive).

This is a pure, read-only projection over (status, applied) — it does NOT
replace or narrow the fine-grained pipeline `status` field (workers still need
exact states like `cv_generating` to orchestrate). Applied stays an orthogonal
boolean rather than a terminal status: a user can apply having only analyzed a
vacancy (hand-tailored CV elsewhere), or after CV-only, or after CV+Cover —
collapsing that into one linear status would lose which stage was reached
before applying. `stage()` is the answer to "which folder does this vacancy
belong in", nothing more.

Used by:
- web/api.py — adds a `stage` field to GET /api/vacancies responses
- (future) core/vacancy_folder.py — physical folder-tree mirroring, BACKLOG P1
"""

STAGES = ("inbox", "analyzed", "processed", "applied", "archive")

# Legacy statuses (pre-dating the current FSM) mapped to their nearest
# equivalent — see BACKLOG "DB data cleanup" bug ticket for the underlying
# data-hygiene issue; this mapping just keeps them from falling through
# the taxonomy silently.
_LEGACY_TO_CURRENT = {
    "new": "fetched",
    "fetching": "fetched",
    "queued": "fetched",
    "done": "analyzed",
}

_PROCESSED_STATUSES = frozenset({"cv_generated", "cover_generating", "cover_generated"})
_ANALYZED_STATUSES = frozenset({"analyzed", "analysis_failed"})


def stage(status: str, applied: bool) -> str:
    """Classify a vacancy into one of STAGES from its (status, applied).

    Order matters: declined always wins (explicit reject), then applied
    (explicit success — the whole point of the pipeline), then the pipeline
    progress implied by status.
    """
    if status == "declined":
        return "archive"
    if applied:
        return "applied"

    resolved = _LEGACY_TO_CURRENT.get(status, status)
    if resolved in _PROCESSED_STATUSES:
        return "processed"
    if resolved in _ANALYZED_STATUSES:
        return "analyzed"
    return "inbox"
