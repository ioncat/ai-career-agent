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
import threading
import unicodedata
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)

# Containment at/above which a title+company match is a CONFIRMED duplicate
# (vacancies.duplicate_of); below it, only POSSIBLE (possible_duplicate_of).
CONFIRM_THRESHOLD = 0.80

# Text-first duplicate detection (2026-10-05): a recent same-user vacancy whose
# JD contains this much of the new one is a CONFIRMED duplicate regardless of
# title or company (the owner's real case: a Djinni and a DOU posting of one
# job, company spelled with Cyrillic lookalike letters on one side — text
# containment 0.98, name+title matching missed it). Higher than
# CONFIRM_THRESHOLD because there is no title+company evidence backing it.
TEXT_CONFIRM_THRESHOLD = 0.90
# Only vacancies created/published within this many days (before the vacancy
# being classified) are scanned by text — keeps the scan bounded and avoids
# matching a years-old posting that merely shares boilerplate.
TEXT_SCAN_WINDOW_DAYS = 120

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


# ── Text-first scan: hashed shingles + per-process cache ──────────────────────
#
# The text-first scan compares a new JD against every same-user vacancy in the
# recent window (~1600 files on the live DB). Tuple shingles would cost a few
# hundred MB to keep around, so the scan uses hash(tuple) ints instead
# (64-bit, collisions negligible) and caches each file's shingle set for the
# life of the process, keyed by path and invalidated by (mtime_ns, size).

_CACHE_MAX_ENTRIES = 6000
_shingle_cache: dict[str, tuple[tuple[int, int], frozenset[int]]] = {}
_cache_lock = threading.Lock()
cache_stats = {"hits": 0, "misses": 0}


def clear_shingle_cache() -> None:
    with _cache_lock:
        _shingle_cache.clear()
        cache_stats["hits"] = 0
        cache_stats["misses"] = 0


def jd_shingle_hashes(text: str) -> frozenset[int]:
    """Same shingles as jd_shingles(), as hashed ints (in-process use only)."""
    return frozenset(hash(s) for s in jd_shingles(text))


def cached_file_shingles(path: Path) -> frozenset[int] | None:
    """Hashed shingles of a JD file, read at most once per (path, mtime, size).
    Blocking (disk + CPU) — call from a worker thread. None when unreadable."""
    try:
        st = path.stat()
    except OSError:
        return None
    sig = (st.st_mtime_ns, st.st_size)
    key = str(path)
    with _cache_lock:
        hit = _shingle_cache.get(key)
        if hit is not None and hit[0] == sig:
            cache_stats["hits"] += 1
            return hit[1]
    text = _read_text_sync(path)
    if text is None:
        return None
    sh = jd_shingle_hashes(text)
    with _cache_lock:
        cache_stats["misses"] += 1
        if len(_shingle_cache) >= _CACHE_MAX_ENTRIES and key not in _shingle_cache:
            _shingle_cache.clear()
        _shingle_cache[key] = (sig, sh)
    return sh


def _score_candidates_sync(
    new_shingles: frozenset[int],
    candidates: list[tuple[int, str | None]],
    project_root: Path,
) -> dict[int, float | None]:
    out: dict[int, float | None] = {}
    for cand_id, md_path in candidates:
        path = resolve_jd_path(md_path, project_root)
        sh = cached_file_shingles(path) if path is not None else None
        out[cand_id] = None if sh is None else shingle_containment(new_shingles, sh)
    return out


async def score_candidates(
    new_text: str,
    candidates: list[tuple[int, str | None]],
    project_root: Path,
) -> dict[int, float | None]:
    """Containment of `new_text` against each candidate's JD.md, off the event
    loop. candidates: (vacancy_id, markdown_path). A candidate whose file is
    missing/unreadable maps to None."""
    new_shingles = jd_shingle_hashes(new_text)
    if not candidates:
        return {}
    return await asyncio.to_thread(_score_candidates_sync, new_shingles, candidates, project_root)


