"""
core/deps.py — shared dependency container for PydanticAI tools.

AgentDeps is passed to every tool via RunContext[AgentDeps].
Built once in agent.py at startup, reused across all router.handle() calls.

Usage in a tool:
    from pydantic_ai import RunContext
    from core.deps import AgentDeps

    async def cv_fetch_jd(ctx: RunContext[AgentDeps], url: str) -> str:
        doc = await ctx.deps.parser_adapter.fetch_markdown(url)
        ...
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from adapters.cv_adapter import CVAdapter
from adapters.parser_adapter import ParserAdapter
from contracts.profile import CandidateProfile
from core.llm_client import ClaudeCodeProvider, ClaudeProvider, OllamaProvider


@dataclass
class AgentDeps:
    """Shared objects injected into every PydanticAI tool via RunContext.

    Attributes:
        parser_adapter: Async HTTP client for jd-parser service (URL → Markdown).
        get_llm:        Phase-aware LLM client factory (EPIC-27) — call
                        `await ctx.deps.get_llm("phase1")` to get a live provider
                        instance for that specific phase (each phase may resolve to
                        a different provider/model per core.config_store's
                        phase_llm_config overrides). Bound to a worker's
                        `_fresh_llm` method — never call the same phase name twice
                        expecting a cached client back; it builds fresh each time.
        vacancies_path: Root directory for vacancy filesystem storage.
        candidate_name: Full name used in CV filenames (e.g. "Oleksii_Bondarenko").
        cv_adapter:     Subprocess wrapper for cv_to_pdf.py in callback-cv repo.
        user_id:        DB user ID for multi-user scoping. Default=1 (single-user mode).
        skill_type:     Routes ALL pipeline phases to prompts/[skill_type]/ (e.g. 'pm', 'generic').
        profile:        Structured candidate profile parsed from PROFILE.md.
                        Provides domain_interests + company_stage_prefs for Phase 1 injection.
                        None if PROFILE.md is absent (pipeline runs with degraded personalisation).
    """
    parser_adapter: ParserAdapter
    get_llm: Callable[[str], Awaitable[ClaudeProvider | OllamaProvider | ClaudeCodeProvider]]
    vacancies_path: Path
    candidate_name: str
    cv_adapter: CVAdapter
    user_id: int = 1
    skill_type: str = "pm"
    profile: CandidateProfile | None = None
