# career-agent — Glossary

> Project vocabulary, one line per term. The prompts, `skill/SKILL.md` and the code stay the source of truth for the rules; this file only fixes what each word means, so one word is not used for two things.
> Add new terms here, not in individual discovery docs. File and folder names in `code style` point to where the term lives.

## 1. Pipeline and commands

| Term | Meaning |
|---|---|
| **`/analyze`** | Claude Code slash command (`.claude/commands/analyze.md`) that runs the local CV pipeline: Claude Code itself is the LLM, no external API. Flags: `-v [id]` (one vacancy), `-u` (switch user), `-l` (list users), `-pdf`, `-inbox`. Orchestration rules live in `skill/SKILL.md`. |
| **`/pipeline`** | The same pipeline run through the Anthropic API (`ClaudeProvider`) instead of Claude Code's own model. |
| **Local mode / API mode** | Local: Claude Code is the agent, nothing goes through a paid API. API: the pipeline calls an LLM provider and spends tokens. Chosen in the Step 0 menu. |
| **Step 0 combined menu** | The first message of every `/analyze` run: Block 1 (items 1–10: mode, profile source, user) next to Block 2 (items 11–20: inbox items or the actions for one vacancy). One numbered answer, no extra round trip. |
| **Batch / sequential mode** | Sequential: vacancies one by one with the full analysis shown for each. Batch: Phase 1+2 run silently for all selected vacancies, then one consolidated table. `analyze.md` picks by count (1–2 sequential, 3+ batch). |
| **`inbox_manual`** | `vacancies/inbox_manual/`, the folder where the user drops JDs by hand. Scanned by `scripts/inbox_scan.py`; after processing the folder moves into `vacancies/inbox/{user_id}/`. |
| **Vacancy folder** | `vacancies/inbox/{user_id}/{vacancy_id} — {Role — Company}/`. Holds every artifact of one vacancy. The characters `#` and `,` are stripped from folder names (they break chat-client file links). |
| **Vacancy artifacts** | `JD.md` (the saved posting), `JD_analysis.md` (Quick Scan, Phase 1, Phase 2 and review/audit blocks), `[Name]_CV.md/.pdf`, `[Name]_Cover.md/.pdf`. A `_UA` suffix marks Ukrainian versions. File names are Latin only. |
| **`analysis_json`** | DB column on `vacancies` with the structured result of each phase under keys `p1`…`p4`. Schema in `contracts/pipeline.py`, written by `scripts/vacancy_track.py update-json`. The full prose stays in `JD_analysis.md`. |
| **skill_type** | Profile setting, `pm` or `generic`. Selects which `prompts/[skill_type]/` set of phase prompts is loaded. Paths are never hard-coded to the prompts root. |
| **PROFILE_SOURCE** | `md` (default: candidate data comes from `PROFILE.md`) or `db` (from the `progressive_profile` JSON). Chosen in the Step 0 menu; settings are still read from `PROFILE.md` either way. |
| **Known company / Listed salary lines** | Lines the pipeline prepends to the JD text before Phase 1, taken from the DB (`company`, `salary`), which the parser extracted structurally. Without them Phase 1 would score a known salary as "not stated" or write a placeholder company. |
| **Pre-flight** | The questions asked once before Phase 3: CV language (only when the JD is not English) and name variant (only when the profile has more than one). |
| **Render once** | Rule: a CV or cover PDF is rendered exactly once, when the document is final. Every edit round saves the `.md` only. |

## 2. Phases and their outputs

