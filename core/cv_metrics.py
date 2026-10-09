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

# Ukrainian + Russian counterpart of the English noise list above, used only by
# top_n_words. Function words and generic JD/CV filler, nothing that names a
# domain, tool or skill (those must stay countable).
_STOPWORDS_CYRILLIC: frozenset[str] = frozenset(
    {
        # Ukrainian: conjunctions, prepositions, pronouns, particles
        "але", "або", "щоб", "що", "які", "який", "яка", "яке", "яких", "якого",
        "якій", "цей", "ця", "цього", "цій", "цих", "той", "тих", "його", "їх",
        "їхній", "наш", "наші", "нашої", "нашій", "нашого", "ваш", "ваші",
        "для", "при", "про", "від", "під", "над", "між", "через", "після",
        "перед", "без", "щодо", "серед", "коли", "тому", "тоді", "також",
        "дуже", "лише", "тільки", "вже", "ще", "все", "всі", "всіх", "кожен",
        "кожна", "інші", "інших", "інший", "буде", "будуть", "бути", "був",
        "була", "було", "були", "має", "мають", "мати", "можна", "може",
        "можуть", "потрібно", "необхідно", "нас", "вас", "нам", "вам", "вони",
        "вона", "воно", "саме", "понад", "більше", "менше",
        # Ukrainian: generic JD/CV noise (mirrors "experience", "work", "team"...)
        "досвід", "досвіду", "досвідом", "робота", "роботи", "роботу",
        "працювати", "команда", "команди", "команді", "компанія", "компанії",
        "компанію", "вимоги", "обов'язки", "знання", "навички", "вміння",
        "вміти", "здатність", "рівень", "рівня", "сильні", "сильний",
        "відмінні", "хороші", "бажано", "вакансія", "вакансії", "кандидат",
        "кандидата", "пропонуємо", "шукаємо", "запрошуємо", "років", "роки",
        "рік", "року", "мінімум",
        # Russian: conjunctions, prepositions, pronouns, particles
        "что", "чтобы", "как", "который", "которая", "которое", "которые",
        "этот", "эта", "это", "эти", "его", "для", "при", "про", "под",
        "над", "между", "через", "после", "перед", "без", "когда", "тоже",
        "также", "очень", "только", "уже", "еще", "ещё", "все", "всех",
        "каждый", "другие", "будет", "будут", "быть", "был", "была", "было",
        "были", "есть", "имеет", "имеют", "иметь", "можно", "может", "могут",
        "нужно", "необходимо", "они", "она", "более", "менее",
        # Russian: generic JD/CV noise
        "опыт", "опыта", "работа", "работы", "работу", "команда", "команды",
        "компания", "компании", "требования", "обязанности", "знание",
        "знания", "навыки", "умение", "умения", "уровень", "сильные",
        "отличные", "хорошие", "желательно", "вакансия", "кандидат",
        "предлагаем", "ищем", "лет", "года", "год", "минимум",
    }
)

