"""
core/dedup.py — pure helpers for text-similarity-based duplicate detection (EPIC-26).

No DB access here — db/database.py wires these into the title+company
candidate scoring. Kept dependency-free so the similarity measure is trivially
unit-testable and reusable from scripts/dedup_backfill.py.

Similarity = containment of 5-word shingles: |A ∩ B| / min(|A|, |B|).
Containment (not Jaccard) because one posting is often a shortened or
extended edition of the other — a short JD fully contained in a long one is
still the same job. Exactly the measure the 2026-10-05 dedup audit used
(research/dedup-audit-2026-10-05_RU.md).

No threshold cleanly separates duplicates from non-duplicates (true duplicates
appear at 0.07, a non-duplicate at 0.64 — rewritten re-publications vs. one
company's templated roles), so callers must only ever use CONFIRM_THRESHOLD to
choose between two *tiers* of a title+company match, never to drop one.
"""

import asyncio
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Containment at/above which a title+company match is a CONFIRMED duplicate
# (vacancies.duplicate_of); below it, only POSSIBLE (possible_duplicate_of).
CONFIRM_THRESHOLD = 0.80

SHINGLE_SIZE = 5

# JD.md layout written by fetch_jd/refetch: "# Title\n\nSource: <url>\n\n---\n\n<body>".
_HEADER_DELIMITER = "\n---\n"

_WORD_RE = re.compile(r"\w+")


def normalize_jd_text(text: str) -> str:
    """Drop the `# Title` / `Source:` header (everything up to and including the
    first `\\n---\\n`), then lowercase. Text without a header is kept whole."""
    idx = text.find(_HEADER_DELIMITER)
    body = text[idx + len(_HEADER_DELIMITER):] if idx != -1 else text
    return body.lower()


def jd_shingles(text: str) -> frozenset[tuple[str, ...]]:
    """Set of 5-word shingles of a JD text (header dropped, lowercased, `\\w+` tokens)."""
    words = _WORD_RE.findall(normalize_jd_text(text))
    if len(words) < SHINGLE_SIZE:
        return frozenset()
    return frozenset(
        tuple(words[i:i + SHINGLE_SIZE]) for i in range(len(words) - SHINGLE_SIZE + 1)
    )


def shingle_containment(a: frozenset, b: frozenset) -> float:
    """|A ∩ B| / min(|A|, |B|); 0.0 when either set is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def containment(text_a: str, text_b: str) -> float:
    """Containment similarity of two JD texts (see module docstring)."""
    return shingle_containment(jd_shingles(text_a), jd_shingles(text_b))


def resolve_jd_path(markdown_path: str | None, project_root: Path) -> Path | None:
    """Resolve a vacancy's `markdown_path` to the JD.md file on disk.

    markdown_path is relative to the project root and normally ends with
    JD.md; a known bad row (#1696) points at JD_analysis.md instead — any
    other file name is replaced by the sibling JD.md in the same folder.
    """
    if not markdown_path:
        return None
    p = Path(markdown_path)
    if not p.is_absolute():
        p = project_root / p
    if p.name != "JD.md":
        p = p.with_name("JD.md")
    return p


def _read_text_sync(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("dedup: cannot read %s: %s", path, exc)
        return None


async def read_jd_text(markdown_path: str | None, project_root: Path) -> str | None:
    """Read a vacancy's JD.md off the event loop. None when missing/unreadable."""
    path = resolve_jd_path(markdown_path, project_root)
    if path is None:
        return None
    return await asyncio.to_thread(_read_text_sync, path)


# ── "Already applied" detection ───────────────────────────────────────────────

def compute_applied_twins(rows) -> dict[int, int]:
    """Map vacancy id -> id of its *applied twin*, for every non-applied vacancy
    that has one.

    A vacancy's duplicate group is the connected component of the undirected
    graph whose edges are the `duplicate_of` and `possible_duplicate_of` links
    (a link in either direction joins two rows), restricted to one user.
    Union-find makes the walk transitive and immune to cycles (the DB has
    hash-twin cycles, e.g. A.duplicate_of=B and B.duplicate_of=A).

    A vacancy has an applied twin when any *other* member of its group has
    applied = 1. With several applied members the most recent `applied_at`
    wins (missing applied_at sorts oldest); remaining ties -> lowest id.
    Applied rows themselves get no entry. Links pointing at a row that is not
    in `rows`, or at another user's row, are ignored.

    rows: iterable of mappings/sqlite rows with keys id, user_id,
          duplicate_of, possible_duplicate_of, applied, applied_at.
          user_id NULL is legacy and counts as user 1.
    One pass over the input, no I/O — safe to call per list request.
    """
    info: dict[int, tuple[int, bool, str]] = {}  # id -> (user, applied, applied_at)
    links: list[tuple[int, int]] = []
    for r in rows:
        rid = r["id"]
        user = r["user_id"] if r["user_id"] is not None else 1
        info[rid] = (user, bool(r["applied"]), r["applied_at"] or "")
        for key in ("duplicate_of", "possible_duplicate_of"):
            target = r[key]
            if target is not None:
                links.append((rid, target))

    parent = {rid: rid for rid in info}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        if b not in info or info[a][0] != info[b][0]:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    best: dict[int, tuple[str, int]] = {}  # root -> (applied_at, id) of best applied row
    for rid, (_user, applied, applied_at) in info.items():
        if not applied:
            continue
        root = find(rid)
        cur = best.get(root)
        # later applied_at wins; on a tie the lower id wins
        if cur is None or applied_at > cur[0] or (applied_at == cur[0] and rid < cur[1]):
            best[root] = (applied_at, rid)

    return {
        rid: best[find(rid)][1]
        for rid, (_u, applied, _a) in info.items()
        if not applied and find(rid) in best
    }