def _parse_db_datetime(value: str | None) -> datetime | None:
    """'YYYY-MM-DD HH:MM:SS' or ISO 'YYYY-MM-DDTHH:MM:SS[...]' -> aware UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_as_of(value: str | None) -> datetime:
    """Reference time for the recency window: the given DB timestamp, else now (UTC)."""
    return _parse_db_datetime(value) or datetime.now(timezone.utc)


def in_text_window(created_at: str | None, published_at: str | None,
                   as_of: datetime, days: int = TEXT_SCAN_WINDOW_DAYS) -> bool:
    """True when the candidate was created OR published within `days` before `as_of`
    (a republished old posting has a fresh published_at)."""
    cutoff = as_of - timedelta(days=days)
    for v in (created_at, published_at):
        dt = _parse_db_datetime(v)
        if dt is not None and dt >= cutoff:
            return True
    return False


# ── Company identity ──────────────────────────────────────────────────────────

def profile_key(site: str | None, profile_url: str | None) -> str | None:
    """Stable company id within one job board: "{site}:{slug}".

    A company's profile page URL is unique per company on a board, so it is a
    far better identity than the free-text company name. DOU:
    `/companies/{slug}/` -> "dou:{slug}". Anything else keeps the whole path
    the parser returned (Djinni: `/jobs/company-{slug}` ->
    "djinni:jobs/company-{slug}"). Lowercased, scheme/host/query/fragment and
    trailing slash dropped. None when either input is empty.
    """
    if not site or not profile_url or not profile_url.strip():
        return None
    raw = profile_url.strip()
    parsed = urlparse(raw if "://" in raw else "//" + raw)
    path = unquote(parsed.path).strip().strip("/").lower()
    if not path:
        return None
    m = re.match(r"(?:jobs/)?companies/([^/]+)", path)
    if m:
        path = m.group(1)
    return f"{site.strip().lower()}:{path}"


# Cyrillic letters that look like a Latin letter (lowercase, after casefold).
_LOOKALIKES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m",
    "н": "h", "о": "o", "р": "p", "с": "c", "т": "t",
    "х": "x", "у": "y", "і": "i", "ѕ": "s", "ј": "j",
    "ԁ": "d", "ԛ": "q", "ԝ": "w",
})
_LATIN_LETTER_RE = re.compile(r"[a-z]")
_CYRILLIC_LETTER_RE = re.compile(r"[Ѐ-ӿԀ-ԯ]")
_NON_WORD_RE = re.compile(r"[\W_]+")

_LEGAL_SUFFIX_TOKENS = frozenset({
    "inc", "incorporated", "llc", "ltd", "limited", "gmbh", "corp",
    "corporation", "co", "plc", "bv", "tov", "тов",
    "тзов", "ооо", "фоп",
})
# Multi-token legal forms (punctuation already turned into token breaks).
_LEGAL_SUFFIX_SEQUENCES = (("sp", "z", "o", "o"), ("s", "r", "o"), ("l", "l", "c"))


def _fold_mixed_script(token: str) -> str:
    """Fold Cyrillic lookalikes to Latin only inside a token that mixes both
    scripts — a purely Cyrillic (or purely Latin) token is left untouched."""
    if _LATIN_LETTER_RE.search(token) and _CYRILLIC_LETTER_RE.search(token):
        return token.translate(_LOOKALIKES)
    return token


def _strip_legal_forms(tokens: list[str]) -> list[str]:
    changed = True
    while changed and len(tokens) > 1:
        changed = False
        for seq in _LEGAL_SUFFIX_SEQUENCES:
            n = len(seq)
            if len(tokens) > n and tuple(tokens[-n:]) == seq:
                tokens = tokens[:-n]
                changed = True
            elif len(tokens) > n and tuple(tokens[:n]) == seq:
                tokens = tokens[n:]
                changed = True
        if len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIX_TOKENS:
            tokens = tokens[:-1]
            changed = True
        if len(tokens) > 1 and tokens[0] in _LEGAL_SUFFIX_TOKENS:
            tokens = tokens[1:]
            changed = True
    return tokens


@lru_cache(maxsize=16384)
def normalize_company_name(name: str | None) -> str:
    """Comparable form of a company name: NFKC, casefold, punctuation -> spaces,
    whitespace collapsed, legal suffixes/prefixes dropped (Inc, LLC, Ltd, GmbH,
    Sp. z o.o., TOV ...), Cyrillic lookalikes folded to Latin inside mixed-script
    tokens (a name written with Cyrillic i/p inside a Latin word folds to the
    plain Latin word). Empty string for empty input."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).casefold()
    tokens = [t for t in _NON_WORD_RE.split(s) if t]
    tokens = [_fold_mixed_script(t) for t in tokens]
    tokens = _strip_legal_forms(tokens)
    return " ".join(tokens)


