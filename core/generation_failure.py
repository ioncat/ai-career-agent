"""core/generation_failure.py — what counts as a failed CV / cover run, and its reason text.

`tools.cv_generate` and `tools.cv_cover` signal most failures by raising (LLM error), but a
missing JD, missing analysis, missing CV file or a cover LLM error come back as a returned
string that starts with the warning sign and leaves the vacancy status untouched. A worker
that only catches exceptions logs "done" and leaves the vacancy stuck in `*_generating`.
`soft_failure_reason()` turns such a return value into a reason, so the workers treat it as
the failure it is.
"""

from __future__ import annotations

import re

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