| Term | Meaning |
|---|---|
| **Phase 1 — JD Analysis** | Reconstructs what the company is trying to solve with this hire: header, North Star and branches, pain points, maturity, role archetype, role balance, expectations, language analysis, VScore. `prompts/pm/phase1_analysis.md`. |
| **Phase 2 — Fit Assessment** | Scores the candidate against the JD. Produces Internal Analysis, Fit Breakdown, Quick Scan, Signal Coverage Table and Adaptation Plan. `phase2_fit.md`. |
| **Phase 2.5 — Objection Handling** | Runs when Key Barriers is not empty (skipped for `decline` and for a clean `apply`). The candidate says which barriers they have real experience for. Resolved evidence is added to the profile; confirmed gaps are never fabricated in the CV. |
| **Phase 3 — CV draft** | Internal step, the draft is not shown. Written under the NON-NEGOTIABLE rules in `phase3_cv_draft.md`. |
| **Phase 3.5 — Self-Review** | Review of the draft: word-frequency and tools tables, mechanical checks, voice, B2 language, North Star alignment, tone. Ends with the corrected CV. |
| **Phase 3.6 — Signal Audit** | Splits each EXPERIENCE sentence into clauses and checks each against the Signal Coverage Table: valuable, weak, or remove. Ends with a North Star check. |
| **Phase 3.7 — Editorial Audit** | Opt-in prose-quality audit (naturalness, credibility, JD-echo risk). Runs only for `apply` with fit 7 or higher, or on request, and runs in an isolated subagent to avoid self-audit bias. |
| **Phase 3.8 — ATS Keyword Coverage** | Planned, not built. Would make sure the CV literally contains the JD's load-bearing keywords wherever real evidence exists. See BACKLOG. |
| **Phase 4 — Cover** | Generates the cover message from the approved CV and the analysis. Deliberately light on evidence; one variant by default. |
| **Quick Scan** | Summary block at the top of `JD_analysis.md`: Fit, VScore, Recommendation, Category, Who they want, Key Barriers, Hidden Risks, Warnings. Written last in Phase 2 as a summary of the deeper analysis, shown first. |
| **Internal Analysis** | Phase 2's deep evidence matching (fit dimensions, strong matches, weak spots, objections). Kept for reference, not sent to the user. |
| **Fit Breakdown** | Table of the 6–10 most significant JD requirements with a status (✅ direct commercial experience, ⚠️ partial or pet-project, ❌ none) and the evidence. |
| **Signal Coverage Table** | Phase 2 table of JD signals with branch, whether the candidate has the evidence, whether it is distinctive, and an importance tier (high, medium, low). |
| **Coverage mandate** | Rule: every signal with importance high or medium and evidence ✅ or ⚠️ must appear in at least one role of the CV's EXPERIENCE. Signals with no evidence are never invented. |
| **Adaptation Plan** | Phase 2's concrete instructions for the CV: 3–5 reframing actions, the lead action framed in North Star terms. Phase 3 must implement all of them. |
| **Company type detection** | Pre-Phase-3 step that labels the employer `enterprise`, `scaleup`, `startup` or `founder-led` and adapts the CV vocabulary. Kept as `COMPANY_TYPE` and used by the Phase 3.5 tone check. |

## 3. Scoring and recommendations

| Term | Meaning |
|---|---|
| **Fit score** | How well the candidate fits, 1–10. Starts at 5.0 and moves with evidence per requirement, capped at 9.5. Stored in the DB as a whole integer (a fractional value breaks the Flutter list); prose in `JD_analysis.md` may stay fractional. |
| **VScore (vacancy score)** | How attractive the vacancy is, independent of fit, 0–10. Computed by `core.vacscore.compute_vacancy_score`, never by hand. |
| **VScore dimensions** | Eight inputs to VScore: `company_tier` (1–4), `seniority` (1–4), `market_scope` (1–3), `company_type` (1–3), `company_stage_fit` (1–3), `domain_score` (1–5), `remote_policy` (1–3), `compensation` (1–3). |
| **Recommendation** | `apply`, `take a chance` or `decline`, taken from the Fit × VScore matrix. A hard blocker or fit under 5 forces `decline`. Stored as the base value (`take_a_chance` with an underscore); the label is display-only. `decline` is advisory and never blocks CV generation. |
| **Key Barriers** | Candidate-side hard gaps (missing commercial experience, archetype mismatch, far below the experience bar). Short labels, up to 5 words each. |
| **Hidden Risks** | Role or company context risks that are not candidate gaps (early stage, chaos risk, scope that may expand). |
| **Warnings** | Application-process risks only (timezone overlap, travel, B2B-only contract, long hiring pipeline, test assignment). |
| **Blocker** | A hard knockout that forces `decline`: mandatory relocation with no remote option, a hard domain requirement the candidate lacks, a verified language threshold, a license, experience far above the candidate's, a mandatory technical stack. |
| **Critical Blockers pre-filter** | EPIC-27. A cheap check right after a vacancy is fetched against the profile's Critical Blockers list. Flags the vacancy with a badge, advisory only. Stage 1 is deterministic (title, English level, location and format, mobile domain); Stage 2 is a manual LLM check. |
| **role_balance** | Percentage split of what the role asks, over six axes that sum to 100: `strategy`, `discovery`, `delivery`, `growth`, `stakeholder`, `operational`. Canonical names only. Shown as a radar chart in Flutter. |
| **Role Balance Shape** | Computed from role_balance: Sharp if the top axis leads the second by 10 points or more; else Dual if the second leads the third by 10 or more; else Diffuse. Drives what the CV leads with. |
| **Primary archetype** | `[balance-intensity] [role-shape]`, e.g. `Delivery-heavy Platform/Systems PM`. Both parts come from closed lists; no other wording is allowed. |
| **Founder Proxy / Executor** | The candidate's dual archetype and the JD's. Founder Proxy: owns vision, 0→1, high autonomy. Executor: delivery and execution. A mismatch is both a Key Barrier and an Adaptation Plan signal. |
| **Company type** | Two different things: the `company_type` field of Phase 1 (`product`, `hybrid`, `outsourcing`, scored in VScore) and the `COMPANY_TYPE` lexicon label (`enterprise`, `scaleup`, `startup`, `founder-led`). |

