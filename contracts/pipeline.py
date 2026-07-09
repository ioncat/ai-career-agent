"""
contracts/pipeline.py — Pydantic contracts for pipeline phase outputs.

Stored as JSON in vacancies.analysis_json:
    {"p1": {...}, "p2": {...}, "p3": {...}, "p4": {...}}

Each phase key is optional — absent key means phase not yet run.
LLM populates p1/p2 via cv_analyze; p3/p4 via cv_generate/cv_cover.
B2 (VacScore Python computation) reads vacscore_dims from p1 and computes
vacancy_score in Python, overwriting the LLM-computed value.

Flutter reads this via GET /api/vacancies/{id}/analysis.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Phase 1 ───────────────────────────────────────────────────────────────────


class VacScoreDims(BaseModel):
    """Raw dimension scores from Phase 1 §1.7 Vacancy Score.

    LLM assigns each dim; B2 uses them to compute vacancy_score in Python.
    Range constraints match prompt scale definitions.
    """

    company_tier: int = Field(ge=1, le=4)
    seniority: int = Field(ge=1, le=4)
    market_scope: int = Field(ge=1, le=3)
    company_type: int = Field(ge=1, le=3)
    company_stage_fit: int = Field(ge=1, le=3)
    domain_score: int = Field(ge=1, le=5)
    remote_policy: int = Field(ge=1, le=3)
    compensation: int = Field(ge=1, le=3)


class Phase1Data(BaseModel):
    """Structured output of Phase 1 analysis.

    Stored in analysis_json['p1']. Markdown blobs (pain_points, maturity
    signals, etc.) are not stored here — they live in JD_analysis.md.
    Only machine-readable fields that Flutter or B2 need are modelled.
    """

    role: str
    company: str
    north_star: str
    primary_archetype: str
    company_type: Literal["product", "hybrid", "outsourcing"]
    role_balance: dict[str, int]
    dominant_culture: str
    vacscore_dims: VacScoreDims
    vacancy_score: float = Field(ge=0.0, le=10.0)


# ── Phase 2 ───────────────────────────────────────────────────────────────────


class FitDimensions(BaseModel):
    """Fit dimension scores from Phase 2 § Internal Analysis."""

    domain_fit: float = Field(ge=0.0, le=10.0)
    execution_fit: float = Field(ge=0.0, le=10.0)
    strategy_fit: float = Field(ge=0.0, le=10.0)
    systems_fit: float = Field(ge=0.0, le=10.0)
    stakeholder_fit: float = Field(ge=0.0, le=10.0)
    overall_fit: float = Field(ge=0.0, le=10.0)


Recommendation = Literal["apply", "take_a_chance", "decline"]


class Phase2Data(BaseModel):
    """Structured output of Phase 2 fit assessment.

    Stored in analysis_json['p2']. recommendation_label is display-only
    (e.g. "apply — strong match") and is NOT used for logic — use
    recommendation for routing. Full fit breakdown and adaptation plan
    text stays in JD_analysis.md.
    """

    fit_score: int = Field(ge=1, le=10)
    recommendation: Recommendation
    recommendation_label: str
    category: str
    who_they_want: str
    key_barriers: list[str] = Field(default_factory=list)
    hidden_risks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    why_apply: list[str] = Field(default_factory=list)
    why_not_apply: list[str] = Field(default_factory=list)
    track_note: str | None = None
    fit_dimensions: FitDimensions

    @field_validator("recommendation_label")
    @classmethod
    def label_starts_with_recommendation(cls, v: str, info) -> str:
        rec = info.data.get("recommendation", "")
        base = rec.replace("_", " ") if rec else ""
        if base and not v.startswith(base):
            raise ValueError(
                f"recommendation_label '{v}' must start with base recommendation '{base}'"
            )
        return v


# ── Phase 3+3.5 ───────────────────────────────────────────────────────────────


class Phase3Data(BaseModel):
    """Metadata from Phase 3+3.5 CV generation.

    CV markdown is stored on disk (vacancies/{id}/CV.md).
    Stored in analysis_json['p3'].
    """

    name_variant: str
    cv_language: Literal["en", "uk", "both"]
    changes_count: int = Field(ge=0)


# ── Phase 4 ───────────────────────────────────────────────────────────────────


class Phase4Data(BaseModel):
    """Metadata from Phase 4 cover message.

    Cover markdown is stored on disk (vacancies/{id}/Cover.md).
    Stored in analysis_json['p4'].
    """

    cover_language: Literal["en", "uk"]


# ── Root ──────────────────────────────────────────────────────────────────────


class AnalysisJson(BaseModel):
    """Root model for vacancies.analysis_json column.

    Each phase key is optional: absent = phase not yet run.
    Partial state (e.g. p1 done, p2 not yet) is valid.

    Read from DB:
        AnalysisJson.model_validate_json(row["analysis_json"] or "{}")

    Write to DB:
        obj.model_dump_json(exclude_none=True)
    """

    p1: Phase1Data | None = None
    p2: Phase2Data | None = None
    p3: Phase3Data | None = None
    p4: Phase4Data | None = None

    def phases_done(self) -> list[str]:
        """Return list of completed phase keys, e.g. ['p1', 'p2']."""
        return [k for k in ("p1", "p2", "p3", "p4") if getattr(self, k) is not None]
