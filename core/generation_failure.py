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

WARNING_SIGN = "⚠️"

# The texts cv_generate / cv_cover return for a failure (after the warning sign). The tools build
# their messages from these constants and the classifier below matches the same constants, so a
# rewording is one edit in one place and cannot silently turn a code into `generation_failed`.
JD_MISSING_TEXT = "Файл JD.md не найден"
ANALYSIS_MISSING_TEXT = "JD_analysis.md не найден"
CV_MISSING_TEXT = "CV не найден в папке вакансии"
LLM_ERROR_TEXT = "Ошибка Claude"
_TAG = re.compile(r"<[^>]+>")


def soft_failure_reason(result: object) -> str | None:
    """The reason text when a tool's return value reports a failure, else None."""
    if not isinstance(result, str) or not result.startswith(WARNING_SIGN):
        return None
    text = _TAG.sub("", result[len(WARNING_SIGN):])
    return re.sub(r"\s+", " ", text).strip() or "generation failed"


def exception_reason(exc: BaseException) -> str:
    """str(exc), or the exception class name when it has no message (e.g. a timeout)."""
    return str(exc).strip() or type(exc).__name__


# ── Failure codes (core/failure_codes.py) ─────────────────────────────────────

# The tools' returned warning texts (the constants above) -> code. A message with no entry here,
# such as "vacancy not found" (the row does not exist, so there is nothing to mark), is
# `generation_failed`.
_SOFT_FAILURE_CODES = (
    (ANALYSIS_MISSING_TEXT, failure_codes.ANALYSIS_MISSING),
    (JD_MISSING_TEXT, failure_codes.JD_MISSING),
    (CV_MISSING_TEXT, failure_codes.CV_MISSING),
    (LLM_ERROR_TEXT, failure_codes.LLM_ERROR),
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
    code = failure_codes.normalize(getattr(exc, "code", None))
    if code != failure_codes.UNKNOWN:
        return code
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return failure_codes.LLM_TIMEOUT
    if isinstance(exc, LLMError):
        return failure_codes.LLM_TIMEOUT if "timed out" in str(exc) else failure_codes.LLM_ERROR
    return failure_codes.GENERATION_FAILED


# The CV language as the worker holds it (the name) -> the code the API accepts and the client sends
# back on a retry. A test keeps this the exact inverse of web.api._LANGUAGE_MAP.
LANGUAGE_CODES = {"English": "en", "Ukrainian": "uk", "both": "both", "auto": "auto"}


def language_code(language: str | None) -> str | None:
    """The API code for a CV language name, or None when it is not a known name."""
    return LANGUAGE_CODES.get(language) if language else None


def analysis_failure_code(source: BaseException | None) -> str:
    """The failure code for an analysis run that raised, or that returned a warning text (a SoftFailure).

    A timeout or a model error keeps its specific code; a missing JD file keeps `jd_missing`; anything
    the vocabulary has no better word for is `analysis_failed`.
    """
    if source is None:
        return failure_codes.ANALYSIS_FAILED
    code = failure_codes.normalize(getattr(source, "code", None))
    if code not in (failure_codes.UNKNOWN, failure_codes.GENERATION_FAILED):
        return code
    if isinstance(source, (TimeoutError, asyncio.TimeoutError)):
        return failure_codes.LLM_TIMEOUT
    if isinstance(source, LLMError):
        return failure_codes.LLM_TIMEOUT if "timed out" in str(source) else failure_codes.LLM_ERROR
    return failure_codes.ANALYSIS_FAILED
