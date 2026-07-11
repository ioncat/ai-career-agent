"""
core/cv_metrics.py — Pre-compute CV/JD metrics for Phase 3.5 self-review.

Replaces LLM-computed sections in phase3_5_review.md prompt:
  - top_n_words     → Top-15 Word Frequency table
  - scan_tools      → Tools & Technologies table
  - detect_repetition → Repeated terms list

Results injected into Phase 3.5 user message; LLM includes them verbatim
and uses them to populate review sections (🔧 / ⚠️).
"""

from __future__ import annotations

import re
from collections import Counter

# ── Stopwords ─────────────────────────────────────────────────────────────────

_STOPWORDS: frozenset[str] = frozenset(
    {
        # Articles / prepositions / conjunctions
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "into", "about", "through", "during",
        "including", "between", "against", "across", "along", "within",
        "without", "upon", "per", "via", "vs",
        # Pronouns
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
        "us", "them", "my", "your", "his", "its", "our", "their", "mine",
        "yours", "ours", "this", "that", "these", "those", "who", "which",
        "what", "whom", "whose",
        # Auxiliary verbs
        "is", "are", "was", "were", "be", "been", "being", "am",
        "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "can", "shall",
        "must", "need", "dare",
        # Common filler
        "as", "if", "so", "then", "than", "also", "just", "not", "no", "nor",
        "very", "more", "most", "any", "all", "each", "both", "such", "other",
        "how", "when", "where", "why", "while", "although", "because",
        "since", "already", "even", "only", "well", "new", "get", "one",
        "two", "three", "make", "look", "know",
        # Common JD/CV noise words — do not carry signal
        "role", "team", "company", "position", "candidate", "responsibilities",
        "work", "working", "experience", "skills", "skill", "ability",
        "abilities", "strong", "excellent", "good", "great", "best",
        "key", "able", "ensure", "support", "provide", "across", "help",
        "using", "use", "used", "within", "related", "based", "required",
        "preferred", "plus", "including", "various", "multiple", "relevant",
        "focused", "proven", "demonstrated",
    }
)

# ── Tool registry ─────────────────────────────────────────────────────────────

_TOOL_REGISTRY: dict[str, list[str]] = {
    "Analytics / tracking": [
        "Mixpanel", "Amplitude", "PostHog", "Google Analytics", "GA4",
        "Hotjar", "Heap", "FullStory", "Pendo",
    ],
    "Project / backlog": ["Jira", "Linear", "Asana", "Confluence", "Notion", "Trello"],
    "Design / prototyping": [
        "Figma", "Sketch", "Miro", "Whimsical", "Marvel", "InVision",
    ],
    "CRM platforms": [
        "Salesforce", "HubSpot", "Pipedrive", "Zoho CRM", "Intercom",
        "Freshdesk", "Zendesk",
    ],
    "A/B testing": ["Optimizely", "VWO", "LaunchDarkly", "GrowthBook", "Firebase A/B"],
    "Data / BI": ["SQL", "Tableau", "Looker", "Metabase", "Redash", "PowerBI"],
    "AI / LLM": [
        "Claude", "ChatGPT", "OpenAI API", "Anthropic API", "Vertex AI",
        "LangChain", "n8n",
    ],
    "Automation": ["Zapier", "Make", "Integromat", "n8n", "Workato"],
}


# ── Public API ────────────────────────────────────────────────────────────────


def top_n_words(text: str, n: int = 15) -> list[tuple[str, int]]:
    """Return top-N content words by frequency, excluding stopwords.

    Args:
        text: Raw text (JD or CV draft).
        n:    How many top words to return (default 15).

    Returns:
        List of (word, count) sorted descending by count.
    """
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    counts = Counter(w for w in words if w not in _STOPWORDS)
    return counts.most_common(n)


def scan_tools(jd_text: str, cv_text: str) -> list[dict[str, object]]:
    """Scan JD and CV for tools from the registry, return comparison rows.

    Args:
        jd_text: Job description text.
        cv_text: CV draft text.

    Returns:
        List of dicts with keys: tool, category, in_jd, in_cv, signal.
        signal: 'aligned' | 'missing' | 'extra'
    """
    rows: list[dict[str, object]] = []

    def _contains(haystack: str, needle: str) -> bool:
        pattern = r"\b" + re.escape(needle) + r"\b"
        return bool(re.search(pattern, haystack, re.IGNORECASE))

    for category, tools in _TOOL_REGISTRY.items():
        for tool in tools:
            in_jd = _contains(jd_text, tool)
            in_cv = _contains(cv_text, tool)
            if not in_jd and not in_cv:
                continue
            if in_jd and in_cv:
                signal = "aligned"
            elif in_jd:
                signal = "missing"
            else:
                signal = "extra"
            rows.append(
                {"tool": tool, "category": category, "in_jd": in_jd, "in_cv": in_cv, "signal": signal}
            )

    return rows


