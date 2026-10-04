"""The CV display name is per user: profile "Name variants", then users.name, else an error."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from contracts.profile import CandidateProfile
from core.candidate_name import resolve_candidate_name
from core.profile_loader import parse_profile_md
from tools.cv_editorial_audit import _latest_doc_path

_VARIANTS = """\
## B. Identity

### Name variants

**English CV:**
- **Jonathan Doe** — formal (use only if user explicitly requests)
- **John Doe** — informal · **DEFAULT** (use without asking)

**Ukrainian CV:**
- **Джон Доу** — standard Ukrainian

> English CV: always use the default.

---

### Certifications
"""


def test_parser_picks_the_default_english_name_and_the_ukrainian_one():
    p = parse_profile_md(_VARIANTS)
    assert p.name_en == "John Doe"
    assert p.name_uk == "Джон Доу"


def test_parser_without_the_section_leaves_names_empty():
    p = parse_profile_md("## A. Settings\nskill_type: pm\n")
    assert (p.name_en, p.name_uk) == ("", "")


def test_parser_takes_first_english_name_when_none_is_flagged_default():
    p = parse_profile_md("### Name variants\n\n**English CV:**\n- **A B** — x\n- **C D** — y\n")
    assert p.name_en == "A B"


def test_name_for_ukrainian_falls_back_to_english():
    assert CandidateProfile(name_en="John Doe").name_for("Ukrainian") == "John Doe"
    assert CandidateProfile(name_en="John Doe").name_for("English") == "John Doe"


@pytest.mark.asyncio
async def test_resolve_prefers_profile_by_language():
    deps = SimpleNamespace(user_id=1, profile=CandidateProfile(name_en="John Doe", name_uk="Джон Доу"))
    assert await resolve_candidate_name(deps, "English") == "John Doe"
    assert await resolve_candidate_name(deps, "Ukrainian") == "Джон Доу"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_users_name_when_profile_has_none():
    deps = SimpleNamespace(user_id=2, profile=CandidateProfile())
    db = AsyncMock()
    db.get_user_by_id = AsyncMock(return_value={"name": "Jane Roe"})
    with patch("core.candidate_name.database", db):
        assert await resolve_candidate_name(deps, "English") == "Jane Roe"
    db.get_user_by_id.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_resolve_does_not_hand_one_users_name_to_another():
    """Two users, one process: each gets their own name."""
    d1 = SimpleNamespace(user_id=1, profile=CandidateProfile(name_en="John Doe"))
    d2 = SimpleNamespace(user_id=2, profile=CandidateProfile(name_en="Jane Roe"))
    assert await resolve_candidate_name(d1, "English") == "John Doe"
    assert await resolve_candidate_name(d2, "English") == "Jane Roe"


@pytest.mark.asyncio
async def test_resolve_raises_instead_of_guessing():
    deps = SimpleNamespace(user_id=3, profile=None)
    db = AsyncMock()
    db.get_user_by_id = AsyncMock(return_value=None)
    with patch("core.candidate_name.database", db), pytest.raises(ValueError, match="No candidate name for user 3"):
        await resolve_candidate_name(deps, "English")


def test_latest_doc_path_finds_highest_version_for_any_name_prefix(tmp_path):
    for n in ("John_Doe_CV.md", "John_Doe_CV_v2.md", "John_Doe_CV_v10.md", "John_Doe_Cover.md", "notes_CVx.md"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    assert _latest_doc_path(tmp_path, "CV").name == "John_Doe_CV_v10.md"
    assert _latest_doc_path(tmp_path, "Cover").name == "John_Doe_Cover.md"
    assert _latest_doc_path(tmp_path / "missing", "CV") is None
