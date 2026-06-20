"""
core/vacscore.py — Deterministic VacScore computation.

LLM assigns raw dimension scores; this module does the arithmetic.
No LLM calls here — pure deterministic Python.

Usage:
    from core.vacscore import compute_vacancy_score, compute_recommendation

    score = compute_vacancy_score(dims)          # float 0.0–10.0
    base, label = compute_recommendation(fit, score)
"""

from __future__ import annotations

from contracts.pipeline import VacScoreDims

# (max_scale, weight) pairs from phase1_analysis.md §1.7 formula.
# Total weights sum to 100 → divide by 10 → result on 0–10 scale.
_WEIGHTS: dict[str, tuple[int, int]] = {
    "company_tier":      (4, 12),
    "seniority":         (4, 12),
    "market_scope":      (3,  8),
    "company_type":      (3, 18),
    "company_stage_fit": (3, 10),
    "domain_score":      (5, 25),
    "remote_policy":     (3, 10),
    "compensation":      (3,  5),
}

assert sum(w for _, w in _WEIGHTS.values()) == 100, "weights must sum to 100"


def compute_vacancy_score(dims: VacScoreDims) -> float:
    """Compute composite vacancy_score (0.0–10.0) from raw dim scores.

    Formula (phase1_analysis.md §1.7):
        score = round(Σ(dim/max_scale * weight) / 10, 1)

    Returns value in [0.0, 10.0] with 1 decimal place.
    Minimum possible value is 2.8 (all dims at 1).
    Maximum is 10.0 (all dims at their max).
    """
    total = sum(
        (getattr(dims, field) / max_scale) * weight
        for field, (max_scale, weight) in _WEIGHTS.items()
    )
    return round(total / 10, 1)


def compute_recommendation(
    fit_score: int,
    vacancy_score: float,
    *,
    hard_blocker: bool = False,
) -> tuple[str, str]:
    """Compute (base, label) from Fit × VacScore matrix.

    base:  "apply" | "take_a_chance" | "decline"  — stored in DB
    label: display string with modifier             — shown in UI only

    Hard knockouts (override matrix, checked first):
        hard_blocker=True  → ("decline", "decline — hard blocker")
        fit_score < 5      → ("decline", "decline")

    Matrix (phase2_fit.md):
        Fit ≥ 7 · VScore ≥ 7.5   → apply — strong match
        Fit ≥ 7 · VScore 5.5–7.4 → apply
        Fit ≥ 7 · VScore < 5.5   → apply — limited upside
        Fit 5–6 · VScore ≥ 7.5   → take a chance — premium opportunity
        Fit 5–6 · VScore 5.5–7.4 → take a chance
        Fit 5–6 · VScore < 5.5   → decline — not worth the effort

    VScore tier boundaries: high ≥ 7.5, mid ≥ 5.5, low < 5.5.
    """
    if hard_blocker:
        return ("decline", "decline — hard blocker")
    if fit_score < 5:
        return ("decline", "decline")

    high = vacancy_score >= 7.5
    mid = vacancy_score >= 5.5  # 5.5 ≤ x < 7.5

    if fit_score >= 7:
        if high:
            return ("apply", "apply — strong match")
        if mid:
            return ("apply", "apply")
        return ("apply", "apply — limited upside")

    # fit 5–6
    if high:
        return ("take_a_chance", "take a chance — premium opportunity")
    if mid:
        return ("take_a_chance", "take a chance")
    return ("decline", "decline — not worth the effort")
