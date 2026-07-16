#!/usr/bin/env python3
"""
scripts/set_provider.py — dev override for the LLM provider (single source of truth).

PURPOSE
-------
Writes through core.config_store so the DB stays the one true record — never
hand-edit user_settings.llm_provider directly, that bypasses validation and
the seeding contract.

USAGE
-----
    python scripts/set_provider.py claude_api
    python scripts/set_provider.py claude_cli
    python scripts/set_provider.py ollama_api
    python scripts/set_provider.py --show          # print current config, no change
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import config_store  # noqa: E402
from db import database  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Set or show the active LLM provider.")
    parser.add_argument("provider", nargs="?", choices=sorted(config_store.VALID_PROVIDERS))
    parser.add_argument("--show", action="store_true", help="print current config and exit")
    args = parser.parse_args()

    database.configure(Path("db/agent.db"))
    await database.init_db()

    if args.show or not args.provider:
        cfg = await config_store.get_config()
        print(f"provider = {cfg['provider']}")
        print(f"model    = {config_store.effective_model(cfg['provider'], cfg['model'])}"
              f"{' (DB override)' if cfg['model'] else ' (env default)'}")
        print(f"effort   = {cfg['thinking_effort']}")
        return

    cfg = await config_store.set_config(provider=args.provider)
    print(f"provider set -> {cfg['provider']} (model reset to provider default)")


if __name__ == "__main__":
    asyncio.run(main())
