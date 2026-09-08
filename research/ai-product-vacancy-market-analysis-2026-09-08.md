# AI-Related Product Vacancy Market Analysis — 2026-09-08

**Corpus:** 285 vacancies (of 1406 total in DB, 1333 scanned with a JD.md on disk) — title match: 93, body match: 192.

**Filter:** Product-track title (Product Manager/Owner, Project/Delivery/Program Manager, Business Analyst, Operations Manager, Technical Product/Project Manager) **and** an AI/ML signal central to the posting (title match, or 2+ body mentions, or 1 mention inside a Requirements-shaped section). Full methodology: `research/ai-product-vacancy-market-analysis-methodology.md`.

**Notable exclusion:** 379 vacancies had an AI signal but a non-Product title (AI/ML/GenAI Engineer, Application Specialist, etc.) — more than the entire included corpus. AI-related hiring in this dataset skews heavily toward engineering roles; Product-track AI roles are the minority even within "AI hiring" as a whole.

---

## Technologies

| Term | Vacancies | % of corpus |
|---|---:|---:|
| Anthropic / Claude | 51 | 17.9% |
| Agents / agentic workflows | 49 | 17.2% |
| OpenAI / GPT / ChatGPT | 41 | 14.4% |
| Google Gemini / PaLM / Vertex AI | 14 | 4.9% |
| RAG / retrieval-augmented generation | 13 | 4.6% |
| Prompt engineering | 9 | 3.2% |
| Computer vision | 8 | 2.8% |
| MCP (Model Context Protocol) | 7 | 2.5% |
| Embeddings | 5 | 1.8% |
| MLOps | 3 | 1.1% |
| Llama / Meta AI | 2 | 0.7% |
| Mistral | 2 | 0.7% |
| Fine-tuning | 2 | 0.7% |
| CrewAI | 2 | 0.7% |
| Figma AI | 2 | 0.7% |
| Azure OpenAI | 1 | 0.4% |
| Vector database | 1 | 0.4% |
| LangChain | 1 | 0.4% |
| Langflow | 1 | 0.4% |
| LangGraph | 1 | 0.4% |
| NLP | 1 | 0.4% |
| Cohere / AWS Bedrock / Hugging Face / LlamaIndex / Flowise / AutoGen / Semantic Kernel / Haystack / Speech-voice AI / Transformer models / Diffusion models | 0 each | 0.0% each |

**Reading it:** the "big three" model providers (Claude, GPT, Gemini) dominate named-technology mentions, with **Claude slightly ahead of GPT** — worth noting given how frequently market commentary assumes OpenAI leads by default. "Agentic/AI agents" is the single most-hyped concrete concept after the model names themselves — nearly 1 in 5 postings names it explicitly, reflecting the 2026 market's agent-workflow wave. Everything past the top 5 is a long tail: specific techniques (RAG, embeddings, fine-tuning), specific frameworks, and infra (MLOps, vector DBs) each show up in under 5% of postings. **Reading:** most Product-track AI postings expect conceptual/practical fluency with named model providers and the agentic-workflow concept, not deep technical AI-tooling expertise (that's an engineering-track expectation, consistent with the 379 excluded engineering vacancies above).

**Named-framework granularity (added mid-run 2026-09-08 per explicit request):** splitting out specific agent-building/orchestration frameworks — LangChain, LlamaIndex, CrewAI, Langflow, Flowise, AutoGen, LangGraph, Semantic Kernel, Haystack — shows almost all of them at 0-1 mentions each. The one real exception is **CrewAI (2 mentions, 0.7%)**, a no-code/low-code agent-building tool — plausibly more likely to surface in a *Product*-track JD than the code-first frameworks (LangChain, LlamaIndex, Semantic Kernel, Haystack), which stayed at 0-1 each. **Figma AI (2 mentions)**, tracked separately from bare "Figma," shows the AI-specific feature is named on its own in a small but real minority of postings. **Reading:** at the Product-track level, specific framework names essentially don't matter yet — the market asks for the concept (agentic workflows, RAG) and the model provider (Claude/GPT/Gemini), not fluency with a particular orchestration library. That fluency lives in the engineering-track postings this report excludes.

## Skills

| Term | Vacancies | % of corpus |
|---|---:|---:|
| AI tool fluency (operational use, not building AI) | 84 | 29.5% |
| Data literacy (SQL/Python) | 33 | 11.6% |
| A/B testing (general — see caveat) | 28 | 9.8% |
| Prompt engineering (as a stated skill) | 9 | 3.2% |
| Hallucination mitigation | 7 | 2.5% |
| Responsible AI / ethics / safety | 5 | 1.8% |
| Human-in-the-loop design | 4 | 1.4% |
| Dataset curation / labeling | 1 | 0.4% |

