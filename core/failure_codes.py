"""core/failure_codes.py — the vocabulary of failure codes shown to the client.

A failure on a vacancy carries a `code` next to its human-readable `reason`. The client
picks its text, its action and its language from the code; the reason is the technical
detail (often an exception message, partly Russian from the tools). An unknown or missing
code must be shown with the generic text plus the reason, so adding a code never breaks a
client that does not know it yet.

The failure projection (core/failure_projection.py) and the places that record a failure
import the constants from here, so the API and the tests share one list.
"""

from __future__ import annotations

# Fetching the job description
FETCH_GAVE_UP = "fetch_gave_up"                # the fetch retry cap was reached (status fetch_failed)

# Analysis
ANALYSIS_FAILED = "analysis_failed"            # status analysis_failed; the reason is analysis_error

# CV / cover generation
LLM_ERROR = "llm_error"                        # the model provider returned an error
LLM_TIMEOUT = "llm_timeout"                    # the call timed out
JD_MISSING = "jd_missing"                      # JD.md is not on disk
ANALYSIS_MISSING = "analysis_missing"          # JD_analysis.md is not on disk
CV_MISSING = "cv_missing"                      # a cover was requested but there is no CV file
GENERATION_FAILED = "generation_failed"        # any other generation failure

# PDF render
PDF_SERVICE_UNREACHABLE = "pdf_service_unreachable"   # not running, connection error or timeout
PDF_SERVICE_ERROR = "pdf_service_error"               # the service answered with an error status
PDF_INVALID = "pdf_invalid"                           # HTTP 200 but not a real PDF (empty or broken)
PDF_WRITE_FAILED = "pdf_write_failed"                 # the PDF could not be saved to disk

UNKNOWN = "unknown"

ALL_CODES = (
    FETCH_GAVE_UP,
    ANALYSIS_FAILED,
    LLM_ERROR,
    LLM_TIMEOUT,
    JD_MISSING,
    ANALYSIS_MISSING,
    CV_MISSING,
    GENERATION_FAILED,
    PDF_SERVICE_UNREACHABLE,
    PDF_SERVICE_ERROR,
    PDF_INVALID,
    PDF_WRITE_FAILED,
    UNKNOWN,
)


def normalize(code: object) -> str:
    """The code if it is in the vocabulary, else UNKNOWN (also for None and old rows)."""
    return code if isinstance(code, str) and code in ALL_CODES else UNKNOWN
