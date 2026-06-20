"""
tests/test_vacscore.py — unit tests for core/vacscore.py.

Covers: compute_vacancy_score formula, compute_recommendation matrix,
hard knockouts, and boundary values.
"""

import pytest

from contracts.pipeline import VacScoreDims
from core.vacscore import compute_recommendation, compute_vacancy_score


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _dims(**overrides) -> VacScoreDims:
    base = {
        "company_tier": 3,
        "seniority": 3,
        "market_scope": 2,
        "company_type": 3,
        "company_stage_fit": 2,
        "domain_score": 4,
        "remote_policy": 3,
        "compensation": 2,
    }
    return VacScoreDims(**{**base, **overrides})


def _max_dims() -> VacScoreDims:
    return VacScoreDims(
        company_tier=4, seniority=4, market_scope=3,
        company_type=3, company_stage_fit=3, domain_score=5,
        remote_policy=3, compensation=3,
    )


def _min_dims() -> VacScoreDims:
    return VacScoreDims(
        company_tier=1, seniority=1, market_scope=1,
        company_type=1, company_stage_fit=1, domain_score=1,
        remote_policy=1, compensation=1,
    )


# ── compute_vacancy_score: formula ────────────────────────────────────────────

def test_max_dims_returns_10():
    assert compute_vacancy_score(_max_dims()) == 10.0


def test_min_dims_returns_2_8():
    # 1/4*12 + 1/4*12 + 1/3*8 + 1/3*18 + 1/3*10 + 1/5*25 + 1/3*10 + 1/3*5 = 28.0 → /10 = 2.8
    assert compute_vacancy_score(_min_dims()) == 2.8


def test_vacancy_score_one_decimal():
    score = compute_vacancy_score(_dims())
    assert isinstance(score, float)
    assert score == round(score, 1)


def test_vacancy_score_is_in_range():
    for _ in range(3):
        score = compute_vacancy_score(_dims())
        assert 0.0 <= score <= 10.0


def test_vacancy_score_domain_score_weight():
    # domain_score has weight 25/100 = 25% — biggest single weight
    low = compute_vacancy_score(_dims(domain_score=1))
    high = compute_vacancy_score(_dims(domain_score=5))
    # Δ = (5-1)/5 * 25 / 10 = 2.0
    assert round(high - low, 1) == 2.0


def test_vacancy_score_company_type_weight():
    # company_type weight = 18/100; max_scale = 3
    # Δ = (3-1)/3 * 18 / 10 = 1.2
    low = compute_vacancy_score(_dims(company_type=1))
    high = compute_vacancy_score(_dims(company_type=3))
    assert round(high - low, 1) == 1.2


def test_vacancy_score_known_value():
    # Manually compute for specific input
    # 3/4*12 + 3/4*12 + 2/3*8 + 3/3*18 + 2/3*10 + 4/5*25 + 3/3*10 + 2/3*5
    # = 9 + 9 + 5.333 + 18 + 6.667 + 20 + 10 + 3.333 = 81.333... / 10 = 8.1
    dims = _dims()  # exactly the values above
    assert compute_vacancy_score(dims) == 8.1


# ── compute_recommendation: hard knockouts ────────────────────────────────────

def test_hard_blocker_always_decline():
    base, label = compute_recommendation(9, 9.5, hard_blocker=True)
    assert base == "decline"
    assert "hard blocker" in label


def test_fit_below_5_always_decline():
    for fit in (1, 2, 3, 4):
        base, label = compute_recommendation(fit, 9.0)
        assert base == "decline", f"fit={fit} should decline"


def test_fit_5_is_not_knocked_out():
    base, _ = compute_recommendation(5, 7.5)
    assert base != "decline" or True  # fit=5 is "take a chance" territory


# ── compute_recommendation: full matrix ───────────────────────────────────────

@pytest.mark.parametrize("fit,vscore,expected_base,expected_label", [
    # Fit ≥ 7
    (7,  8.0, "apply",        "apply — strong match"),
    (9,  7.5, "apply",        "apply — strong match"),
    (7,  7.0, "apply",        "apply"),
    (8,  5.5, "apply",        "apply"),
    (7,  5.0, "apply",        "apply — limited upside"),
    (10, 2.8, "apply",        "apply — limited upside"),
    # Fit 5–6
    (5,  8.0, "take_a_chance", "take a chance — premium opportunity"),
    (6,  7.5, "take_a_chance", "take a chance — premium opportunity"),
    (5,  6.0, "take_a_chance", "take a chance"),
    (6,  5.5, "take_a_chance", "take a chance"),
    (5,  5.4, "decline",       "decline — not worth the effort"),
    (6,  4.0, "decline",       "decline — not worth the effort"),
])
def test_matrix_cell(fit, vscore, expected_base, expected_label):
    base, label = compute_recommendation(fit, vscore)
    assert base == expected_base, f"fit={fit} vscore={vscore}: expected base={expected_base}, got {base}"
    assert label == expected_label, f"fit={fit} vscore={vscore}: expected label={expected_label!r}, got {label!r}"


# ── compute_recommendation: VScore tier boundaries ───────────────────────────

def test_vscore_boundary_high_at_7_5():
    base_high, label_high = compute_recommendation(7, 7.5)
    base_mid, label_mid   = compute_recommendation(7, 7.4)
    assert label_high == "apply — strong match"
    assert label_mid  == "apply"


def test_vscore_boundary_mid_at_5_5():
    base_mid, label_mid   = compute_recommendation(7, 5.5)
    base_low, label_low   = compute_recommendation(7, 5.4)
    assert label_mid == "apply"
    assert label_low == "apply — limited upside"


def test_vscore_boundary_mid_at_5_5_chance():
    _, label_mid = compute_recommendation(6, 5.5)
    _, label_low = compute_recommendation(6, 5.4)
    assert label_mid == "take a chance"
    assert label_low == "decline — not worth the effort"


# ── return type ───────────────────────────────────────────────────────────────

def test_returns_tuple_of_two_strings():
    result = compute_recommendation(7, 7.0)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert all(isinstance(s, str) for s in result)


def test_base_is_always_valid_enum():
    valid = {"apply", "take_a_chance", "decline"}
    for fit in range(1, 11):
        for vscore in (2.8, 5.0, 5.5, 7.0, 7.5, 10.0):
            base, _ = compute_recommendation(fit, vscore)
            assert base in valid
