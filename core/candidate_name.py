"""
core/candidate_name.py — which name goes on a candidate's CV.

The name belongs to the candidate, not to the process: it is read from the user's
PROFILE.md ("Name variants", parsed into CandidateProfile) and, for a profile that has
no such section, from `users.name` in the DB. Nothing is read from settings or the
environment, so a second candidate never inherits the first one's name.
"""
from __future__ import annotations

from db import database


async def resolve_candidate_name(deps, language: str) -> str:
    """Return the CV display name for `deps.user_id` in `language`.

    Raises ValueError when neither the profile nor the users table has a name,
    rather than guessing one.
    """
    profile = getattr(deps, "profile", None)
    name = profile.name_for(language) if profile is not None else ""
    if not name:
        user_row = await database.get_user_by_id(deps.user_id)
        name = (user_row["name"] if user_row else "") or ""
    name = name.strip()
    if not name:
        raise ValueError(
            f"No candidate name for user {deps.user_id}: add a 'Name variants' section "
            "to the user's PROFILE.md or set users.name"
        )
    return name