## 4. Vacancy lifecycle

| Term | Meaning |
|---|---|
| **status** | Fine-grained pipeline state of a vacancy in the DB (`fetched`, `analyzed`, `analysis_failed`, `cv_generated`, `cover_generating`, `cover_generated`, `declined`, plus a few legacy values). Workers need the exact state. |
| **stage** | The five-way folder classification derived from status and the Applied flag by `core/vacancy_stage.py`: Inbox, Analyzed, Processed, Applied, Archive. `declined` wins first (Archive), then Applied, then the status decides. The Flutter tabs show stages. |
| **Applied** | An orthogonal boolean flag, not a status: a user can apply after only an analysis, after a CV, or after CV and cover. `applied_at` records when. |
| **Declined / Archive** | Declined is the user's explicit reject (`declined_at`). Archive is the folder those vacancies live in. |
| **starred** | User flag for vacancies to keep an eye on. |
| **Republish detection** | EPIC-26. When a known vacancy reappears in a feed, the system re-fetches its JD and re-checks tags, salary, company and blockers instead of ignoring the known URL. |
| **`duplicate_of`** | Pointer from the later-found posting to the canonical one (the same JD on Djinni and DOU). The badge shows on both sides of the pair. |
| **Company identity** | EPIC-26. Who a vacancy's employer is: the company's job-board profile URL (`company_profile_url`, key `"{site}:{slug}"`, `core.dedup.profile_key`), learned cross-board pairs (`company_profile_links`), and a normalized name as the fallback (`normalize_company_name`, folds Cyrillic lookalike letters inside Latin words). `same_company()` combines them. |
| **Text-first duplicate** | EPIC-26. A vacancy whose JD contains >= 0.90 (`TEXT_CONFIRM_THRESHOLD`) of a recent (120-day window) vacancy's text is a confirmed duplicate whatever its company or title. |
| **`company_applied_id`** | The most recently applied vacancy at the same company (not a duplicate): the weaker "Co. applied #N" card badge. |
| **Manual import** | A JD pasted by hand through `/api/vacancies/import-jd`. The `manual_import` flag marks it; the real posting URL is recovered from the pasted text when possible. |
| **Tags** | Auto-assigned keyword categories (`deftech`, `igaming`, `mobile`, `outsourcing`, `b2b_saas`, `studio`, `fintech`, `healthtech`, `b2c`) and user-assigned tags (the primary one goes into the folder name as `[TAG]`). Not the same as `role_tags`, which are derived from role_balance and display-only. |
| **Hidden-salary estimator** | `services/parser/salary_probe.py`. Estimates a Djinni vacancy's undisclosed salary through Djinni's own `salary=N` search filter (exponential, then binary search). A give-up note `(probe: ...)` is retry-eligible, not a real value. |

## 5. The candidate profile

