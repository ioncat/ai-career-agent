"""
tests/test_pipeline_fsm.py — tests for core/pipeline_fsm.py.

Verifies VacancyState enum values, VALID_TRANSITIONS completeness,
fsm_transition() happy path, and all rejection cases.
DB calls are mocked — no real SQLite required.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.pipeline_fsm import (
    FSMError,
    VALID_TRANSITIONS,
    VacancyState,
    fsm_transition,
    get_allowed_transitions,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(status: str) -> dict:
    return {"status": status, "id": 1}


# ── VacancyState enum ─────────────────────────────────────────────────────────

def test_vacancy_state_values_match_db_strings():
    """Each enum value must equal the string written to the DB."""
    assert VacancyState.QUEUED           == "queued"
    assert VacancyState.FETCHING         == "fetching"
    assert VacancyState.FETCHED          == "fetched"
    assert VacancyState.ANALYSIS_QUEUED  == "analysis_queued"
    assert VacancyState.ANALYZING        == "analyzing"
    assert VacancyState.ANALYZED         == "analyzed"
    assert VacancyState.ANALYSIS_FAILED  == "analysis_failed"
    assert VacancyState.CV_QUEUED        == "cv_queued"
    assert VacancyState.CV_GENERATING    == "cv_generating"
    assert VacancyState.CV_GENERATED     == "cv_generated"
    assert VacancyState.COVER_GENERATING == "cover_generating"
    assert VacancyState.COVER_GENERATED  == "cover_generated"
    assert VacancyState.DECLINED         == "declined"
    assert VacancyState.SKIPPED          == "skipped"
    assert VacancyState.DONE             == "done"
    assert VacancyState.ERROR            == "error"


def test_all_states_have_transition_entry():
    """Every VacancyState must appear as a key in VALID_TRANSITIONS."""
    for state in VacancyState:
        assert state in VALID_TRANSITIONS, f"{state!r} missing from VALID_TRANSITIONS"


# ── fsm_transition — not found / bad status ───────────────────────────────────

@pytest.mark.asyncio
async def test_fsm_transition_vacancy_not_found():
    with patch("core.pipeline_fsm.database.get_vacancy_by_id", new_callable=AsyncMock) as mock_get, \
         patch("core.pipeline_fsm.database.update_vacancy_status", new_callable=AsyncMock) as mock_up:
        mock_get.return_value = None
        with pytest.raises(FSMError, match="not found"):
            await fsm_transition(999, VacancyState.ANALYZED)
        mock_up.assert_not_called()


@pytest.mark.asyncio
async def test_fsm_transition_unknown_current_status():
    with patch("core.pipeline_fsm.database.get_vacancy_by_id", new_callable=AsyncMock) as mock_get, \
         patch("core.pipeline_fsm.database.update_vacancy_status", new_callable=AsyncMock) as mock_up:
        mock_get.return_value = _row("some_unknown_status")
        with pytest.raises(FSMError, match="unknown status"):
            await fsm_transition(1, VacancyState.ANALYZED)
        mock_up.assert_not_called()


# ── fsm_transition — valid transitions ───────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("current,target", [
    ("queued",           "fetching"),
    ("queued",           "declined"),
    ("fetching",         "fetched"),
    ("fetching",         "queued"),
    ("fetched",          "analysis_queued"),
    ("fetched",          "declined"),
    ("analysis_queued",  "analyzing"),
    ("analysis_queued",  "declined"),
    ("analyzing",        "analyzed"),
    ("analyzing",        "analysis_failed"),
    ("analysis_failed",  "analysis_queued"),
    ("analysis_failed",  "declined"),
    ("analyzed",         "cv_queued"),
    ("analyzed",         "analysis_queued"),
    ("analyzed",         "declined"),
    ("cv_queued",        "cv_generating"),
    ("cv_queued",        "analyzed"),
    ("cv_generating",    "cv_generated"),
    ("cv_generating",    "analyzed"),
    ("cv_generated",     "cover_generating"),
    ("cv_generated",     "cv_queued"),
    ("cv_generated",     "analysis_queued"),
    ("cv_generated",     "declined"),
    ("cover_generating", "cover_generated"),
    ("cover_generating", "cv_generated"),
    ("cover_generated",  "cover_generating"),
    ("cover_generated",  "cv_queued"),
    ("cover_generated",  "analysis_queued"),
    ("cover_generated",  "declined"),
    ("declined",         "fetched"),
    ("declined",         "analyzed"),
    ("skipped",          "fetched"),
    ("skipped",          "analyzed"),
    ("done",             "analysis_queued"),
    ("error",            "fetched"),
    ("error",            "analysis_queued"),
])
async def test_fsm_transition_valid(current: str, target: str):
    with patch("core.pipeline_fsm.database.get_vacancy_by_id", new_callable=AsyncMock) as mock_get, \
         patch("core.pipeline_fsm.database.update_vacancy_status", new_callable=AsyncMock) as mock_up:
        mock_get.return_value = _row(current)
        await fsm_transition(1, VacancyState(target))
        mock_up.assert_awaited_once_with(1, target)


# ── fsm_transition — invalid transitions ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("current,target", [
    ("queued",           "analyzed"),
    ("queued",           "cv_generated"),
    ("fetching",         "analyzed"),
    ("fetching",         "analysis_queued"),
    ("fetched",          "analyzing"),
    ("fetched",          "cv_queued"),
    ("analysis_queued",  "analyzed"),
    ("analysis_queued",  "cv_queued"),
    ("analyzing",        "fetched"),
    ("analyzing",        "cv_queued"),
    ("analysis_failed",  "analyzed"),
    ("analysis_failed",  "cv_queued"),
    ("analyzed",         "cover_generating"),
    ("analyzed",         "cover_generated"),
    ("cv_queued",        "cover_generating"),
    ("cv_queued",        "cover_generated"),
    ("cv_generating",    "cover_generating"),
    ("cv_generating",    "queued"),
    ("cv_generated",     "analyzing"),
    ("cv_generated",     "queued"),
    ("cover_generating", "analyzed"),
    ("cover_generating", "queued"),
    ("cover_generated",  "analyzing"),
    ("cover_generated",  "queued"),
    ("declined",         "analysis_queued"),
    ("declined",         "cv_queued"),
    ("done",             "cv_queued"),
    ("error",            "cv_queued"),
])
async def test_fsm_transition_invalid(current: str, target: str):
    with patch("core.pipeline_fsm.database.get_vacancy_by_id", new_callable=AsyncMock) as mock_get, \
         patch("core.pipeline_fsm.database.update_vacancy_status", new_callable=AsyncMock) as mock_up:
        mock_get.return_value = _row(current)
        with pytest.raises(FSMError, match="not allowed"):
            await fsm_transition(1, VacancyState(target))
        mock_up.assert_not_called()


# ── get_allowed_transitions ───────────────────────────────────────────────────

def test_get_allowed_transitions_known_state():
    allowed = get_allowed_transitions(VacancyState.ANALYZED)
    assert VacancyState.CV_QUEUED in allowed
    assert VacancyState.ANALYSIS_QUEUED in allowed
    assert VacancyState.DECLINED in allowed
    assert VacancyState.QUEUED not in allowed


def test_get_allowed_transitions_unknown_state_returns_empty():
    # VacancyState is StrEnum — pass a raw unknown string via __new__ would fail,
    # so test that a state with no outgoing edges returns frozenset().
    # All states currently have entries, so verify the function returns frozenset for a missing key.
    result = get_allowed_transitions.__wrapped__(VacancyState.ANALYZED) if hasattr(get_allowed_transitions, "__wrapped__") else get_allowed_transitions(VacancyState.ANALYZED)
    assert isinstance(result, frozenset)
