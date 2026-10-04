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
    # Display name for CV header + file naming, from PROFILE.md "Name variants".
    # Empty when the profile has no such section (caller falls back to users.name).
    name_en: str = ""
    name_uk: str = ""

    def name_for(self, language: str) -> str:
        """Name to use on a CV in `language`; Ukrainian falls back to the English one."""
        if language.lower() == "ukrainian":
            return self.name_uk or self.name_en
        return self.name_en

    def phase1_context(self) -> str:
        """Compact JSON for Phase 1 injection — domain signals only, ~10 tokens."""
        return json.dumps(
            {
                "domain_interests": self.domain_interests,
                "company_stage_prefs": self.company_stage_prefs,
            },
            ensure_ascii=False,
        )
