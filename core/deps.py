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

from dataclasses import dataclass
from pathlib import Path

from adapters.cv_adapter import CVAdapter
from adapters.parser_adapter import ParserAdapter
from core.llm_client import ClaudeProvider, OllamaProvider


@dataclass
class AgentDeps:
    """Shared objects injected into every PydanticAI tool via RunContext.

    Attributes:
        parser_adapter: Async HTTP client for jd-parser service (URL → Markdown).
        llm:            LLM provider for completions — ClaudeProvider or OllamaProvider.
        vacancies_path: Root directory for vacancy filesystem storage.
        candidate_name: Full name used in CV filenames (e.g. "Oleksii_Bondarenko").
        cv_adapter:     Subprocess wrapper for cv_to_pdf.py in callback-cv repo.
        user_id:        DB user ID for multi-user scoping. Default=1 (single-user mode).
        skill_type:     Routes ALL pipeline phases to prompts/[skill_type]/ (e.g. 'pm', 'generic').
    """
    parser_adapter: ParserAdapter
    llm: ClaudeProvider | OllamaProvider
    vacancies_path: Path
    candidate_name: str
    cv_adapter: CVAdapter
    user_id: int = 1
    skill_type: str = "pm"
