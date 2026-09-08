# General Product Manager/Owner Vacancy Market Analysis — 2026-09-08

**Corpus:** 954 vacancies (of 1406 total in DB, 1333 scanned with a JD.md on disk) — every vacancy with a Product-track title (Product Manager/Owner, Project/Delivery/Program Manager, Business Analyst, Operations Manager, Technical Product/Project Manager). No AI-signal filter — AI-related Product vacancies (the 285-vacancy corpus from `research/ai-product-vacancy-market-analysis-2026-09-08.md`) are included here as a natural subset of the whole market, not excluded.

**Filter/methodology:** `research/pm-vacancy-market-analysis-methodology.md`.

---

## Methodologies

| Term | Vacancies | % of corpus |
|---|---:|---:|
| Agile / Scrum | 330 | 34.6% |
| Kanban | 112 | 11.7% |
| Waterfall | 31 | 3.2% |
| OKR | 22 | 2.3% |
| JTBD (Jobs-to-be-Done) | 17 | 1.8% |
| Design Thinking | 11 | 1.2% |
| WSJF | 5 | 0.5% |
| SAFe (Scaled Agile Framework) | 4 | 0.4% |
| Lean / Lean Startup | 4 | 0.4% |
| RICE / ICE prioritization | 0 | 0.0% |

**Reading it:** Agile/Scrum dominates by a wide margin — over a third of all Product-track vacancies name it explicitly, roughly 3x the next most common methodology (Kanban). Everything past the top two is a long tail under 4%. Named prioritization frameworks (OKR, WSJF, RICE/ICE, formal SAFe) are genuinely rare as explicit JD language — most postings either don't name a framework at all or describe the practice generically ("quarterly roadmap," "prioritization based on impact") without a named methodology. **RICE/ICE at 0% is likely a dictionary undercount, not a true zero** — the pattern requires "framework"/"score"/"method" immediately near the acronym to avoid false positives (bare "ICE"/"rice" risked far more noise than signal) — see methodology doc.

## Tools

| Term | Vacancies | % of corpus |
|---|---:|---:|
| Jira / Confluence | 287 | 30.1% |
| Amplitude / Mixpanel | 88 | 9.2% |
| Figma | 77 | 8.1% |
| SQL | 70 | 7.3% |
| Notion | 65 | 6.8% |
| Google Analytics | 62 | 6.5% |
| Miro / Mural | 34 | 3.6% |
| Trello | 33 | 3.5% |
| Asana | 24 | 2.5% |
| GitHub Copilot / AI coding assistants | 17 | 1.8% |
| Monday.com | 3 | 0.3% |
| Figma AI | 3 | 0.3% |
| Notion AI | 3 | 0.3% |
| Productboard | 1 | 0.1% |

**Reading it:** Jira/Confluence is the de facto standard — named in almost 1 in 3 vacancies, well ahead of any alternative tracker (Trello, Asana, Monday.com are all under 4% combined). Analytics tools (Amplitude/Mixpanel, Google Analytics) and design collaboration (Figma) show up consistently in the 6-9% range — a real, recurring expectation, not a fringe ask. Dedicated product-management/roadmapping tools (Productboard) are essentially absent — almost nobody names a specialized PM tool by brand; Jira/Confluence covers that role generically for most companies in this market.

**Named AI-tool granularity (added mid-run 2026-09-08 per explicit request):** even in this general, non-AI-filtered corpus, GitHub Copilot/AI coding assistants shows up in 1.8% of postings — more than Monday.com, Figma AI, or Notion AI combined. Figma AI and Notion AI (the AI-specific *feature* inside an already-common base tool, tracked separately from bare "Figma"/"Notion") are each named in only 0.3% — real but rare as an explicitly-called-out capability; most postings that expect AI-tool fluency don't specify which AI feature of which tool, consistent with the AI-related report's own finding that "AI tool fluency" is usually asked for generically, not tool-by-tool.

## Domains

| Term | Vacancies | % of corpus |
|---|---:|---:|
| B2B SaaS | 168 | 17.6% |
| Gaming / iGaming | 166 | 17.4% |
| Fintech | 140 | 14.7% |
| E-commerce / Marketplace | 127 | 13.3% |
| B2C | 117 | 12.3% |
| Mobile app product | 36 | 3.8% |
| Edtech | 34 | 3.6% |
| Cybersecurity | 27 | 2.8% |
| Logistics / Supply chain | 25 | 2.6% |
| HR tech | 15 | 1.6% |
| Healthtech / Medtech | 11 | 1.2% |
| Martech | 10 | 1.0% |
| Adtech | 9 | 0.9% |
| Mobile subscription (B2C recurring revenue) | 3 | 0.3% |

**Reading it:** five domains — B2B SaaS, Gaming/iGaming, Fintech, E-commerce/Marketplace, **B2C** — each show up in 12-18% of the whole corpus, together accounting for a large majority of all domain-identifiable vacancies. B2C (added mid-run — see Dictionary changes below) turns out to be the 5th-largest domain, ahead of every long-tail category. Everything else (Mobile, Edtech, Cybersecurity, Logistics, HR tech, Healthtech, Martech, Adtech) is a long tail under 4% each. This roughly matches the general shape of the Ukrainian/CIS outsourcing-and-product IT market this dataset is drawn from (DOU/Djinni), not a universal finding about Product Management as a discipline.

**B2C + mobile + subscription:** mobile app product roles are 3.8% of the corpus on their own, but the specific combination the user flagged — B2C mobile subscription/recurring-revenue products — shows up as an *explicit, textually-combined* mention in only 0.3% (3 vacancies). That's almost certainly an undercount of the real segment: most JDs describe "B2C," "mobile app," and "subscription" as separate facts scattered across the posting rather than one combined phrase, so this narrow combined-phrase count is a floor, not the true size of the segment.