# English words stay Latin-only with a 3+ letter floor (unchanged behaviour);
# Ukrainian/Russian words may contain an apostrophe inside the word
# ("м'який"), so a plain \b-bounded run would split them.
_TOP_WORDS_RE = re.compile(
    r"\b[a-zA-Z]{3,}\b|[а-яёіїєґ]+(?:['ʼ’][а-яёіїєґ]+)*"
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
    words = [
        w.replace("ʼ", "'").replace("’", "'")
        for w in _TOP_WORDS_RE.findall(text.lower())
    ]
    counts = Counter(
        w for w in words
        if len(w) >= 3 and w not in _STOPWORDS and w not in _STOPWORDS_CYRILLIC
    )
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


def detect_phrase_repetition(
    text: str, min_n: int = 3, max_n: int = 5, threshold: int = 2
) -> list[tuple[str, int]]:
    """Return multi-word phrases (n-grams) repeated at or above threshold times.

    Complements detect_repetition (single-word frequency), which cannot catch
    verbatim phrase/construction echoes — e.g. "as part of the team" reused
    across three different roles reads as obvious duplication to a human but
    never trips a single-word count (each individual word is common, and
    "team" is itself a stopword here). Found live 2026-09-06, vacancy #1441:
    three 3+ word phrases were reused verbatim across unrelated CV sections
    and only caught by a manual ad-hoc n-gram scan after the fact.

    Args:
        text:      Full CV draft text (markdown).
        min_n:     Shortest phrase length to check, in words (default 3).
        max_n:     Longest phrase length to check, in words (default 5).
        threshold: Minimum occurrence count to report (default 2 — unlike
                   single words, a verbatim 3+ word phrase repeated even once
                   more is already worth a human look).

    Returns:
        List of (phrase, count) tuples, longest phrases first, then by count
        descending. Phrases made entirely of stopwords (e.g. "in the of") are
        skipped as grammatical noise, not a real echo. A short, uniform
        prose-then-bullet restatement of the same fact (e.g. a sentence and
        its own Key Results bullet) is a legitimate pattern, not a bug — the
        review step interprets findings, this function only surfaces them.
    """
    body = re.sub(r"\[.*?\]\(.*?\)", " ", text)  # strip markdown links first
    body = re.sub(r"[#*`]", " ", body)
    words = re.findall(r"[a-zA-Z']+", body.lower())

    results: list[tuple[str, int]] = []
    for n in range(max_n, min_n - 1, -1):
        grams = Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
        for gram, count in grams.items():
            if count < threshold:
                continue
            if all(w in _STOPWORDS for w in gram):
                continue
            results.append((" ".join(gram), count))

    results.sort(key=lambda t: (-len(t[0].split()), -t[1]))
    return results


# ── JD-echo (CV-vs-JD, not self-repetition) ────────────────────────────────────

# Words that combine into a title/role phrase (e.g. "Product Manager", "Senior
# Product Owner") and therefore legitimately overlap between CV and JD by
# design — the CV headline may legitimately echo the JD's own title term (when
# the profile's title rules say the headline follows the vacancy). Local to detect_jd_echo only — do NOT
# merge into _STOPWORDS, which other functions use for within-document
# repetition where these words carry real signal.
_ROLE_TITLE_WORDS: frozenset[str] = frozenset(
    {"product", "manager", "owner", "project", "program", "senior", "junior",
     "lead", "director", "specialist", "coordinator"}
)


def detect_jd_echo(cv_text: str, jd_text: str, min_n: int = 2, max_n: int = 6) -> list[str]:
    """Return phrases that appear in both the CV and the JD text verbatim.

    Different from detect_phrase_repetition (which checks a single document
    against itself): this compares TWO documents, and a single co-occurrence
    already counts — unlike self-repetition, echoing the employer's own
    distinctive phrasing back at them is a problem the first time, not just
    on a second occurrence. Found live 2026-09-21, vacancy #1658: an isolated
    Phase 3.8 audit caught a CV Summary opening sentence built almost
    entirely from paraphrased JD clauses, including one verbatim 2-word
    phrase ("running ceremonies") lifted from the exact JD line describing
    what the company does NOT want. min_n defaults to 2 (not 3, like
    detect_phrase_repetition) specifically so a short but distinctive
    phrase like that one isn't silently missed.

    This is a cheap, advisory pre-filter, not a judgment call — it cannot
    tell "echoed the JD's distinctive voice" apart from "used a shared,
    expected term" as reliably as a human or an isolated Phase 3.8 read
    can. It exists to catch the clear, literal cases cheaply in Phase 3.5,
    before the more expensive Phase 3.8 audit ever runs — not to replace
    3.8's own JD-Echo Risk check, which also catches paraphrased (non-
    literal) echo this n-gram scan cannot see by construction.

    Filtered out (to keep findings to genuine candidates, not routine
    professional-vocabulary overlap):
      - phrases made entirely of stopwords or role/title words (e.g. "the
        product manager", "senior product owner" — expected to match, the
        CV headline may echo the JD's own title term)
      - phrases that are a known tool/technology name (see _TOOL_REGISTRY)
        — the CV SHOULD name a tool the JD asks for; that is ATS coverage,
        the opposite problem from JD-echo
      - a shorter phrase that is already a substring of a longer phrase
        already found (report the longest match, not every nested overlap)

    Args:
        cv_text: Full CV or cover draft text (markdown).
        jd_text: The vacancy's original JD text.
        min_n:   Shortest phrase length to check, in words (default 2).
        max_n:   Longest phrase length to check, in words (default 6).

    Returns:
        List of matched phrases, longest first. Empty when clean. Advisory
        only — a hit can be a legitimate, defensible shared term a human
        dismisses on review, same treatment as detect_mechanical_violations.
    """

    def _words(text: str) -> list[str]:
        body = re.sub(r"\[.*?\]\(.*?\)", " ", text)
        body = re.sub(r"[#*`]", " ", body)
        return re.findall(r"[a-zA-Z']+", body.lower())

    cv_words = _words(cv_text)
    jd_words = _words(jd_text)

    tool_phrases = {t.lower() for tools in _TOOL_REGISTRY.values() for t in tools}
    skip_words = _STOPWORDS | _ROLE_TITLE_WORDS

    results: list[str] = []
    for n in range(max_n, min_n - 1, -1):
        jd_grams = {tuple(jd_words[i : i + n]) for i in range(len(jd_words) - n + 1)}
        cv_grams = {tuple(cv_words[i : i + n]) for i in range(len(cv_words) - n + 1)}
        for gram in jd_grams & cv_grams:
            phrase = " ".join(gram)
            # 2-word grams: a single stopword/connector riding along a real
            # word (e.g. "the platform", "blockers and") isn't a distinctive
            # echoed phrase — require BOTH words to carry content. Longer
            # grams may legitimately weave in one function word naturally
            # ("bring structure to ambiguity") — the looser "not all
            # skip words" check is enough there.
            if n == 2:
                if any(w in skip_words for w in gram):
                    continue
            elif all(w in skip_words for w in gram):
                continue
            if phrase in tool_phrases:
                continue
            if any(phrase in longer for longer in results):
                continue
            results.append(phrase)

    results.sort(key=lambda p: -len(p.split()))
    return results


# ── Mechanical rule violations ─────────────────────────────────────────────────

# Maintained banned-phrase list — each entry traces to a dated feedback rule
# that recurred despite already being stated once in a prompt file. Literal
# substrings only (case-insensitive) — advisory, not exhaustive; a phrase not
# on this list can still be a real violation a human catches on read-through.
_BANNED_PHRASES: tuple[str, ...] = (
    "AI-Native", "AI-Driven mindset",  # phase3_cv_draft.md rule 7
    "gap analysis",  # feedback_no_gap_analysis — JD-specific BA jargon, not universal
    "on time", "on schedule",  # feedback_no_on_time_claim — table-stakes, not a claim
    "вчасно", "без нагадувань", "без потреби нагадувати",  # same, UA
    "portfolio",  # feedback_no_portfolio_word_pet_projects — these are pet projects
    "active daily practice, not a side project",  # same memory, banned line
    "account management",  # feedback_no_account_management_wording
    "what's already working well", "what's going fine", "what's on track",  # feedback_no_whats_working_well
    "чесно:", "важливо:", "honestly:",  # feedback_no_robotic_lead_in_phrases
)


def detect_mechanical_violations(text: str) -> dict[str, list[str]]:
    """Deterministic, non-LLM scan for NON-NEGOTIABLE rules that free-form
    generation doesn't reliably self-enforce on its own.

    Covers phase3_cv_draft.md rule 25 (em-dash ban) and the maintained
    banned-phrase list above. Both recurred multiple times across sessions
    despite the prompt already stating the rule explicitly (em-dash on
    #915/#922/#932/#934, "gap analysis" on #932/#934, same session,
    2026-07-30) — see BACKLOG.md "Mechanical NON-NEGOTIABLE rule violations
    are never re-verified downstream".

    Args:
        text: Full CV or cover draft text.

    Returns:
        {"em_dash": [...], "banned_phrases": [...]} — each a list of
        one-line human-readable hits ("line 12: ..."), empty when clean.
        Advisory only — flag for a one-click fix, don't hard-block; a hit
        can be a legitimate false positive (e.g. "on time" inside an
        unrelated phrase) that a human dismisses on review.
    """
    lines = text.splitlines()

    em_dash_hits = [
        f"line {i}: {line.strip()}" for i, line in enumerate(lines, start=1) if "—" in line
    ]

    banned_hits: list[str] = []
    for i, line in enumerate(lines, start=1):
        line_lower = line.lower()
        for phrase in _BANNED_PHRASES:
            if phrase.lower() in line_lower:
                banned_hits.append(f'line {i}: "{phrase}" — {line.strip()}')

    return {"em_dash": em_dash_hits, "banned_phrases": banned_hits}


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
