"""
tests/test_dedup.py — EPIC-26 dedup rework (2026-10-05): text-similarity tiers.

Part 1: pure helpers in core/dedup.py (containment, path resolution).
Part 2: database.classify_duplicate / find_duplicate / find_possible_duplicate
        against a temp DB with real JD.md files in tmp_path.
"""

from pathlib import Path

import pytest
import pytest_asyncio

from core import dedup
from core.dedup import (
    CONFIRM_THRESHOLD,
    containment,
    jd_shingles,
    normalize_jd_text,
    read_jd_text,
    resolve_jd_path,
)
from db import database


# ── Helpers ───────────────────────────────────────────────────────────────────

def _words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def _jd(body: str, title: str = "Role", source: str = "https://example.org/1") -> str:
    """Full JD.md text as fetch_jd writes it (header + --- + body)."""
    return f"# {title}\n\nSource: {source}\n\n---\n\n{body}"


# ── Part 1: pure helpers ──────────────────────────────────────────────────────

def test_containment_identical_texts_is_one():
    text = _words("w", 60)
    assert containment(text, text) == 1.0


def test_containment_bilingual_superset_is_one():
    """A short JD fully contained in a longer one (extended re-publication)
    scores 1.0 — containment is relative to the SMALLER shingle set."""
    short = _words("w", 40)
    long = short + " " + _words("extra", 40)
    assert containment(short, long) == 1.0
    assert containment(long, short) == 1.0


def test_containment_disjoint_is_zero():
    assert containment(_words("a", 40), _words("b", 40)) == 0.0


def test_containment_empty_or_too_short_is_zero():
    assert containment("", _words("w", 40)) == 0.0
    assert containment(_words("w", 40), "") == 0.0
    # fewer than 5 words -> no shingles at all
    assert containment("one two three four", "one two three four") == 0.0


def test_normalize_drops_header_through_first_delimiter_and_lowercases():
    text = "# Title\n\nSource: https://x\n\n---\n\nHello World\n---\nlater rule"
    assert normalize_jd_text(text) == "\nhello world\n---\nlater rule"
    # No header delimiter -> whole text kept
    assert normalize_jd_text("Plain TEXT") == "plain text"


def test_header_does_not_influence_similarity():
    body = _words("w", 40)
    a = _jd(body, title="Alpha", source="https://a.example/1")
    b = _jd(body, title="Totally different title", source="https://b.example/2")
    assert containment(a, b) == 1.0
    assert jd_shingles(a) == jd_shingles(b)


def test_confirm_threshold_is_080():
    assert CONFIRM_THRESHOLD == 0.80


def test_resolve_jd_path_keeps_jd_md():
    root = Path("/proj")
    assert resolve_jd_path("vacancies/inbox/1/42 — X/JD.md", root) == root / "vacancies/inbox/1/42 — X/JD.md"


def test_resolve_jd_path_maps_analysis_file_to_sibling_jd_md():
    root = Path("/proj")
    p = resolve_jd_path("vacancies/inbox/1/1696 — X/JD_analysis.md", root)
    assert p == root / "vacancies/inbox/1/1696 — X/JD.md"


def test_resolve_jd_path_absolute_and_empty(tmp_path):
    abs_p = tmp_path / "a" / "JD_analysis.md"
    assert resolve_jd_path(str(abs_p), Path("/proj")) == tmp_path / "a" / "JD.md"
    assert resolve_jd_path(None, Path("/proj")) is None
    assert resolve_jd_path("", Path("/proj")) is None


@pytest.mark.asyncio
async def test_read_jd_text_missing_file_is_none(tmp_path):
    assert await read_jd_text(str(tmp_path / "nope" / "JD.md"), tmp_path) is None


@pytest.mark.asyncio
async def test_read_jd_text_reads_off_the_event_loop(tmp_path, monkeypatch):
    f = tmp_path / "JD.md"
    f.write_text("hello", encoding="utf-8")
    called_in_thread = []

    real = dedup.asyncio.to_thread

    async def spy(func, *a, **kw):
        called_in_thread.append(func.__name__)
        return await real(func, *a, **kw)

    monkeypatch.setattr(dedup.asyncio, "to_thread", spy)
    assert await read_jd_text(str(f), tmp_path) == "hello"
    assert called_in_thread == ["_read_text_sync"]


# ── Part 2: DB-backed classification ──────────────────────────────────────────

@pytest_asyncio.fixture
async def env(tmp_path):
    database.configure(tmp_path / "test.db")
    await database.init_db()
    uid = await database.insert_user("Test User")
    return {"tmp": tmp_path, "uid": uid, "n": 0}


async def _add(env, body: str | None, *, title="Product Manager", company="Acme",
               content_hash: str | None = None, md_name: str = "JD.md",
               write_file: bool = True) -> int:
    """Insert a vacancy (+ its JD.md) and return its id."""
    env["n"] += 1
    n = env["n"]
    folder = env["tmp"] / f"v{n}"
    folder.mkdir()
    md_path = folder / md_name
    if write_file and body is not None:
        (folder / "JD.md").write_text(_jd(body), encoding="utf-8")
    vid = await database.insert_vacancy(
        url=f"https://example.org/jobs/{n}", title=title, company=company,
        markdown_path=str(md_path), user_id=env["uid"],
    )
    if content_hash:
        await database.set_content_hash(vid, content_hash)
    return vid