| Term | Meaning |
|---|---|
| **`PROFILE.md`** | The candidate's profile in Markdown (`skill/users/[id]/PROFILE.md`, gitignored): Settings, Identity, Narrative, Experience, Skills, Generation Rules, Pipeline Config, Reference, Honest Gaps. The default source of candidate data. |
| **`progressive_profile`** | EPIC-24. The structured JSON profile stored in the DB. Read only when `PROFILE_SOURCE=db`. Its future is an open decision. |
| **Name variants** | The allowed forms of the candidate's name for a CV (an informal default and a formal one). A single variant or a stated default is used without asking. |
| **Vacancy Preferences** | Profile section (`domain_interests`, `company_stage_prefs`, `product_type_prefs`). Input to VScore. |
| **Honest Gaps** | Facts the candidate does NOT have. Never fabricated and never implied, however strongly a JD asks. |
| **Generation Rules** | Profile section with the owner's rules for writing a CV: summary opening term, key results, AI paragraph, and so on. |
| **Golden standard / locked text** | Text the owner fixed verbatim. Used unchanged on every CV, never paraphrased per vacancy. |
| **Canonical text** | The owner-approved wording of a role block (English or Ukrainian) to reuse as the base. |
| **Key results** | The outcomes block that every role in EXPERIENCE must have, including the current one. NPS and CSAT are merged into one bullet. |
| **Profile language** | The `language` setting controls chat and analysis language. CV language follows the JD, not this setting. |

## 6. CV writing rules

| Term | Meaning |
|---|---|
| **Golden Rule (North Star Mirroring)** | The SUMMARY and the cover opening must recognizably answer the Phase 1 North Star, paraphrased and never copied from the JD. Applied in every phase from analysis to cover. |
| **Emphasis Precedence** | Order that resolves conflicting "what to lead with" mechanisms: Golden Rule first, then archetype-mismatch handling, then Tailoring Logic (Role Balance Shape), then Primary Asset. |
| **Primary asset / supporting roles** | The 1–2 roles that most directly match the core requirement lead with the JD's vocabulary. Every other role carries a secondary signal without having the primary keyword forced into it. |
| **Tailoring Logic** | Default emphasis driver when no branch qualified as lead: lead with the strongest experience for the axis (or two) the Role Balance Shape points to. |
| **Elaboration-depth check** | An action named in the Adaptation Plan must get the same depth in the CV as comparable signals, not a one-line name drop. |
| **Practice, not cases** | CV rule 23: roles describe a pattern of work, not specific case stories. Cases belong in the interview. |
| **Voice rule** | CV rules 8 and 9: no first person, and no third-person present-tense verbs with an implied subject ("Owns", "Works"). Headline style or past tense. A present-tense verb inside a relative clause with its own subject ("a tool that tracks X") is allowed. |
| **Language-level rule** | CV rule 26: write at the candidate's actual English level, stated in the profile's Languages entry (for a non-native intermediate level such as B2: plain wording, no idiom the candidate could not defend in an interview). |
| **Manufactured parallel** | An invented or forced link between a JD requirement and a profile fact, usually a shared word. A fabrication-class error; banned. |
| **AI tooling paragraph** | The fixed one-line "AI tooling across PM workflows…" mention, a default on every CV. A two-component form with human-in-the-loop wording is for roles with real AI depth. The portfolio link appears exactly once. |
| **Mechanical lint** | `core/cv_metrics.py` checks run in Phase 3.5: `detect_mechanical_violations` (em-dash, banned phrases), `detect_repetition` and `detect_phrase_repetition`, and `detect_jd_echo`. `scripts/cv_checks.py` runs all of them (plus the frequency and tools tables) in one command. |
| **Self-audit bias** | Measured effect: an auditor in the same conversation as the author scores the text higher than an isolated one. The reason Phase 3.7 runs in an isolated subagent. |

## 7. North Star Signal Tree

