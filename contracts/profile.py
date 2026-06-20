"""
contracts/profile.py — Structured candidate profile parsed from PROFILE.md.

CandidateProfile captures machine-readable fields from PROFILE.md
stored in users.profile_json and injected into Phase 1 LLM prompts.
"""

import json

from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    """Structured fields extracted from PROFILE.md.

    Stored as JSON in users.profile_json.
    Used for:
      - Phase 1: domain_interests + company_stage_prefs injected into VacScore prompt
      - Pipeline routing: skill_type, language
    """

    skill_type: str = "pm"
    language: str = "ru"
    domain_interests: list[str] = Field(default_factory=list)
    company_stage_prefs: list[str] = Field(default_factory=list)

    def phase1_context(self) -> str:
        """Compact JSON for Phase 1 injection — domain signals only, ~10 tokens."""
        return json.dumps(
            {
                "domain_interests": self.domain_interests,
                "company_stage_prefs": self.company_stage_prefs,
            },
            ensure_ascii=False,
        )