def _get(row, key: str):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def row_profile_key(row) -> str | None:
    """Profile key of a vacancy-like row: an explicit `profile_key` entry wins,
    else derived from `site` + `company_profile_url`."""
    explicit = _get(row, "profile_key")
    if explicit:
        return explicit
    return profile_key(_get(row, "site"), _get(row, "company_profile_url"))


LinkGraph = dict[str, set[str]]


def build_link_graph(pairs: Iterable[tuple[str, str]]) -> LinkGraph:
    """Undirected adjacency of learned profile-key links."""
    graph: LinkGraph = {}
    for a, b in pairs:
        if not a or not b or a == b:
            continue
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph


def profile_group(key: str | None, graph: LinkGraph) -> frozenset[str]:
    """Connected group of profile keys containing `key` (BFS), key included."""
    if not key:
        return frozenset()
    seen = {key}
    queue = deque([key])
    while queue:
        cur = queue.popleft()
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return frozenset(seen)


def profile_components(graph: LinkGraph) -> dict[str, str]:
    """key -> component representative (smallest key), for bulk lookups."""
    comp: dict[str, str] = {}
    for start in sorted(graph):
        if start in comp:
            continue
        group = profile_group(start, graph)
        rep = min(group)
        for k in group:
            comp[k] = rep
    return comp


def same_company(row_a, row_b, graph: LinkGraph | None = None) -> bool:
    """Same employer? Profile groups intersect (learned cross-board identity
    included), else normalized names equal (both non-empty)."""
    graph = graph or {}
    ka, kb = row_profile_key(row_a), row_profile_key(row_b)
    if ka and kb and profile_group(ka, graph) & profile_group(kb, graph):
        return True
    na = normalize_company_name(_get(row_a, "company"))
    nb = normalize_company_name(_get(row_b, "company"))
    return bool(na) and na == nb


# ── "Applied at this company" hint ────────────────────────────────────────────

def compute_company_applied(rows, graph: LinkGraph | None = None,
                            applied_twins: dict[int, int] | None = None) -> dict[int, int]:
    """Map vacancy id -> id of the most recently applied vacancy of the SAME
    COMPANY (same_company rules), for every non-applied vacancy that has one.

    Most recent = latest applied_at, fallback (missing/equal applied_at) highest
    id. The vacancy itself and the one already reported as its `applied_twin_id`
    are skipped (the "Applied #X" badge already covers that one); a vacancy
    that is itself applied gets no entry. Same user only (NULL user_id counts
    as 1). One in-memory pass — no per-row queries.

    rows: mappings with id, user_id, applied, applied_at, company, and either
          profile_key or site + company_profile_url.
    """
    graph = graph or {}
    applied_twins = applied_twins or {}
    comp = profile_components(graph)

    def ident(r):
        k = row_profile_key(r)
        root = comp.get(k, k) if k else None
        name = normalize_company_name(_get(r, "company")) or None
        return root, name

    def user_of(r):
        u = _get(r, "user_id")
        return u if u is not None else 1

    by_root: dict[tuple, list[tuple[str, int]]] = {}
    by_name: dict[tuple, list[tuple[str, int]]] = {}
    rows = list(rows)
    for r in rows:
        if not _get(r, "applied"):
            continue
        entry = (_get(r, "applied_at") or "", r["id"])
        root, name = ident(r)
        u = user_of(r)
        if root:
            by_root.setdefault((u, root), []).append(entry)
        if name:
            by_name.setdefault((u, name), []).append(entry)

    out: dict[int, int] = {}
    for r in rows:
        if _get(r, "applied"):
            continue
        root, name = ident(r)
        u = user_of(r)
        twin = applied_twins.get(r["id"])
        cands: list[tuple[str, int]] = []
        if root:
            cands += by_root.get((u, root), [])
        if name:
            cands += by_name.get((u, name), [])
        cands = [c for c in cands if c[1] != r["id"] and c[1] != twin]
        if cands:
            out[r["id"]] = max(cands)[1]  # latest applied_at, then highest id
    return out