| Term | Meaning |
|---|---|
| **North Star** | The single sentence stating what result the company is buying with this hire (`[role] must [action] so that [outcome]`), or an honest "not found". Searched in `phase1_analysis.md` §1.0.5 Stage 1. Requirements & Qualifications outweigh Key Responsibilities when looking for it. |
| **Trunk** | The design-time name for the North Star. The prompts use "North Star"; "trunk" appears only in the early sections of the discovery doc. |
| **Branch** | One distinct cluster of JD requirements hanging off the North Star. One branch is one distinct function or ask; bundles are split in Phase 1 Stage 2, not later. |
| **Central / secondary** | Phase 1's judgment of whether a branch belongs to the North Star's own core or only supports it. `no North Star` when none was found. A judgment call, not a count or a position in the text. |
| **Branch weight** | Two independent judgments combined: JD-centrality (Phase 1) and candidate-distinctiveness (Phase 2). Neither is a formula. |
| **Distinctive?** | Phase 2's direct question per signal: would most competing candidates for this exact role also credibly claim this evidence, or is it hard for them to match? |
| **Lead signal** | The branch that is both `central` and has `Distinctive = yes` evidence in the profile. The CV leads with it. If none qualifies, the honest output is "No strong differentiator identified". |
| **Bold-signal** | Check of the JD for selective bold emphasis: if the author bolded only some items, attention shifts to them. Bolding every item by template is not a signal. Rule in `phase1_analysis.md` §1.0.5 Stage 1. |
| **Unlock condition** | A usage condition written on a profile fact (rare / default-omit / "include only when…"). Phase 2 checks it by the type of work the JD asks for, never by a shared word. |
| **JD-echo** | CV phrasing lifted from the JD's own wording instead of composed from the candidate's evidence. Caught mechanically by `detect_jd_echo()` and by Phase 3.7. |
| **Weak-signal overfit** | Pairing a low-importance, single-mention JD word with a narrow profile fact just because the words match. |

## 8. Architecture and infrastructure

| Term | Meaning |
|---|---|
| **LLMClient / providers** | `core/llm_client.py`. One interface, `LLMClient.complete()`, with three providers: `ClaudeProvider` (Anthropic API), `OllamaProvider` (local models), `ClaudeCodeProvider` (the `claude` CLI). Selected by `LLM_PROVIDER` (`claude_api`, `ollama_api`, `claude_cli`). |
| **Per-phase LLM routing** | EPIC-27. Each phase (pre-filter, 1, 2, 3, 3.5, 4) can run on its own provider, model and effort instead of one global setting. |
| **Prompt caching** | The profile is sent as a cached system prompt through `ClaudeProvider`, which cuts cost. Skipped for Ollama, which has no caching. |
| **Adapter / contract** | Adapters (`adapters/`) are the only way to call external services. Contracts (`contracts/`) are the typed Pydantic models adapters return, never raw dicts. |
| **Profile contract** | The named profile sections the engine files read (Settings, Name variants, Contacts line, Certifications, Languages, Archetype & Role Positioning, Experience, Generation Rules, CV cutoff year, AI Tooling Paragraph, Vacancy Preferences). `tests/test_profile_contract.py` checks that every local `pm` profile has them and that the engine still mentions each, so a profile restructure cannot silently break the references. |
| **Deterministic vs cognitive** | EPIC-21 principle. Work with one right answer (PDF render, metrics, scoring, status updates) lives in Python; judgment stays with the LLM. |
| **pdf-service** | `services/pdf/`, a FastAPI service (port 8002) that renders Markdown to PDF for CVs and covers. |
| **jd-parser** | `services/parser/`: URL to JD Markdown for Djinni and DOU, plus the salary estimator. |
| **RSS watcher** | `core/rss_watcher.py`. Polls job feeds, seeds the DB, starts the fire-and-forget fetch and probe tasks, and sends the Telegram push. |
| **Telegram push-only** | Telegram only notifies about new vacancies. It has no incoming handlers (the Router and FSM were removed on 2026-07-08). |
| **FastAPI backend** | `web/api.py`, port 8080. Serves the vacancy list and actions to Flutter; `/api/health` reports liveness. |
| **Flutter app** | The primary desktop UI (`flutter/`). Polls the backend for the vacancy list and filters it into the five stage tabs. |
| **Details header / action bar** | `_JdModeView` (before analysis) and `_ActionBar` (after analysis) in `vacancy_detail_screen.dart`. Two widgets treated as one template: any change to a shared element must be made in both. |
| **Offline cache** | The Flutter status line "Offline · cache from N min ago" means the last list poll failed and the app shows its cached list. The backend can be healthy at the same time, for example when one malformed record breaks parsing of the whole list. |
| **Isolated (blind) agent run** | A subagent started with no conversation context, given only the files a fresh run would read. Used to validate prompts without the author's knowledge leaking into the result. |
