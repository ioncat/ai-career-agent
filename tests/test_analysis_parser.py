"""
tests/test_analysis_parser.py — Unit tests for cv_analyze.py parser helpers.

Tests _parse_vacscore_dims, _parse_phase1_data, _parse_phase2_data,
_build_analysis_json with realistic LLM output samples.
"""

import pytest

from tools.cv_analyze import (
    _build_analysis_json,
    _parse_fit_dimensions,
    _parse_phase1_data,
    _parse_phase2_data,
    _parse_vacscore_dims,
    _rec_label_to_base,
    _split_semicolons,
)


# ── Sample LLM outputs ────────────────────────────────────────────────────────

PHASE1_SAMPLE = """
**Role:** Product Manager
**Company:** Stripe

**North Star:** PM must own the CRM product so that sales velocity doubles.

**Sub-goals:**
├── discovery — user research, interviews
└── delivery — feature roadmap, backlog

### 1.4 Role Balance

- Strategy: 20%
- Discovery: 30%
- Execution/delivery: 30%
- Stakeholder coordination: 10%
- Operational/process work: 10%

**Primary archetype:** `Execution-heavy Platform/Systems PM`

### 1.6 Language Analysis

Which dominates: **Ownership** / Delivery.
Culture type: product-led.

### 1.7 Vacancy Score

**VScore:** 8.1/10

| Dim | Score | Reasoning |
|-----|-------|-----------|
| company_tier | 4/4 | top global brand |
| seniority | 4/4 | senior/lead role |
| market_scope | 3/3 | global product |
| company_type | 3/3 | product company |
| company_stage_fit | 2/3 | partial match |
| domain_score | 4/5 | interest=2, longevity=2 |
| remote_policy | 3/3 | full remote |
| compensation | 2/3 | not stated |
"""

PHASE2_SAMPLE = """
## Quick Scan
**Fit score:** 7/10
**Recommendation:** apply — strong match
**Category:** Execution-heavy Platform/Systems PM · Remote
**Who they want:** A senior PM who has shipped CRM integrations end-to-end.

**Key Barriers:** no direct CRM ownership; A/B testing gap
**Hidden Risks:** early-stage, no confirmed funding
**Warnings:** нет

---

## Fit Breakdown

| Требование из JD | Статус | Опыт кандидата |
|--|--|--|
| CRM product ownership | ⚠️ | pet-project only |

---

## Internal Analysis

### Fit Dimensions

| Измерение | Оценка /10 | Комментарий |
|-----------|-----------|---------|
| Domain fit | 7 | partial domain match |
| Execution fit | 8 | strong delivery track |
| Strategy fit | 6 | limited strategy |
| Systems/platform fit | 7 | platform experience |
| Stakeholder fit | 6 | coordinator background |
| **Overall fit** | 7 | solid candidate |
"""

PHASE2_TAKE_CHANCE = """
## Quick Scan
**Fit score:** 5/10
**Recommendation:** take a chance — premium opportunity
**Category:** Discovery-heavy PM · Hybrid
**Who they want:** A PM with deep fintech experience.

**Key Barriers:** no fintech domain
**Hidden Risks:** нет
**Warnings:** нет

## Internal Analysis
### Fit Dimensions
| Измерение | Оценка /10 | Комментарий |
|--|--|--|
| Domain fit | 5 | |
| Execution fit | 6 | |
| Strategy fit | 5 | |
| Systems/platform fit | 5 | |
| Stakeholder fit | 5 | |
| **Overall fit** | 5 | |
"""


# ── _split_semicolons ─────────────────────────────────────────────────────────

def test_split_semicolons_basic():
    result = _split_semicolons("gap1; gap2; gap3")
    assert result == ["gap1", "gap2", "gap3"]


def test_split_semicolons_filters_none():
    result = _split_semicolons("нет")
    assert result == []


def test_split_semicolons_filters_empty():
    result = _split_semicolons("")
    assert result == []


def test_split_semicolons_strips_trailing_dot():
    result = _split_semicolons("gap1.; gap2")
    assert result[0] == "gap1"


# ── _rec_label_to_base ────────────────────────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("apply — strong match", "apply"),
    ("apply", "apply"),
    ("apply — limited upside", "apply"),
    ("take a chance — premium opportunity", "take_a_chance"),
    ("take a chance", "take_a_chance"),
    ("decline", "decline"),
    ("decline — not worth the effort", "decline"),
])
def test_rec_label_to_base(label, expected):
    assert _rec_label_to_base(label) == expected


def test_rec_label_to_base_unknown():
    assert _rec_label_to_base("maybe") is None


# ── _parse_vacscore_dims ──────────────────────────────────────────────────────

def test_parse_vacscore_dims_all_8_dims():
    dims = _parse_vacscore_dims(PHASE1_SAMPLE)
    assert dims is not None
    assert dims.company_tier == 4
    assert dims.seniority == 4
    assert dims.market_scope == 3
    assert dims.company_type == 3
    assert dims.company_stage_fit == 2
    assert dims.domain_score == 4
    assert dims.remote_policy == 3
    assert dims.compensation == 2


def test_parse_vacscore_dims_returns_none_on_missing():
    result = _parse_vacscore_dims("no table here")
    assert result is None


def test_parse_vacscore_dims_partial_table_returns_none():
    partial = "| company_tier | 3/4 | reason |\n| seniority | 4/4 | reason |"
    result = _parse_vacscore_dims(partial)
    assert result is None  # not all 8 dims present


# ── _parse_fit_dimensions ─────────────────────────────────────────────────────

