"""
adapters/cv_adapter.py — CVAdapter: HTTP client for services/pdf/.

Replaces the previous subprocess wrapper for callback-cv/cv_to_pdf.py.
Sends markdown text to the pdf-service POST /render endpoint and
writes returned PDF bytes to disk.

Usage:
    adapter = CVAdapter(pdf_service_url="http://localhost:8002")
    pdf_path = await adapter.generate_pdf(Path("vacancies/1/job/Name_CV.md"))
"""

import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0  # seconds — PDF rendering can be slow for large CVs

PDF_MAGIC = b"%PDF-"
# A one-page PDF with fonts is tens of kilobytes; anything this small is a header with
# no document in it (a broken or empty render that still came back as HTTP 200).
MIN_PDF_BYTES = 256


class CVAdapterError(Exception):
    """Raised when the pdf-service returns an error or is unreachable."""


def validate_pdf_bytes(content: bytes) -> None:
    """Raise CVAdapterError unless `content` looks like a real rendered PDF.

    HTTP 200 alone proves nothing: the check is the `%PDF-` header and a minimum size.
    Shared by the adapter and the on-demand PDF endpoints, so "rendered" means the same
    thing everywhere.
    """
    if not content.startswith(PDF_MAGIC):
        raise CVAdapterError("pdf-service returned a response that is not a PDF")
    if len(content) < MIN_PDF_BYTES:
        raise CVAdapterError(f"pdf-service returned a PDF of only {len(content)} bytes (empty render)")


class CVAdapter:
    """Async HTTP client for the career-agent PDF render service.

    Args:
        pdf_service_url: Base URL of the pdf-service (default: http://localhost:8002).
    """

    def __init__(self, pdf_service_url: str = "http://localhost:8002") -> None:
        self._url = pdf_service_url.rstrip("/")

    async def generate_pdf(self, md_path: Path, pdf_path: Path | None = None) -> Path:
        """Generate PDF from a CV markdown file via the pdf-service.

        Reads markdown from md_path, POSTs to /render, writes response
        bytes to pdf_path.

        Args:
            md_path:  Path to the input CV markdown file.
            pdf_path: Output PDF path. Defaults to md_path with .pdf extension.

        Returns:
            Path to the generated PDF file.

        Raises:
            CVAdapterError: Service returned an error, is unreachable, returned
                something that is not a valid PDF, or the file could not be written.
            FileNotFoundError: md_path does not exist.
        """
        md_path = Path(md_path)
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {md_path}")

        if pdf_path is None:
            pdf_path = md_path.with_suffix(".pdf")

        markdown_text = md_path.read_text(encoding="utf-8")
        render_url = f"{self._url}/render"
        log.info("CVAdapter: POST %s → %s", render_url, pdf_path)

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    render_url,
                    json={"markdown": markdown_text},
                )
        except httpx.ConnectError as exc:
            raise CVAdapterError(
                f"pdf-service unreachable at {self._url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise CVAdapterError(
                f"pdf-service timed out after {_DEFAULT_TIMEOUT}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise CVAdapterError(f"HTTP error calling pdf-service: {exc}") from exc

        if response.status_code != 200:
            body = response.text[:300]
            raise CVAdapterError(
                f"pdf-service returned {response.status_code}: {body}"
            )

        validate_pdf_bytes(response.content)

        pdf_path = Path(pdf_path)
        try:
            pdf_path.write_bytes(response.content)
        except OSError as exc:
            raise CVAdapterError(f"could not write the PDF to {pdf_path}: {exc}") from exc
        log.info("CVAdapter: PDF written → %s (%d bytes)", pdf_path, len(response.content))
        return pdf_path
