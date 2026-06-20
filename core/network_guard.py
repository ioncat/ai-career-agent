"""
core/network_guard.py — Block outbound HTTP calls unless ALLOW_EXTERNAL_CALLS=true.

Set ALLOW_EXTERNAL_CALLS=true in .env to permit outbound HTTP to external services.
Default: false — any call to guard_external() raises ExternalCallBlocked.

Localhost services (Ollama at localhost:11434, jd-parser, pdf-service) never call
this guard — they are always local. Only non-localhost API calls use it.
"""

import os


class ExternalCallBlocked(RuntimeError):
    """Raised when outbound HTTP is attempted and ALLOW_EXTERNAL_CALLS is not true."""


def guard_external(label: str = "") -> None:
    """Raise ExternalCallBlocked if ALLOW_EXTERNAL_CALLS != 'true'.

    Call this before any outbound HTTP request to a non-localhost service.

    Args:
        label: Short description of the call for the error message (e.g. "Claude API").
    """
    if os.getenv("ALLOW_EXTERNAL_CALLS", "false").strip().lower() == "true":
        return
    detail = f" ({label})" if label else ""
    raise ExternalCallBlocked(
        f"External HTTP call blocked{detail}. "
        "Set ALLOW_EXTERNAL_CALLS=true in .env to permit outbound requests."
    )
