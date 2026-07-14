"""
tests/test_pipeline_contracts.py — Pydantic contract validation for pipeline.py.

Covers: VacScoreDims, Phase1Data, FitDimensions, Phase2Data,
        Phase3Data, Phase4Data, AnalysisJson round-trip.
"""

import json

import pytest
from pydantic import ValidationError

from contracts.pipeline import (
    AnalysisJson,
    FitDimensions,
    Phase1Data,
    Phase2Data,
    Phase3Data,
    Phase4Data,
    VacScoreDims,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dims(**overrides) -> dict:
    base = {
        "company_tier": 3,
        "seniority": 4,
        "market_scope": 2,
        "company_type": 3,
        "company_stage_fit": 2,
        "domain_score": 4,
        "remote_policy": 3,
        "compensation": 2,
    }
    return {**base, **overrides}


def _p1(**overrides) -> dict:
    base = {
        "role": "Product Manager",
        "company": "Acme Corp",
        "north_star": "PM must ship CRM so that sales velocity doubles.",
        "primary_archetype": "Execution-heavy Platform/Systems PM",
        "company_type": "product",
        "role_balance": {"strategy": 20, "discovery": 20, "execution": 40, "stakeholder": 10, "operational": 10},
        "dominant_culture": "ownership",
        "vacscore_dims": _dims(),
        "vacancy_score": 7.4,
    }
    return {**base, **overrides}


def _fit_dims(**overrides) -> dict:
    base = {
        "domain_fit": 7.0,
        "execution_fit": 8.0,
        "strategy_fit": 6.0,
        "systems_fit": 7.5,
        "stakeholder_fit": 6.5,
        "overall_fit": 7.0,
    }
    return {**base, **overrides}


def _p2(**overrides) -> dict:
    base = {
        "fit_score": 7,
        "recommendation": "apply",
        "recommendation_label": "apply — strong match",
        "category": "Execution-heavy Platform/Systems PM · Remote",
        "who_they_want": "A senior PM who has shipped CRM integrations end-to-end.",
        "key_barriers": ["no direct CRM ownership"],
        "hidden_risks": ["early-stage, no PM process"],
        "warnings": [],
        "fit_dimensions": _fit_dims(),
    }
    return {**base, **overrides}


# ── VacScoreDims ─────────────────────────────────────────────────────────────

def test_vacscore_dims_valid():
    d = VacScoreDims(**_dims())
    assert d.company_tier == 3
    assert d.domain_score == 4


def test_vacscore_dims_boundary_values():
    d = VacScoreDims(**_dims(company_tier=1, seniority=4, market_scope=1, company_type=1,
                              company_stage_fit=1, domain_score=1, remote_policy=1, compensation=1))
    assert d.company_tier == 1

    d2 = VacScoreDims(**_dims(company_tier=4, domain_score=5))
    assert d2.domain_score == 5


def test_vacscore_dims_rejects_out_of_range():
    with pytest.raises(ValidationError):
        VacScoreDims(**_dims(company_tier=5))

    with pytest.raises(ValidationError):
        VacScoreDims(**_dims(domain_score=6))

    with pytest.raises(ValidationError):
        VacScoreDims(**_dims(market_scope=0))


def test_vacscore_dims_rejects_float():
    with pytest.raises(ValidationError):
        VacScoreDims(**_dims(company_tier=2.5))  # type: ignore[arg-type]


# ── Phase1Data ────────────────────────────────────────────────────────────────

def test_phase1_valid():
    p1 = Phase1Data(**_p1())
    assert p1.role == "Product Manager"
    assert p1.vacancy_score == 7.4
    assert isinstance(p1.vacscore_dims, VacScoreDims)


def test_phase1_vacancy_score_bounds():
    Phase1Data(**_p1(vacancy_score=0.0))
    Phase1Data(**_p1(vacancy_score=10.0))

    with pytest.raises(ValidationError):
        Phase1Data(**_p1(vacancy_score=10.1))

    with pytest.raises(ValidationError):
        Phase1Data(**_p1(vacancy_score=-0.1))


def test_phase1_company_type_enum():
    for ct in ("product", "hybrid", "outsourcing"):
        p = Phase1Data(**_p1(company_type=ct))
        assert p.company_type == ct

    with pytest.raises(ValidationError):
        Phase1Data(**_p1(company_type="agency"))


def test_phase1_role_balance_is_dict():
    p1 = Phase1Data(**_p1())
    assert isinstance(p1.role_balance, dict)
    assert p1.role_balance["strategy"] == 20


# ── FitDimensions ─────────────────────────────────────────────────────────────

def test_fit_dimensions_valid():
    fd = FitDimensions(**_fit_dims())
    assert fd.overall_fit == 7.0


def test_fit_dimensions_boundary():
    FitDimensions(**_fit_dims(overall_fit=0.0))
    FitDimensions(**_fit_dims(overall_fit=10.0))

    with pytest.raises(ValidationError):
        FitDimensions(**_fit_dims(domain_fit=10.5))


# ── Phase2Data ────────────────────────────────────────────────────────────────

def test_phase2_valid():
    p2 = Phase2Data(**_p2())
    assert p2.recommendation == "apply"
    assert p2.fit_score == 7
    assert isinstance(p2.fit_dimensions, FitDimensions)


def test_phase2_recommendation_enum():
    for rec, label in [
        ("apply", "apply — strong match"),
        ("take_a_chance", "take a chance"),
        ("decline", "decline"),
    ]:
        p = Phase2Data(**_p2(recommendation=rec, recommendation_label=label))
        assert p.recommendation == rec


def test_phase2_invalid_recommendation():
    with pytest.raises(ValidationError):
        Phase2Data(**_p2(recommendation="maybe"))


def test_phase2_recommendation_label_must_start_with_base():
    with pytest.raises(ValidationError):
        Phase2Data(**_p2(recommendation="apply", recommendation_label="decline — strong"))


def test_phase2_recommendation_label_case_insensitive():
    """Providers vary capitalisation — 'Apply' must validate against base 'apply'."""
    p = Phase2Data(**_p2(recommendation="apply", recommendation_label="Apply"))
    assert p.recommendation_label == "Apply"
    # Also the bare capitalised word (what tripped vacancy #660 with a switched provider)
    p2 = Phase2Data(**_p2(recommendation="take_a_chance", recommendation_label="Take a chance — premium"))
    assert p2.recommendation == "take_a_chance"


def test_phase2_fit_score_bounds():
    Phase2Data(**_p2(fit_score=1))
    Phase2Data(**_p2(fit_score=10))

    with pytest.raises(ValidationError):
        Phase2Data(**_p2(fit_score=0))

    with pytest.raises(ValidationError):
        Phase2Data(**_p2(fit_score=11))


def test_phase2_barriers_and_risks_default_empty():
    p2 = Phase2Data(**_p2(key_barriers=[], hidden_risks=[], warnings=[]))
    assert p2.key_barriers == []
    assert p2.warnings == []


def test_phase2_track_note_optional():
    p2_no_note = Phase2Data(**_p2())
    assert p2_no_note.track_note is None

    p2_with_note = Phase2Data(**_p2(track_note="Role differs significantly from PM/PO."))
    assert p2_with_note.track_note is not None


def test_phase2_decline_label():
    p2 = Phase2Data(**_p2(
        recommendation="decline",
        recommendation_label="decline — not worth the effort",
        fit_score=4,
    ))
    assert p2.recommendation == "decline"


# ── Phase3Data ────────────────────────────────────────────────────────────────

def test_phase3_valid():
    p3 = Phase3Data(name_variant="Alex Bondarenko", cv_language="en", changes_count=3)
    assert p3.cv_language == "en"
    assert p3.changes_count == 3


def test_phase3_language_enum():
    for lang in ("en", "uk", "both"):
        Phase3Data(name_variant="Test", cv_language=lang, changes_count=0)

    with pytest.raises(ValidationError):
        Phase3Data(name_variant="Test", cv_language="ru", changes_count=0)


def test_phase3_changes_count_non_negative():
    Phase3Data(name_variant="Test", cv_language="en", changes_count=0)

    with pytest.raises(ValidationError):
        Phase3Data(name_variant="Test", cv_language="en", changes_count=-1)


# ── Phase4Data ────────────────────────────────────────────────────────────────

def test_phase4_valid():
    p4 = Phase4Data(cover_language="uk")
    assert p4.cover_language == "uk"


def test_phase4_invalid_language():
    with pytest.raises(ValidationError):
        Phase4Data(cover_language="ru")


# ── AnalysisJson ──────────────────────────────────────────────────────────────

def test_analysis_json_empty():
    aj = AnalysisJson()
    assert aj.p1 is None
    assert aj.p2 is None
    assert aj.phases_done() == []


def test_analysis_json_partial_p1_only():
    aj = AnalysisJson(p1=Phase1Data(**_p1()))
    assert aj.p1 is not None
    assert aj.p2 is None
    assert aj.phases_done() == ["p1"]


def test_analysis_json_all_phases():
    aj = AnalysisJson(
        p1=Phase1Data(**_p1()),
        p2=Phase2Data(**_p2()),
        p3=Phase3Data(name_variant="Alex", cv_language="en", changes_count=2),
        p4=Phase4Data(cover_language="en"),
    )
    assert aj.phases_done() == ["p1", "p2", "p3", "p4"]


def test_analysis_json_round_trip_json():
    aj = AnalysisJson(
        p1=Phase1Data(**_p1()),
        p2=Phase2Data(**_p2()),
    )
    serialized = aj.model_dump_json(exclude_none=True)
    parsed = json.loads(serialized)
    assert "p1" in parsed
    assert "p2" in parsed
    assert "p3" not in parsed

    restored = AnalysisJson.model_validate(parsed)
    assert restored.p1.role == "Product Manager"
    assert restored.p2.recommendation == "apply"


def test_analysis_json_from_empty_string():
    aj = AnalysisJson.model_validate_json("{}")
    assert aj.phases_done() == []


def test_analysis_json_model_validate_json():
    raw = json.dumps({
        "p1": _p1() | {"vacscore_dims": _dims()},
        "p2": _p2() | {"fit_dimensions": _fit_dims()},
    })
    aj = AnalysisJson.model_validate_json(raw)
    assert aj.p1.company == "Acme Corp"
    assert aj.p2.fit_score == 7