**Settled empirically (2026-09-08) — is B2C mostly mobile, i.e. should the two categories be merged?** No. Checked directly against the corpus: only 9.4% of B2C-tagged vacancies also match "Mobile app product" on the narrow phrase; even with a deliberately broad mobile-signal check (iOS/Android/App Store/Google Play/native app, not just the literal phrase "mobile app"), the overlap only rises to 25.6%. Spot-checked the non-overlapping majority directly: Influence Pro Services (#66) states outright "B2C продуктами з підписочною моделлю (**mobile та web**)" — the company itself treats web as an equal channel, not an edge case; ELVTR (#230, an edtech company) asks for "B2C or consumer-facing product work, especially in edtech or online learning" — online learning is typically web-first, not mobile-native. B2C and Mobile stay separate dictionary categories — merging them would erase a real, large slice of the market (web-based B2C subscriptions, online learning, desktop-first consumer products).

**Caveat:** these counts measure *mention*, not *primary business* — a company describing itself as spanning several areas (e.g. "cultural projects, capital markets, and gaming") gets counted under every domain it names, even when only one is the company's actual core product. Treat this table as "how often each domain comes up," not "how many companies are purely in that domain."

## Requirements

| Term | Vacancies | % of corpus |
|---|---:|---:|
| Explicit years-of-experience threshold | 442 | 46.3% |
| Senior/Lead level language (see caveat) | 418 | 43.8% |
| Explicit English level (CEFR) | 245 | 25.7% |
| Startup/Scaleup stage signal | 52 | 5.5% |
| Commercial/technical background (CS/eng degree) | 43 | 4.5% |
| Product certification (CSPO/PSPO/SAFe POPM/PMP) | 38 | 4.0% |

**Reading it:** roughly half of all Product-track postings state an explicit years-of-experience number, and a similar share use senior/lead-level language somewhere in the text — this market skews experienced, not entry-level, as a baseline. A quarter of postings state an explicit CEFR English level (mostly a Ukrainian-outsourcing-market feature — international clients need a stated language bar). Named product certifications (CSPO/PSPO/SAFe POPM/PMP) appear in only 4% of postings — having one is far from a market-wide expectation, more a differentiator than a baseline requirement.

**Caveat:** "Senior/Lead level language" and "explicit years-of-experience threshold" both measure any occurrence of that language anywhere in the JD (title, team description, stakeholder mentions), not a confirmed hard requirement specifically for the PM/PO role itself.

---

## Notable patterns

- **Agile/Scrum + Jira/Confluence is close to a universal baseline** (34.6% and 30.1% respectively, each roughly 3x its nearest alternative) — the safest default assumption for what any given Product-track posting expects, absent other signal.
- **Named prioritization frameworks are rare in explicit JD language** — most postings describe prioritization practice generically rather than naming OKR/WSJF/RICE/SAFe. A candidate's own "quarterly roadmap, prioritized by impact" framing (informal-but-real practice) matches how most of this market actually talks about it, not a gap against the norm.
- **Domain concentration:** just 5 domains (SaaS, Gaming, Fintech, E-commerce, B2C) cover the large majority of domain-identifiable postings — worth knowing which of these five best matches a candidate's own background/interest, since together they're a majority of the addressable market, not a handful of niches.
- **Certifications are a differentiator, not table stakes** — only 4% of postings name one explicitly, so having a certification (e.g. SAFe POPM) is a genuine, uncommon signal, not something the market broadly assumes.

## Comparison against the AI-related Product report (same date)

Both reports scanned the same DB snapshot, so this comparison is directly meaningful:

- **Seniority skews higher in AI-related roles than the general market.** "Senior/Lead level language" is 52.6% in the 285-vacancy AI corpus vs. 43.8% here — AI-related Product roles ask for more seniority than the Product-track market as a whole, by a real margin (roughly +9 points).
- **Jira/Confluence is an equally universal baseline in both** (28.8% AI-corpus vs. 30.1% here) — AI-related hiring doesn't change the baseline tooling expectation at all.
- **The AI report's headline finding — "AI tool fluency" as the single most-requested skill (29.5%) — has no equivalent axis in this general report** (Methodologies/Tools/Domains/Requirements don't capture "operational AI-tool usage" as a category). Worth noting as a real blind spot in this report's own category design, not evidence that the skill is unimportant generally.

## Dictionary changes this run

B2C, Mobile app product, and Mobile subscription (B2C recurring revenue) added after the user flagged a real gap: B2C wasn't in the original domain dictionary at all. B2C turned out to be the 5th-largest domain (12.3%) — see Domains section callout above for the mobile+subscription combo caveat.

Named AI-tool granularity added per explicit user request (see Tools section callout above): Figma AI, Notion AI, and GitHub Copilot/AI coding assistants — all tracked separately from their base-tool entries.

One bug fixed before this run counted: bare "gaming" matched office-perk mentions ("lounge and gaming zones," vacancy #70) alongside genuine gaming-industry postings. Fixed with a negative lookahead excluding the perk-noun pattern (`zone`/`room`/`area`/`lounge`/`corner`/`chair`/`console`/`pc`/`setup`/`table`); `igaming`/`gambling`/`casino`/`betting` stay unconditional. See methodology doc for the "SAFe" and "Monday.com" false-positive guards designed in from the start (same lesson, applied pre-emptively before the first run).

*(No previous dated report exists yet — this is the first run.)*