def detect_repetition(text: str, threshold: int = 3) -> list[str]:
    """Return content words appearing at or above threshold times in the CV body.

    Focuses on the body below the SUMMARY anchor when present.

    Args:
        text:      Full CV draft text.
        threshold: Minimum occurrence count (default 3).

    Returns:
        List of repeated words, sorted by frequency descending.
    """
    summary_pos = text.find("\nSUMMARY")
    body = text[summary_pos:] if summary_pos != -1 else text

    words = re.findall(r"\b[a-zA-Z]{4,}\b", body.lower())
    counts = Counter(w for w in words if w not in _STOPWORDS)
    return [word for word, count in counts.most_common() if count >= threshold]


# ── Formatters ────────────────────────────────────────────────────────────────


def format_freq_table(
    jd_freq: list[tuple[str, int]],
    cv_freq: list[tuple[str, int]],
) -> str:
    """Render two word-frequency lists as a side-by-side plain-text table.

    Flag column (per row) signals mismatch between JD rank and CV rank:
      👻 missing   — JD top-5 word absent or rank >15 in CV
      📉 weak      — JD top-10 word rank >10 in CV
      📣 overloaded — CV top-3 word not in JD top-10
    """
    jd_top5 = {w for w, _ in jd_freq[:5]}
    jd_top10 = {w for w, _ in jd_freq[:10]}
    cv_rank: dict[str, int] = {w: i for i, (w, _) in enumerate(cv_freq)}
    cv_top10 = {w for w, _ in cv_freq[:10]}

    divider = "─" * 58
    lines = [
        f"{'JD top-15':<30}{'CV top-15':<22}",
        divider,
    ]

    n_rows = max(len(jd_freq), len(cv_freq))
    for i in range(n_rows):
        jd_cell = ""
        if i < len(jd_freq):
            jd_word, jd_cnt = jd_freq[i]
            jd_cell = f"{jd_cnt:3d}  {jd_word}"

        cv_cell = ""
        if i < len(cv_freq):
            cv_word, cv_cnt = cv_freq[i]
            cv_cell = f"{cv_cnt:3d}  {cv_word}"

        # Determine flag
        flag = ""
        if i < len(jd_freq):
            jd_word = jd_freq[i][0]
            rank_in_cv = cv_rank.get(jd_word, 99)
            if jd_word in jd_top5 and rank_in_cv > 14:
                flag = "👻 missing"
            elif jd_word in jd_top10 and rank_in_cv > 9:
                flag = "📉 weak"
        if not flag and i < len(cv_freq):
            cv_word = cv_freq[i][0]
            if i < 3 and cv_word not in cv_top10.intersection(jd_top10):
                # CV word is very high rank but not in JD top-10
                if cv_word not in {w for w, _ in jd_freq[:10]}:
                    flag = "📣 overloaded"

        lines.append(f"{jd_cell:<30}{cv_cell:<22}{flag}")

    return "\n".join(lines)


def format_tools_table(rows: list[dict[str, object]]) -> str:
    """Render tool scan results as a plain-text table."""
    if not rows:
        return (
            "🛠️ Tools & Technologies\n"
            + "─" * 58
            + "\nJD names no specific tools — generic categories only"
        )

    _signal_label = {
        "aligned": "✅ aligned",
        "missing": "👻 missing",
        "extra": "📣 extra",
    }

    divider = "─" * 58
    lines = [
        "🛠️ Tools & Technologies",
        divider,
        f"{'JD requires / mentions':<28}{'CV has':<22}Signal",
        divider,
    ]
    for row in rows:
        tool = str(row["tool"])
        jd_col = tool if row["in_jd"] else "—"
        cv_col = tool if row["in_cv"] else "—"
        signal = _signal_label.get(str(row["signal"]), str(row["signal"]))
        lines.append(f"{jd_col:<28}{cv_col:<22}{signal}")

    return "\n".join(lines)