def _norm(title="Product Manager"):
    return database._normalize_title(title, None)


async def _classify(env, new_body, *, exclude_id=None, content_hash=None,
                    title="Product Manager", company="Acme", before_id=None):
    return await database.classify_duplicate(
        env["uid"], content_hash, _norm(title), company,
        exclude_id=exclude_id,
        new_text=_jd(new_body) if new_body is not None else None,
        before_id=before_id,
    )


@pytest.mark.asyncio
async def test_migration_adds_possible_duplicate_of_column(env):
    async with database.get_db() as db:
        cur = await db.execute("PRAGMA table_info(vacancies)")
        cols = {r["name"] for r in await cur.fetchall()}
    assert "possible_duplicate_of" in cols


@pytest.mark.asyncio
async def test_best_candidate_by_similarity_beats_lowest_id(env):
    """#1453-style: the lower-id candidate shares title+company but is a
    different role; the true twin has a HIGHER id. The twin must win."""
    new_body = _words("twin", 60)
    unrelated = await _add(env, _words("other", 60))   # lowest id
    twin = await _add(env, new_body)                   # higher id, same text
    new = await _add(env, new_body)

    verdict = await _classify(env, new_body, exclude_id=new)
    assert unrelated < twin
    assert verdict.confirmed_id == twin
    assert verdict.possible_id is None
    assert verdict.containment == 1.0
    assert await database.find_duplicate(
        env["uid"], None, _norm(), "Acme", exclude_id=new, new_text=_jd(new_body)
    ) == twin


@pytest.mark.asyncio
async def test_equal_scores_tie_to_lowest_id(env):
    body = _words("same", 60)
    first = await _add(env, body)
    await _add(env, body)
    new = await _add(env, body)
    verdict = await _classify(env, body, exclude_id=new)
    assert verdict.confirmed_id == first


def _boundary_pair(common_words: int) -> tuple[str, str]:
    """(new_body, candidate_body): both 104 words / 100 shingles, sharing the
    first `common_words` words -> `common_words - 4` shared shingles."""
    base = _words("a", 104)
    cand = _words("a", common_words) + " " + _words("z", 104 - common_words)
    return base, cand


@pytest.mark.asyncio
async def test_exactly_080_is_confirmed(env):
    new_body, cand_body = _boundary_pair(84)   # 80/100 = 0.80
    cand = await _add(env, cand_body)
    verdict = await _classify(env, new_body)
    assert verdict.containment == pytest.approx(0.80)
    assert verdict.confirmed_id == cand and verdict.possible_id is None


@pytest.mark.asyncio
async def test_just_below_080_is_only_possible(env):
    new_body, cand_body = _boundary_pair(83)   # 79/100 = 0.79
    cand = await _add(env, cand_body)
    verdict = await _classify(env, new_body)
    assert verdict.containment == pytest.approx(0.79)
    assert verdict.confirmed_id is None and verdict.possible_id == cand
    # public API mirrors it
    args = (env["uid"], None, _norm(), "Acme")
    assert await database.find_duplicate(*args, new_text=_jd(new_body)) is None
    assert await database.find_possible_duplicate(*args, new_text=_jd(new_body)) == cand


@pytest.mark.asyncio
async def test_low_containment_match_is_downgraded_never_dropped(env):
    cand = await _add(env, _words("b", 60))
    verdict = await _classify(env, _words("a", 60))
    assert verdict.containment == 0.0
    assert verdict.possible_id == cand and verdict.confirmed_id is None


@pytest.mark.asyncio
async def test_unreadable_candidate_file_is_possible(env):
    cand = await _add(env, None, write_file=False)   # row exists, no JD.md on disk
    verdict = await _classify(env, _words("a", 60))
    assert verdict.possible_id == cand and verdict.confirmed_id is None
    assert verdict.containment is None


@pytest.mark.asyncio
async def test_no_new_text_makes_title_company_only_possible(env):
    cand = await _add(env, _words("a", 60))
    verdict = await _classify(env, None)
    assert verdict.possible_id == cand and verdict.confirmed_id is None
    assert await database.find_duplicate(env["uid"], None, _norm(), "Acme") is None
    assert await database.find_possible_duplicate(env["uid"], None, _norm(), "Acme") == cand


@pytest.mark.asyncio
async def test_hash_match_is_unconditional_and_wins(env):
    # Hash twin has totally different text and a different title/company…
    hash_twin = await _add(env, _words("x", 60), title="Other", company="Else", content_hash="h1")
    # …while a title+company candidate has IDENTICAL text.
    await _add(env, _words("a", 60))
    verdict = await _classify(env, _words("a", 60), content_hash="h1")
    assert verdict.confirmed_id == hash_twin
    assert verdict.reason == "hash"
    assert verdict.possible_id is None


