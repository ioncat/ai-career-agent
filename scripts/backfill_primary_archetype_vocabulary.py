"""
scripts/backfill_primary_archetype_vocabulary.py — one-off backfill for the
2026-09-21 primary_archetype closed-vocabulary tightening.

phase1_analysis.md §1.4 was rewritten (2026-09-21 prompt audit,
prompt-audit-pm-2026-09-21.md finding 1a) so new analyses generate
`primary_archetype` as `[balance-intensity] [role-shape]` from two closed
lists, instead of an open "can combine two" list that had drifted into 81
distinct, inconsistent free-text values across 131 vacancies. This script
retrofits EXISTING vacancies to the new format — but only where it can be
done without fabricating a judgment call:

- balance-intensity is recomputed deterministically from the vacancy's own
  already-stored role_balance percentages (same rule the new prompt uses:
  highest-% axis, canonical name + "-heavy", ties broken by canonical axis
  order) — never taken from the old free-text string.
- role-shape is salvaged from the OLD primary_archetype string only when
  it contains EXACTLY ONE of the 7 canonical role-shape terms as a
  substring. Zero matches (a genuinely different vocabulary, e.g. "Backend/
  Integration Owner") or 2+ matches (a combined label, e.g. "Platform/
  Systems PM / Delivery-coordinator" — which one was actually primary is a
  judgment call the original free text never disambiguated) are SKIPPED,
  not guessed at.

Read-only by default; pass --apply to write changes. Back up the DB
yourself before running --apply (see CLAUDE.md's DB-backup convention) —
this script does not do it for you.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

# Windows console default codepage can't display em-dashes etc. in the
# report — reconfigure to UTF-8 (same pattern as scripts/vacancy_track.py).
sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "agent.db"

# Same aliases contracts/pipeline.py normalizes on read — applied here too
# since this script reads raw JSON directly, not through the Pydantic model.
ROLE_BALANCE_ALIASES = {
    "execution": "delivery",
    "coordination": "stakeholder",
    "ops": "operational",
}

# Canonical axis order — tie-break, matches phase1_analysis.md §1.4 and the
# Flutter Role Balance Shape classifier.
AXIS_ORDER = ["strategy", "discovery", "delivery", "growth", "stakeholder", "operational"]

ROLE_SHAPES = [
    "Platform/Systems PM",
    "Feature PM",
    "Founder proxy",
    "Delivery-coordinator",
    "Operations/BizOps",
    "Technical PM",
    "Growth PM",
]


def normalize_role_balance(role_balance: dict) -> dict:
    normalized: dict = {}
    for key, val in role_balance.items():
        canonical = ROLE_BALANCE_ALIASES.get(key, key)
        if canonical in normalized:
            continue
        normalized[canonical] = val
    return normalized


def compute_intensity(role_balance: dict) -> str | None:
    """Highest-% axis, canonical name + '-heavy'. Returns None (not a guess)
    when 2+ axes are genuinely tied for the top spot — an axis-order
    tie-break would be arbitrary, not a real derivation, for exactly the
    same reason Role Balance Shape calls this case "Diffuse" rather than
    picking one. Found live: 24/87 otherwise-clean cases had a real tie
    (e.g. #625: strategy=discovery=delivery=25%) — too common to silently
    tie-break away.
    """
    rb = normalize_role_balance(role_balance)
    present = [axis for axis in AXIS_ORDER if axis in rb]
    if not present:
        return None
    max_val = max(rb[axis] for axis in present)
    tied = [axis for axis in present if rb[axis] == max_val]
    if len(tied) >= 2:
        return None
    return f"{tied[0].capitalize()}-heavy"


def tied_axes(role_balance: dict) -> list[str]:
    """The axis names tied for the top spot (len>=2), or [] if there's a clear winner."""
    rb = normalize_role_balance(role_balance)
    present = [axis for axis in AXIS_ORDER if axis in rb]
    if not present:
        return []
    max_val = max(rb[axis] for axis in present)
    tied = [axis for axis in present if rb[axis] == max_val]
    return tied if len(tied) >= 2 else []


# Substring search for an intensity term already present in the OLD free-text
# label — including the pre-2026-09-06 "execution"/"coordination"/"ops"
# vocabulary. Used only to salvage a genuine numeric tie (see
# salvage_tied_intensity) — the LLM's original phrasing may have broken a
# tie using JD nuance the bare percentages can't capture, which is a real
# signal, not a guess, as long as it's sanity-checked against the tied set.
_INTENSITY_TERMS = {
    "strategy-heavy": "strategy", "discovery-heavy": "discovery", "delivery-heavy": "delivery",
    "execution-heavy": "delivery", "growth-heavy": "growth", "stakeholder-heavy": "stakeholder",
    "coordination-heavy": "stakeholder", "operational-heavy": "operational", "ops-heavy": "operational",
}


def salvage_tied_intensity(old_archetype: str, tied: list[str]) -> str | None:
    """When role_balance is tied, try the old label's own intensity word —
    but only if exactly one intensity term appears AND it names one of the
    tied axes (otherwise the old judgment no longer agrees with the current
    numbers, or names an axis that isn't even tied — not safe to use).
    """
    found = {axis for term, axis in _INTENSITY_TERMS.items() if term in old_archetype.lower()}
    valid = [axis for axis in found if axis in tied]
    if len(found) == 1 and len(valid) == 1:
        return f"{valid[0].capitalize()}-heavy"
    return None


def find_role_shape(old_archetype: str) -> str | None:
    """Exactly one canonical role-shape substring, else None (ambiguous or absent)."""
    matches = [s for s in ROLE_SHAPES if s.lower() in old_archetype.lower()]
    return matches[0] if len(matches) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument(
        "--sample-pct", type=int, default=15,
        help="Show a random sample of this %% of changes (dry run and after --apply). Default 15.",
    )
    args = parser.parse_args()

    db = sqlite3.connect(DB_PATH)
    rows = db.execute(
        "SELECT id, analysis_json FROM vacancies WHERE analysis_json IS NOT NULL"
    ).fetchall()

    updates: list[tuple[int, str, str]] = []  # (id, old, new)
    skipped_ambiguous: list[tuple[int, str]] = []
    skipped_no_shape: list[tuple[int, str]] = []
    skipped_tied: list[tuple[int, str, dict]] = []
    skipped_no_data = 0

    for vid, aj_str in rows:
        try:
            aj = json.loads(aj_str)
        except (json.JSONDecodeError, TypeError):
            continue
        p1 = aj.get("p1") or {}
        old_archetype = p1.get("primary_archetype")
        role_balance = p1.get("role_balance")
        if not old_archetype or not role_balance or not isinstance(role_balance, dict):
            skipped_no_data += 1
            continue

        shape = find_role_shape(old_archetype)
        if shape is None:
            matches = [s for s in ROLE_SHAPES if s.lower() in old_archetype.lower()]
            if len(matches) >= 2:
                skipped_ambiguous.append((vid, old_archetype))
            else:
                skipped_no_shape.append((vid, old_archetype))
            continue

        intensity = compute_intensity(role_balance)
        if intensity is None:
            tied = tied_axes(role_balance)
            intensity = salvage_tied_intensity(old_archetype, tied) if tied else None
            if intensity is None:
                normalized_rb = normalize_role_balance(role_balance)
                skipped_tied.append((vid, old_archetype, normalized_rb))
                continue

        new_archetype = f"{intensity} {shape}"
        if new_archetype == old_archetype:
            continue  # already in the new format, nothing to do
        updates.append((vid, old_archetype, new_archetype))

        if args.apply:
            p1["primary_archetype"] = new_archetype
            aj["p1"] = p1
            db.execute(
                "UPDATE vacancies SET analysis_json = ? WHERE id = ?",
                (json.dumps(aj, ensure_ascii=False), vid),
            )

    if args.apply:
        db.commit()

    print(f"{'Applied' if args.apply else 'Dry run'}: {len(updates)} vacancies "
          f"{'updated' if args.apply else 'would be updated'}.")
    print(f"Skipped — ambiguous (2+ role-shape terms in old value): {len(skipped_ambiguous)}")
    print(f"Skipped — no canonical role-shape term found at all: {len(skipped_no_shape)}")
    print(f"Skipped — genuine tie at the top axis (no confident intensity): {len(skipped_tied)}")
    print(f"Skipped — no usable role_balance/primary_archetype data: {skipped_no_data}")

    if updates:
        sample_size = max(1, round(len(updates) * args.sample_pct / 100))
        sample = random.sample(updates, min(sample_size, len(updates)))
        sample.sort(key=lambda t: t[0])
        print(f"\nRandom {args.sample_pct}% sample ({len(sample)} of {len(updates)}):")
        print(f"{'ID':>6}  {'OLD':<55} {'NEW'}")
        for vid, old, new in sample:
            print(f"{vid:>6}  {old:<55} {new}")

    if skipped_ambiguous:
        print(f"\nAmbiguous (needs a real decision, not guessed — full list):")
        for vid, old in skipped_ambiguous:
            print(f"  #{vid}: {old}")

    if skipped_no_shape:
        print(f"\nNo canonical role-shape term found (full list):")
        for vid, old in skipped_no_shape:
            print(f"  #{vid}: {old}")

    if skipped_tied:
        print(f"\nGenuine tie at the top axis — role-shape was findable but intensity wasn't confident (full list):")
        for vid, old, rb in skipped_tied:
            print(f"  #{vid}: {old}  role_balance={rb}")

    db.close()


if __name__ == "__main__":
    main()