**Reading it:** the single most commonly requested AI-related skill, by a wide margin, is **using AI tools day-to-day to work faster** (research synthesis, drafting, analysis) — not building or shipping AI features. Nearly 3 in 10 postings ask for this. That's a meaningfully different bar than "AI product experience" as commonly imagined, and it's the skill this candidate's own profile already leads with (daily Claude/ChatGPT/Gemini practice). Harder, more specialized skills — dataset curation, responsible-AI judgment, human-in-the-loop design — stay rare across the whole Product-track segment, reinforcing that deep AI-craft skills concentrate in the excluded engineering-track postings, not here.

**Caveat:** "A/B testing" measures any A/B-testing mention in an AI-related posting, not specifically A/B testing of AI features — the dictionary can't currently distinguish the two.

## Requirements

| Term | Vacancies | % of corpus |
|---|---:|---:|
| Senior/Lead level language (see caveat) | 150 | 52.6% |
| AI-native positioning (title/company) | 23 | 8.1% |
| Commercial/technical background (CS/eng degree) | 17 | 6.0% |
| X+ years AI/ML experience (explicit) | 5 | 1.8% |
| Shipped AI feature(s) to production (explicit) | 3 | 1.1% |

**Reading it:** explicitly *stated* requirements are rare — only 3 of 285 postings spell out "shipped AI to production" as a line item, and only 5 name an explicit years-of-AI-experience threshold. Most postings imply the bar through framing instead: "AI-native" as a self-description (8.1%) is a distinct, newer positioning pattern (a company/role branding itself around AI from the start, not listing AI as one requirement among many) — worth watching as its own category rather than folding into generic AI-technology mentions.

**Caveat:** "Senior/Lead level language" measures the words "senior"/"lead" appearing anywhere in the JD (title, team description, stakeholder mentions, etc.) — it is **not** an AI-specific finding, just general market context for how senior this vacancy segment skews. Do not read the 52.6% as "AI roles specifically demand seniority" — it may just reflect this Product-track corpus generally.

## Tools

| Term | Vacancies | % of corpus |
|---|---:|---:|
| Jira / Confluence (generic PM baseline) | 82 | 28.8% |
| Amplitude / Mixpanel (analytics) | 33 | 11.6% |
| Figma | 30 | 10.5% |
| n8n / Zapier / Make (automation) | 17 | 6.0% |
| GitHub Copilot / AI coding assistants | 14 | 4.9% |
| Notion AI | 3 | 1.1% |

**Reading it:** the tool list is dominated by generic PM tooling (Jira/Confluence, Amplitude/Mixpanel, Figma) that would show up in any Product-track corpus, AI-related or not — included here as a baseline, not a finding. The one AI-specific pattern: n8n/Zapier/Make (automation-building tools) appear more often (6.0%) than AI coding assistants (4.9%) — automation-tool fluency shows up more than expected for a Product-track (not engineering) corpus.

---

## Notable patterns

- **The market's "AI Product" hiring is mostly engineering hiring wearing an AI label** — 379 excluded vacancies (AI signal, non-Product title) vs. 285 included. Anyone scanning "AI job postings" casually would overcount actual Product-track opportunity.
- **"AI tool fluency" (operational, not technical) is the single largest skill ask** (29.5%) — larger than any named technology, framework, or specialized AI skill. This is the most learnable, most already-demonstrated bar in this whole dataset.
- **Claude edges out GPT** as the most-named model by a small margin (17.9% vs 14.4%) — useful to know when a candidate's own tooling practice already centers on Claude.
- **"Shipped AI to production" as an explicit stated requirement is rare** (1.1%) — the market mostly signals the AI bar through framing (AI-native positioning, technology mentions) rather than a hard, explicitly-worded production-shipping requirement.

## Dictionary changes this run

Named-framework granularity added per explicit user request: split the old combined "LangChain / LlamaIndex" entry into two, and added CrewAI, Langflow, Flowise, AutoGen, LangGraph, Semantic Kernel, Haystack, and Figma AI (tracked separately from bare "Figma"). See the Technologies section's own callout above for what this did and didn't change.

Two other terms added mid-run after the open-coding spot-check surfaced them (see `scripts/ai_vacancy_report.py` for the exact regex):
- **"AI tool fluency (operational use, not building AI)"** (Skills) — found on vacancy #203 (Operations Manager), a distinct and far more common ask than "prompt engineering as a skill."
- **"AI-native positioning (title/company)"** (Requirements) — found as a recurring title pattern (#1324 "AI-Native Product Manager", #692's JD body "AI-native рішень").

One bug fixed before this run counted: an early version of the "Computer vision" technology term matched bare `\bcv\b`, which caught "send us your CV" (résumé) 37 times before the pattern was tightened to `computer vision` only — see methodology doc for the full story.

One scoping fix made before this run counted: the corpus filter originally checked only for an AI signal, with no requirement that the role itself be Product-track — engineering titles like "AI Engineer" and "GenAI Engineer, AI Builder..." were slipping in. Added a required second condition (title must match the Product-track allowlist) — dropped the raw AI-signal corpus from 380 to the final 285.

*(No previous dated report exists yet — this is the first run. Future runs should compare against this one here.)*
