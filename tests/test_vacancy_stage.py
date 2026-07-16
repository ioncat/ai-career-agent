"""tests/test_vacancy_stage.py — core/vacancy_stage.py: 5-stage taxonomy classifier."""

import pytest

from core.vacancy_stage import stage


@pytest.mark.parametrize(
    "status,applied,expected",
    [
        # Inbox — not yet analyzed / mid-pipeline before analysis completes
        ("fetched", False, "inbox"),
        ("analysis_queued", False, "inbox"),
        ("analyzing", False, "inbox"),
        ("cv_queued", False, "inbox"),
        ("cv_generating", False, "inbox"),
        # Analyzed — Phase 1+2 done (or failed retry, still "seen")
        ("analyzed", False, "analyzed"),
        ("analysis_failed", False, "analyzed"),
        # Processed — CV and/or Cover generated
        ("cv_generated", False, "processed"),
        ("cover_generating", False, "processed"),
        ("cover_generated", False, "processed"),
        # Archive — declined always wins regardless of applied
        ("declined", False, "archive"),
        ("declined", True, "archive"),
        # Legacy statuses map to their nearest current equivalent
        ("new", False, "inbox"),
        ("fetching", False, "inbox"),
        ("queued", False, "inbox"),
        ("done", False, "analyzed"),
    ],
)
def test_stage_classification(status, applied, expected):
    assert stage(status, applied) == expected


@pytest.mark.parametrize(
    "status",
    ["fetched", "analyzing", "analyzed", "cv_generated", "cover_generated", "new", "done"],
)
def test_applied_wins_over_any_non_declined_status(status):
    """Applied is orthogonal — it wins over pipeline progress at any stage,
    because the user can apply having only analyzed, or CV-only, or CV+Cover."""
    assert stage(status, True) == "applied"


def test_unknown_status_falls_back_to_inbox():
    """An unrecognized status (future addition, typo, migration gap) must not
    crash or silently vanish from every folder — falls back to Inbox (safest:
    visible, not lost in Archive)."""
    assert stage("some_future_status", False) == "inbox"
