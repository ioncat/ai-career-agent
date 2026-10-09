"""core/generation_failure.py — what counts as a failed CV / cover run, and its reason text.

`tools.cv_generate` and `tools.cv_cover` signal most failures by raising (LLM error), but a
missing JD, missing analysis, missing CV file or a cover LLM error come back as a returned
string that starts with the warning sign and leaves the vacancy status untouched. A worker
that only catches exceptions logs "done" and leaves the vacancy stuck in `*_generating`.
`soft_failure_reason()` turns such a return value into a reason, so the workers treat it as
the failure it is.
"""

from __future__ import annotations

import asyncio
import re

from core import failure_codes
from core.llm_client import LLMError

_WARNING_SIGN = "⚠️"
_TAG = re.compile(r"<[^>]+>")


def soft_failure_reason(result: object) -> str | None:
    """The reason text when a tool's return value reports a failure, else None."""
    if not isinstance(result, str) or not result.startswith(_WARNING_SIGN):
        return None
    text = _TAG.sub("", result[len(_WARNING_SIGN):])
    return re.sub(r"\s+", " ", text).strip() or "generation failed"


def exception_reason(exc: BaseException) -> str:
    """str(exc), or the exception class name when it has no message (e.g. a timeout)."""
    return str(exc).strip() or type(exc).__name__


# ── Failure codes (core/failure_codes.py) ─────────────────────────────────────

# Substrings of the tools' returned warning texts -> code. First match wins; the analysis
# file is tested before the JD file because both texts end with the same phrase.
_SOFT_FAILURE_CODES = (
    ("JD_analysis.md не найден", failure_codes.ANALYSIS_MISSING),
    ("JD.md не найден", failure_codes.JD_MISSING),
    ("CV не найден", failure_codes.CV_MISSING),
    ("Ошибка Claude", failure_codes.LLM_ERROR),
)


def soft_failure_code(reason: str) -> str:
    """The code for a warning text returned by cv_generate / cv_cover."""
    if "timed out" in reason:
        return failure_codes.LLM_TIMEOUT
    for needle, code in _SOFT_FAILURE_CODES:
        if needle in reason:
            return code
    return failure_codes.GENERATION_FAILED


class SoftFailure(RuntimeError):
    """A failure the tool reported by returning a warning text instead of raising."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.code = soft_failure_code(reason)


def soft_failure(result: object) -> SoftFailure | None:
    """A SoftFailure when a tool's return value reports a failure, else None."""
    reason = soft_failure_reason(result)
    return SoftFailure(reason) if reason is not None else None


def exception_code(exc: BaseException) -> str:
    """The failure code for an exception raised during a CV / cover generation run."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in failure_codes.ALL_CODES:
        return code
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return failure_codes.LLM_TIMEOUT
    if isinstance(exc, LLMError):
        return failure_codes.LLM_TIMEOUT if "timed out" in str(exc) else failure_codes.LLM_ERROR
    return failure_codes.GENERATION_FAILED