def test_parse_fit_dimensions_all_fields():
    fd = _parse_fit_dimensions(PHASE2_SAMPLE)
    assert fd is not None
    assert fd.domain_fit == 7.0
    assert fd.execution_fit == 8.0
    assert fd.strategy_fit == 6.0
    assert fd.systems_fit == 7.0
    assert fd.stakeholder_fit == 6.0
    assert fd.overall_fit == 7.0


def test_parse_fit_dimensions_none_on_missing():
    fd = _parse_fit_dimensions("no fit table")
    assert fd is None


# ── _parse_phase1_data ────────────────────────────────────────────────────────

def test_parse_phase1_data_success():
    p1 = _parse_phase1_data(PHASE1_SAMPLE)
    assert p1 is not None
    assert p1.role == "Product Manager"
    assert p1.company == "Stripe"
    assert "CRM" in p1.north_star
    assert p1.primary_archetype == "Execution-heavy Platform/Systems PM"
    assert p1.company_type == "product"
    assert p1.vacscore_dims.company_tier == 4


def test_parse_phase1_data_computes_vacscore():
    p1 = _parse_phase1_data(PHASE1_SAMPLE)
    assert p1 is not None
    # dims: 4/4*12 + 4/4*12 + 3/3*8 + 3/3*18 + 2/3*10 + 4/5*25 + 3/3*10 + 2/3*5 = 95.33/10 = 9.5
    assert 0.0 <= p1.vacancy_score <= 10.0
    assert isinstance(p1.vacancy_score, float)


def test_parse_phase1_data_role_balance():
    p1 = _parse_phase1_data(PHASE1_SAMPLE)
    assert p1 is not None
    assert p1.role_balance.get("strategy") == 20
    assert p1.role_balance.get("discovery") == 30


def test_parse_phase1_data_dominant_culture():
    p1 = _parse_phase1_data(PHASE1_SAMPLE)
    assert p1 is not None
    assert p1.dominant_culture == "ownership"


def test_parse_phase1_data_returns_none_on_no_dims():
    result = _parse_phase1_data("**Role:** PM\n**Company:** X\nNo dim table.")
    assert result is None


def test_parse_phase1_data_returns_none_on_no_role():
    result = _parse_phase1_data("| company_tier | 3/4 | x |\n")
    assert result is None


# ── _parse_phase2_data ────────────────────────────────────────────────────────

def test_parse_phase2_data_apply():
    from tools.cv_analyze import _parse_vacscore_dims
    dims = _parse_vacscore_dims(PHASE1_SAMPLE)
    p2 = _parse_phase2_data(PHASE2_SAMPLE, dims)
    assert p2 is not None
    assert p2.fit_score == 7
    assert p2.recommendation == "apply"
    assert "no direct CRM ownership" in p2.key_barriers
    assert p2.warnings == []
    assert p2.fit_dimensions.execution_fit == 8.0


def test_parse_phase2_data_recommendation_overridden_by_python(monkeypatch):
    """Python compute_recommendation overrides LLM label when dims available."""
    from contracts.pipeline import VacScoreDims
    from tools.cv_analyze import _parse_phase2_data

    dims = VacScoreDims(
        company_tier=1, seniority=1, market_scope=1, company_type=1,
        company_stage_fit=1, domain_score=1, remote_policy=1, compensation=1,
    )
    # fit=7 + vacscore=2.8 (<5.5) → "apply — limited upside" from Python matrix
    p2 = _parse_phase2_data(PHASE2_SAMPLE, dims)
    assert p2 is not None
    assert p2.recommendation == "apply"
    assert "limited upside" in p2.recommendation_label


def test_parse_phase2_data_take_a_chance():
    p2 = _parse_phase2_data(PHASE2_TAKE_CHANCE, None)
    assert p2 is not None
    assert p2.fit_score == 5
    assert p2.recommendation == "take_a_chance"


def test_parse_phase2_data_returns_none_on_no_fit():
    result = _parse_phase2_data("no fit score here", None)
    assert result is None


def test_parse_phase2_data_hidden_risks():
    p2 = _parse_phase2_data(PHASE2_SAMPLE, None)
    assert p2 is not None
    assert "early-stage" in p2.hidden_risks[0]


def test_parse_phase2_data_category():
    p2 = _parse_phase2_data(PHASE2_SAMPLE, None)
    assert p2 is not None
    assert "Remote" in p2.category


def test_parse_phase2_data_who_they_want():
    p2 = _parse_phase2_data(PHASE2_SAMPLE, None)
    assert p2 is not None
    assert "CRM" in p2.who_they_want


# ── _build_analysis_json ──────────────────────────────────────────────────────

def test_build_analysis_json_full():
    aj = _build_analysis_json(PHASE1_SAMPLE, PHASE2_SAMPLE)
    assert aj.p1 is not None
    assert aj.p2 is not None
    assert aj.p1.role == "Product Manager"
    assert aj.p2.fit_score == 7
    assert aj.phases_done() == ["p1", "p2"]


def test_build_analysis_json_partial_on_bad_phase2():
    aj = _build_analysis_json(PHASE1_SAMPLE, "garbage output")
    assert aj.p1 is not None
    assert aj.p2 is None
    assert aj.phases_done() == ["p1"]


def test_build_analysis_json_empty_on_bad_both():
    aj = _build_analysis_json("garbage", "garbage")
    assert aj.p1 is None
    assert aj.p2 is None
    assert aj.phases_done() == []


def test_build_analysis_json_json_serializable():
    import json
    aj = _build_analysis_json(PHASE1_SAMPLE, PHASE2_SAMPLE)
    serialized = aj.model_dump_json(exclude_none=True)
    parsed = json.loads(serialized)
    assert "p1" in parsed
    assert "p2" in parsed
