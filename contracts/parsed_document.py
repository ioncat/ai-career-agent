"""
contracts/parsed_document.py — shared contract for jd-parser /parse response.

Mirrors the ParsedDocument model in services/parser/app.py.
Both sides must stay in sync — if parser response changes, update here.
"""

from pydantic import BaseModel, HttpUrl


class ParsedDocument(BaseModel):
    """Clean-parsed job description returned by jd-parser POST /parse."""

    title: str
    markdown: str
    source_url: str
    company: str | None = None  # employer name — extracted by parser, None if unavailable
    company_profile_url: str | None = None  # separate company profile page — see fetch_company_website()

    @property
    def is_empty(self) -> bool:
        return not self.markdown.strip()