@pytest.mark.asyncio
async def test_hash_only_call_without_title_company_stays_hash_only(env):
    """web/api.py manual import: find_duplicate(user, hash, None, None)."""
    await _add(env, _words("a", 60))   # same-ish title+company must NOT matter
    assert await database.find_duplicate(env["uid"], "nohash", None, None) is None
    twin = await _add(env, _words("q", 60), content_hash="hh")
    assert await database.find_duplicate(env["uid"], "hh", None, None) == twin
    assert await database.find_possible_duplicate(env["uid"], "hh", None, None) is None


@pytest.mark.asyncio
async def test_jd_analysis_md_path_uses_sibling_jd_md(env):
    body = _words("a", 60)
    # markdown_path points at JD_analysis.md (known bad row #1696); the sibling
    # JD.md holds the real text. A long unrelated analysis file must be ignored.
    cand = await _add(env, body, md_name="JD_analysis.md")
    (env["tmp"] / "v1" / "JD_analysis.md").write_text(_words("analysis", 500), encoding="utf-8")
    verdict = await _classify(env, body)
    assert verdict.confirmed_id == cand
    assert verdict.containment == 1.0


@pytest.mark.asyncio
async def test_exclude_id_and_before_id(env):
    body = _words("a", 60)
    old = await _add(env, body)
    me = await _add(env, body)
    newer = await _add(env, body)
    # exclude_id: the vacancy never matches itself
    assert (await _classify(env, body, exclude_id=me)).confirmed_id == old
    # before_id (backfill replay): only strictly older rows are candidates
    assert (await _classify(env, body, exclude_id=me, before_id=me)).confirmed_id == old
    assert (await _classify(env, body, exclude_id=old, before_id=old)).confirmed_id is None
    assert newer > me


@pytest.mark.asyncio
async def test_other_users_rows_are_never_candidates(env):
    other_uid = await database.insert_user("Other")
    await _add(env, _words("a", 60))
    verdict = await database.classify_duplicate(
        other_uid, None, _norm(), "Acme", new_text=_jd(_words("a", 60)))
    assert verdict.confirmed_id is None and verdict.possible_id is None


@pytest.mark.asyncio
async def test_no_candidates_means_no_verdict(env):
    verdict = await _classify(env, _words("a", 60), title="Something Else")
    assert (verdict.confirmed_id, verdict.possible_id, verdict.reason) == (None, None, "none")


@pytest.mark.asyncio
async def test_never_both_tiers_set(env):
    orig = await _add(env, _words("a", 60))
    vid = await _add(env, _words("a", 60))

    async def _tiers():
        row = await database.get_vacancy_by_id(vid)
        return row["duplicate_of"], row["possible_duplicate_of"]

    await database.set_duplicate_of(vid, orig)
    assert await _tiers() == (orig, None)
    await database.set_possible_duplicate_of(vid, orig)      # downgrade clears confirmed
    assert await _tiers() == (None, orig)
    await database.set_duplicate_of(vid, orig)               # upgrade clears possible
    assert await _tiers() == (orig, None)
    await database.clear_duplicate_flags(vid)
    assert await _tiers() == (None, None)


@pytest.mark.asyncio
async def test_before_id_restricts_hash_matches_too(env):
    """Replay semantics for backfills: a newer hash twin is not an 'original'."""
    me = await _add(env, _words("a", 60), title="Other", company="Else", content_hash="hx")
    newer_twin = await _add(env, _words("a", 60), title="Other", company="Else", content_hash="hx")
    live = await _classify(env, _words("a", 60), exclude_id=me, content_hash="hx",
                           title="Other", company="Else")
    assert live.confirmed_id == newer_twin and live.reason == "hash"
    replay = await _classify(env, _words("a", 60), exclude_id=me, content_hash="hx",
                             title="Other", company="Else", before_id=me)
    assert (replay.confirmed_id, replay.possible_id) == (None, None)


# ── Linking a duplicate must not bump updated_at ──────────────────────────────
# The Analyzed/processed folders sort by updated_at; a bulk (re-)link used to
# push every old vacancy to the top of the list.

async def _stamp_old(vid: int) -> None:
    async with database.get_db() as db:
        await db.execute("UPDATE vacancies SET updated_at = '2026-06-01 10:00:00' WHERE id = ?", (vid,))
        await db.commit()


async def _updated_at(vid: int) -> str:
    async with database.get_db() as db:
        cur = await db.execute("SELECT updated_at FROM vacancies WHERE id = ?", (vid,))
        return (await cur.fetchone())["updated_at"]


@pytest.mark.asyncio
async def test_duplicate_linking_keeps_updated_at(env):
    orig = await _add(env, _words("w", 60))
    vid = await _add(env, _words("w", 60))
    await _stamp_old(vid)

    await database.set_possible_duplicate_of(vid, orig)
    assert await _updated_at(vid) == "2026-06-01 10:00:00"

    await database.set_duplicate_of(vid, orig)
    assert await _updated_at(vid) == "2026-06-01 10:00:00"

    await database.clear_duplicate_flags(vid)
    assert await _updated_at(vid) == "2026-06-01 10:00:00"
