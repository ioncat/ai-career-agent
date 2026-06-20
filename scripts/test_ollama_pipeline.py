"""
scripts/test_ollama_pipeline.py — test Phase 1+2 via Ollama on an existing vacancy.

Saves output to <vacancy_folder>/ollama/ — never overwrites production files.

Usage:
    python scripts/test_ollama_pipeline.py --id 120 --phase 1
    python scripts/test_ollama_pipeline.py --id 120 --phase 2
    python scripts/test_ollama_pipeline.py --id 120           # both phases (default)
"""

import asyncio
import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("test_ollama")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


async def run(vacancy_id: int, phase: int) -> None:
    from dotenv import load_dotenv
    load_dotenv()

    from core.settings import load_settings
    from core.llm_client import OllamaProvider, ClaudeProvider
    from adapters.parser_adapter import ParserAdapter
    from db import database

    settings = load_settings()
    database.configure(settings.db_path)

    # ── Load vacancy from DB ──────────────────────────────────────────────────
    vacancy = await database.get_vacancy_by_id(vacancy_id)
    if not vacancy:
        log.error("Vacancy #%d not found", vacancy_id)
        return

    url = vacancy["url"]
    title = vacancy["title"] or "Unknown"
    log.info("Vacancy #%d: %s", vacancy_id, title)
    log.info("URL: %s", url)

    # ── Determine output folder ───────────────────────────────────────────────
    markdown_path = vacancy["markdown_path"]
    if markdown_path:
        vacancy_folder = Path(markdown_path).parent
    else:
        log.error("No markdown_path in DB for vacancy #%d", vacancy_id)
        return

    ollama_folder = vacancy_folder / "ollama"
    ollama_folder.mkdir(exist_ok=True)
    log.info("Output folder: %s (provider determined after settings load)", ollama_folder)

    # ── Fetch JD (always needed) ──────────────────────────────────────────────
    jd_file = ollama_folder / "JD.md"
    if jd_file.exists():
        log.info("JD.md already exists in ollama/ — skipping fetch")
        jd_text = jd_file.read_text(encoding="utf-8")
    else:
        log.info("Fetching JD from parser: %s", url)
        adapter = ParserAdapter(base_url=settings.parser_url)
        doc = await adapter.fetch_markdown(url)
        jd_text = doc.markdown
        jd_file.write_text(jd_text, encoding="utf-8")
        log.info("JD.md written (%d chars)", len(jd_text))

    # ── Load prompts ──────────────────────────────────────────────────────────
    skill_type = settings.default_skill_type
    skill_dir = _PROMPTS_DIR / skill_type
    phase1_prompt = (skill_dir / "phase1_analysis.md").read_text(encoding="utf-8")
    phase2_prompt = (skill_dir / "phase2_fit.md").read_text(encoding="utf-8")

    # ── Build LLM provider ────────────────────────────────────────────────────
    from tools.cv_onboard import get_profile_for_llm
    profile_md = await get_profile_for_llm(settings.telegram_chat_id)
    if "not yet created" in profile_md and settings.profile_md_path.exists():
        profile_md = settings.profile_md_path.read_text(encoding="utf-8")

    if settings.llm_provider == "claude":
        llm = ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
        )
        provider_label = f"claude/{settings.llm_model}"
        log.info("Claude: model=%s", settings.llm_model)
    else:
        llm = OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            profile_md=profile_md,
            max_tokens=settings.max_tokens,
            timeout=settings.ollama_timeout,
        )
        provider_label = settings.ollama_model.replace(":", "-").replace("/", "-")
        log.info("Ollama: model=%s base_url=%s", settings.ollama_model, settings.ollama_base_url)

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    if phase in (1, 0):
        log.info("Phase 1 start...")
        t0 = time.monotonic()
        phase1_output = await llm.complete(jd_text, system=phase1_prompt)
        elapsed = time.monotonic() - t0
        log.info("Phase 1 done — %d chars, %.1fs", len(phase1_output), elapsed)
        (ollama_folder / "phase1.md").write_text(phase1_output, encoding="utf-8")
        log.info("Saved: %s/phase1.md", ollama_folder)
        if phase == 1:
            return

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    if phase in (2, 0):
        phase1_file = ollama_folder / "phase1.md"
        if not phase1_file.exists():
            log.error("phase1.md not found — run --phase 1 first")
            return
        phase1_output = phase1_file.read_text(encoding="utf-8")
        log.info("Phase 2 start (phase1.md loaded: %d chars)...", len(phase1_output))
        t0 = time.monotonic()
        phase2_input = f"{jd_text}\n\n---\n\nPhase 1 Analysis:\n\n{phase1_output}"
        phase2_output = await llm.complete(phase2_input, system=phase2_prompt)
        elapsed = time.monotonic() - t0
        log.info("Phase 2 done — %d chars, %.1fs", len(phase2_output), elapsed)
        (ollama_folder / "phase2.md").write_text(phase2_output, encoding="utf-8")

        # ── Write combined analysis ───────────────────────────────────────────
        analysis = (
            f"# Ollama Analysis: {title}\n\n"
            f"Source: {url}\n"
            f"Model: {settings.ollama_model}\n\n"
            f"---\n\n"
            f"## Phase 2: Candidate Fit Assessment\n\n"
            f"{phase2_output}\n\n"
            f"---\n\n"
            f"## Phase 1: JD Analysis\n\n"
            f"{phase1_output}\n"
        )
        out_file = ollama_folder / "JD_analysis.md"
        out_file.write_text(analysis, encoding="utf-8")
        log.info("Saved: %s", out_file)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True, help="Vacancy DB id")
    parser.add_argument(
        "--phase", type=int, choices=[1, 2], default=0,
        help="1 = Phase 1 only, 2 = Phase 2 only (reads phase1.md), omit = both"
    )
    args = parser.parse_args()
    asyncio.run(run(args.id, args.phase))


if __name__ == "__main__":
    main()
