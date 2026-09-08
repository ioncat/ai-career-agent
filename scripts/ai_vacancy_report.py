"""
scripts/ai_vacancy_report.py — deterministic corpus filter + keyword-frequency
scan for the AI-related Product vacancy market report (recurring analysis,
see research/ai-product-vacancy-market-analysis-methodology.md).

Two-phase job, both phases live here:
1. Filter: select vacancies whose title OR JD body signals AI/ML as central
   to the product/role, not an incidental "we use AI tools internally"
   mention.
2. Count: for the filtered corpus, count how many vacancies mention each
   term in a predefined dictionary (technologies / skills / requirements /
   tools) — vacancy-level presence, not raw occurrence count, so one JD
   repeating a term ten times doesn't outweigh ten JDs mentioning it once.

Output is raw structured data (JSON) — no narrative synthesis. The LLM
open-coding pass (methodology doc, step 2) reads this JSON plus the filtered
JD.md files directly and writes the actual dated report.

Read-only — never writes to the DB or to vacancy files.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "agent.db"

# ── Inclusion filter ──────────────────────────────────────────────────────

# Title match is a strong, standalone signal — any hit here includes the
# vacancy with no further check (mirrors _TITLE_DOMAIN_DENYLIST's "title
# names it directly, don't second-guess" precedent in tools/cv_prefilter.py).
_TITLE_AI_RE = re.compile(
    r"\bAI\b|\bML\b|\bLLM\b|artificial intelligence|machine learning|"
    r"generative ai|genai|\bgpt\b",
    re.IGNORECASE,
)

# Body match needs a second signal (repetition or a Requirements-shaped
# section) before counting — a single incidental "our AI-powered platform"
# company-blurb mention must not qualify a vacancy whose actual role has
# nothing to do with AI. Same false-positive-guard principle as the mobile
# domain check in tools/cv_prefilter.py, applied generically instead of to
# one fixed phrase pattern.
_BODY_AI_RE = re.compile(
    r"\bAI\b|\bML\b|\bLLM\b|artificial intelligence|machine learning|"
    r"generative ai|genai|\bgpt\b|neural network|deep learning|"
    r"large language model",
    re.IGNORECASE,
)

_REQUIREMENTS_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s*(?:requirements?|must.?have|what (?:you.ll need|we.re looking for)|"
    r"qualifications?|responsibilities|what you.ll do|"
    r"вимоги|необхідні? навички|необхідно|обов.язков\w*|требовани\w*|"
    r"обязанности|задачі|задачи)\s*$"
)

# Second, independent filter dimension — is this actually a Product-track
# role at all? The AI-signal check alone isn't enough: "AI Engineer" and
# "GenAI Engineer, AI Builder, Agent Associate" both matched on AI signal in
# the first run but are engineering roles, not Product Manager/Owner ones —
# found live 2026-09-08 during the open-coding spot-check (vacancies #905,
# #883). Same allowlist term set as PROFILE.md's Critical Blockers `title:`
# line / tools/cv_prefilter.py's _TITLE_ALLOWLIST, duplicated here rather
# than imported to keep this script standalone (no pydantic_ai/AgentDeps
# dependency) — same rationale as that module's own hardcoded
# _CANDIDATE_ENGLISH_LEVEL constant.
_TITLE_PRODUCT_TRACK_RE = re.compile(
    r"product manager|product owner|project manager|delivery manager|"
    r"program manager|business analyst|operations manager|"
    r"technical product manager|technical project manager",
    re.IGNORECASE,
)


def _is_product_track(title: str) -> bool:
    return bool(_TITLE_PRODUCT_TRACK_RE.search(title or ""))


def _is_ai_related(title: str, jd_text: str) -> str | None:
    """Return 'title' or 'body' if the vacancy qualifies, else None.

    Caller must ALSO check _is_product_track() separately — this function
    only judges the AI signal, not whether the role is Product-track at all.
    """
    if _TITLE_AI_RE.search(title or ""):
        return "title"
    matches = list(_BODY_AI_RE.finditer(jd_text))
    if len(matches) >= 2:
        return "body"
    if len(matches) == 1 and _REQUIREMENTS_HEADING_RE.search(jd_text):
        # one mention is enough if the JD has ANY requirements-shaped
        # section at all — cheap proxy for "structured JD", cuts down on
        # missing single-mention-but-genuine roles without reopening the
        # door to a lone company-blurb mention in an unstructured posting.
        return "body"
    return None


# ── Frequency dictionary ──────────────────────────────────────────────────
# Vacancy-level presence per term: does this JD mention it at all (not how
# many times). Each entry: canonical label -> regex. Grouped into the 4
# report categories. Not exhaustive by design — the LLM open-coding pass
# (methodology doc step 2) is expected to surface terms missing here; add
# them back into this dictionary over time so later runs catch them for free.

TECHNOLOGIES: dict[str, str] = {
    "OpenAI / GPT / ChatGPT": r"\bopenai\b|\bchatgpt\b|\bgpt-?\d\b|\bgpt\b",
    "Anthropic / Claude": r"\banthropic\b|\bclaude\b",
    "Google Gemini / PaLM / Vertex AI": r"\bgemini\b|\bpalm\b|vertex ai",
    "Llama / Meta AI": r"\bllama\b|meta ai",
    "Mistral": r"\bmistral\b",
    "Cohere": r"\bcohere\b",
    "Azure OpenAI": r"azure openai",
    "AWS Bedrock": r"\bbedrock\b",
    "Hugging Face": r"hugging ?face",
    "RAG / retrieval-augmented generation": r"\brag\b|retrieval.augmented",
    "Fine-tuning": r"fine.?tun",
    "Embeddings": r"\bembedding",
    "Vector database": r"vector (?:db|database)|\bpinecone\b|\bweaviate\b|\bchroma\b|\bpgvector\b|\bqdrant\b",
    "Prompt engineering": r"prompt engineer|prompt design|prompt architect",
    "Agents / agentic workflows": r"\bagentic\b|ai agents?\b|autonomous agents?",
    "MCP (Model Context Protocol)": r"\bmcp\b|model context protocol",
    # Split from the old combined "LangChain / LlamaIndex" entry (2026-09-08,
    # user request for named-framework granularity) — each is a distinct,
    # separately-adoptable tool, worth tracking on its own.
    "LangChain": r"langchain",
    "LlamaIndex": r"llamaindex",
    # No-code/low-code AI-agent-building tools — a distinct product category
    # from the code-first frameworks above, and one a Product-track (not
    # engineering) role is more likely to actually touch hands-on. Added
    # 2026-09-08 per explicit user request (named examples: LangChain,
    # CrewAI, Langflow, Figma AI).
    "CrewAI": r"crewai",
    "Langflow": r"langflow",
    "Flowise": r"\bflowise\b",
    "AutoGen": r"\bautogen\b",
    "LangGraph": r"langgraph",
    "Semantic Kernel": r"semantic kernel",
    "Haystack": r"\bhaystack\b",
    # Not a framework — a specific AI *feature* inside an existing,
    # widely-used design tool. Tracked separately from bare "Figma" (already
    # in the Tools category) so the two can be compared: how often is the
    # base tool named vs. its AI-specific capability.
    "Figma AI": r"figma ai",
    "NLP": r"\bnlp\b|natural language processing",
    # "cv" as a bare abbreviation is excluded entirely — "send us your CV" /
    # "attach your CV" is far more common in job postings than "computer
    # vision" ever is, and there's no reliable way to tell them apart by
    # regex alone. Found live on the first run: 37 false-positive "computer
    # vision" hits, all resume mentions.
    "Computer vision": r"computer vision",
    "Speech / voice AI": r"speech recognition|voice ai|text.to.speech|speech.to.text",
    "Transformer models": r"\btransformer\b",
    "Diffusion models": r"diffusion model",
    "MLOps": r"\bmlops\b",
}

SKILLS: dict[str, str] = {
    "Prompt engineering (as a skill)": r"prompt engineer|prompt design",
    "Model evaluation / benchmarking": r"model evaluation|benchmark\w* model|eval\w* (?:the )?model|llm eval",
    "Dataset curation / labeling": r"dataset curation|data labeling|data annotation|labeled dataset|training data",
    "AI product strategy": r"ai (?:product )?strategy|ai roadmap|ai vision",
    "Responsible AI / AI ethics / safety": r"responsible ai|ai ethics|ai safety|ai governance|bias (?:in|and) ai",
    "Data literacy (SQL/Python)": r"\bsql\b|\bpython\b(?!\s*package)",
    "A/B testing for AI features": r"a\/?b test",
    "Human-in-the-loop design": r"human.in.the.loop|human in the loop",
    "Hallucination mitigation": r"hallucinat",
    "AI UX / interaction design": r"ai ux|ai interaction design|conversational (?:ui|design)",
    # Distinct from "Prompt engineering (as a skill)" — this is the lighter,
    # far more common ask: use Claude/ChatGPT/Gemini etc. day-to-day to speed
    # up your own work, not build AI features. Found live 2026-09-08 during
    # the open-coding spot-check (vacancy #203, Operations Manager — "Досвід
    # використання ШІ-інструментів для оптимізації операційних процесів...
    # (Claude, ChatGPT, Google Gemini, Notion AI)").
    "AI tool fluency (operational use, not building AI)": r"ai.?(?:powered|driven)? tools?|"
    r"ai.instruments?|ші.інструмент|ai.assisted (?:work|workflow)",
}

REQUIREMENTS: dict[str, str] = {
    "Shipped AI feature(s) to production": r"shipped? (?:an? )?ai|ai (?:feature|product)s? (?:to|into) production|"
    r"launched ai|deployed ai|production ai",
    "Commercial/technical background (CS/eng degree)": r"computer science degree|engineering degree|"
    r"technical background|cs degree",
    "Senior/Lead level required": r"\bsenior\b|\blead\b(?!ership)",
    "X+ years AI/ML experience": r"\d+\+?\s*years?[^.\n]{0,40}(?:ai|ml|machine learning)",
    "PhD / advanced degree": r"\bphd\b|ph\.d\.|master.?s degree",
    # "AI-native" as a positioning/identity term (company or role calling
    # itself this), distinct from any specific technology or requirement —
    # found live 2026-09-08 as a recurring title pattern (#1324 "AI-Native
    # Product Manager", #692's JD body "AI-native рішень").
    "AI-native positioning (title/company)": r"ai.native",
}

TOOLS: dict[str, str] = {
    "LangSmith": r"langsmith",
    "Weights & Biases": r"weights\s*&?\s*biases|\bwandb\b",
    "MLflow": r"mlflow",
    "GitHub Copilot / AI coding assistants": r"copilot|cursor\.?sh|cursor ai",
    "n8n / Zapier / Make (automation)": r"\bn8n\b|\bzapier\b|\bmake\.com\b",
    "Notion AI": r"notion ai",
    "Jira / Confluence (generic PM)": r"\bjira\b|\bconfluence\b",
    "Figma": r"\bfigma\b",
    "Amplitude / Mixpanel (analytics)": r"\bamplitude\b|\bmixpanel\b",
}

CATEGORIES: dict[str, dict[str, str]] = {
    "technologies": TECHNOLOGIES,
    "skills": SKILLS,
    "requirements": REQUIREMENTS,
    "tools": TOOLS,
}


def _compile(cat: dict[str, str]) -> dict[str, re.Pattern]:
    return {label: re.compile(pattern, re.IGNORECASE) for label, pattern in cat.items()}


_COMPILED_CATEGORIES = {name: _compile(cat) for name, cat in CATEGORIES.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH), help="Path to agent.db")
    parser.add_argument("--out", default=None, help="Output JSON path (default: scratch file next to this script)")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, company, site, markdown_path FROM vacancies "
        "WHERE markdown_path IS NOT NULL AND markdown_path != ''"
    ).fetchall()

    corpus: list[dict] = []
    freq: dict[str, dict[str, int]] = {name: {label: 0 for label in cat} for name, cat in CATEGORIES.items()}
    scanned = 0
    missing_files = 0
    not_product_track = 0

    for row in rows:
        jd_path = Path(row["markdown_path"])
        if not jd_path.exists():
            missing_files += 1
            continue
        scanned += 1
        jd_text = jd_path.read_text(encoding="utf-8", errors="replace")

        if not _is_product_track(row["title"] or ""):
            not_product_track += 1
            continue
        match_reason = _is_ai_related(row["title"] or "", jd_text)
        if not match_reason:
            continue

        matched_terms: dict[str, list[str]] = {name: [] for name in CATEGORIES}
        for cat_name, compiled in _COMPILED_CATEGORIES.items():
            for label, pat in compiled.items():
                if pat.search(jd_text):
                    freq[cat_name][label] += 1
                    matched_terms[cat_name].append(label)

        corpus.append(
            {
                "id": row["id"],
                "title": row["title"],
                "company": row["company"],
                "site": row["site"],
                "jd_path": str(jd_path),
                "match_reason": match_reason,
                "matched_terms": matched_terms,
            }
        )

    result = {
        "total_vacancies_in_db": len(rows),
        "vacancies_scanned": scanned,
        "vacancies_missing_jd_file": missing_files,
        "vacancies_not_product_track": not_product_track,
        "ai_related_corpus_size": len(corpus),
        "term_frequency": freq,
        "corpus": corpus,
    }

    research_dir = Path(__file__).resolve().parent.parent / "research"
    out_path = Path(args.out) if args.out else research_dir / "ai_vacancy_report_raw.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    out_path.write_text(payload, encoding="utf-8")

    # Dated snapshot alongside the overwritten working copy above — the
    # working copy is for THIS run's open-coding pass, this one is what a
    # future trend feature (see research/*-methodology.md) would read back;
    # without it, historical numbers only survive as markdown table text in
    # the dated report, not as parseable JSON. Added 2026-09-08.
    today = datetime.date.today().isoformat()
    dated_path = research_dir / f"ai_vacancy_report_raw_{today}.json"
    dated_path.write_text(payload, encoding="utf-8")

    print(f"Scanned: {scanned}/{len(rows)} (missing JD.md: {missing_files})")
    print(f"Not Product-track title (excluded): {not_product_track}")
    print(f"AI-related corpus: {len(corpus)}")
    print(f"Dated snapshot: {dated_path}")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
