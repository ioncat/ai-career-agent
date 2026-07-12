---
name: career-agent-pipeline
description: >
  PM vacancy analyzer + tailored CV + cover message generator.
  Use when user provides a job description and wants: fit analysis, CV generation, cover message.
  Triggers on: "проанализируй вакансию", "сделай CV", "напиши кавер", "analyze vacancy",
  "tailor CV", "job fit", "cover message", "разбор вакансии".
---

# Career Agent — Claude Code Skill

> Local pipeline. Claude Code IS the agent. Writes to DB via `scripts/vacancy_track.py` → visible in web tracker.
> Phase prompts live in `prompts/`. This file is orchestration only.
> Active user: `skill/active_user` → ID → `skill/users.yaml` → `skill/users/[id]/PROFILE.md`.

---

## Language Rules

**Output language** (user communication + JD_analysis.md):
1. Read `skill/users/[id]/PROFILE.md` → `## Settings` → `language` field
2. Default if not set: `en`
3. Apply to ALL output: user messages, analysis, internal sections — everything except CV/cover

- **CV language** — default = JD language (English JD → English CV, Ukrainian JD → Ukrainian CV). Final choice = user (pre-flight ask before Phase 3). User can override the default.
- **Cover language** = same as the approved CV language.

Default is derived from JD language, not from user language setting. But user always confirms or changes before CV is generated.

**Writing tone — authenticity rule (applies to ALL users, ALL languages):**
CV and cover prose must match the candidate's actual proficiency level in the target language. Check PROFILE.md → Languages for the candidate's level in the CV language.

If the candidate is NOT a native speaker of the CV language — do NOT write in native-fluent idiomatic prose.

Avoid:
- Idioms the candidate couldn't translate or verify themselves
- Complex native-speaker constructions that sound unnatural for a non-native writer
- Phrasing the candidate couldn't confidently stand behind in an interview

Prefer: simple, direct, professional sentences. A strong non-native professional writes clearly — not like a native impersonator.

Universal principle: never make the candidate appear to be something they are not. This applies to any language — English, Ukrainian, French, or otherwise.

---

## Pipeline Flow (NON-NEGOTIABLE)

```
Phase 1 + Phase 2  [run immediately on JD input, no confirmation needed]
  → Create folder vacancies/inbox/[user_id]/[Role — Company]/   [silent]
  → Save full output to JD_analysis.md   [silent — no confirmation needed]
  → Save p1+p2 to DB analysis_json       [silent — see Analysis JSON section below]
  → Update DB status → analyzed          [silent]

  ⛔ HARD RULE: JD_analysis.md MUST be written to disk BEFORE Quick Scan is shown to user.
     Quick Scan is derived from the saved file — never from memory or inline reasoning only.
     Violation = showing a conclusion without a saved source. Not acceptable.

  → Display in chat: Quick Scan block ONLY

  ↓ [if Key Barriers ≠ нет → Phase 2.5 Objection Handling FIRST — see section below]

  → Ask: "Генерируем CV?"

  ↓ [user confirms]

Pre-flight (ask once, before Phase 3):
  → CV language: ask only if JD ≠ English (English JD → English CV, obvious — skip)
  → Name variant: ask only if PROFILE.md → ## Name variants has more than one entry; single variant → use automatically, no ask

Phase 3: CV Draft          [NOT shown to user — internal]
Phase 3.5: Self-Review     [show to user, ask approval]
  → Ask: "Вносим правки или всё ок?"
  → Apply approved changes
  → Save [Name]_CV.md to existing folder (already created after Phase 1+2)
  → Generate PDF via http://localhost:8002/render → save PDF bytes
  → Save p3 to DB analysis_json          [silent — see Analysis JSON section below]

Phase 3.6: Signal Audit    [runs after save, shown to user]
  → Read saved CV (EXPERIENCE section) + Signal Coverage Table from JD_analysis.md
  → For each sentence: assess value vs JD requirements (valuable / weak / remove)
  → Check coverage: all high/medium signals present in at least one role?
  → Display audit report
  → If 🗑️ sentences found: confirm with user → remove → re-save CV.md + PDF
  → If ⚠️ only: present to user, they decide
  → If clean: proceed

  → Display full CV text
  → Ask: "Переходим к cover?"

  ↓ [user explicitly requests cover]

Phase 4: Cover Message
  → Review/approval cycle
  → Save [Name]_Cover.md
  → Generate PDF via http://localhost:8002/render → save [Name]_Cover.pdf
  → Save p4 to DB analysis_json          [silent — see Analysis JSON section below]
  → Display full cover text
```

**One question at a time. Never ask two questions in one message.**

**File operations — no permission ask.** Create `.md`, `.pdf`, `.json` files and write DB JSON (analysis_json via `vacancy_track.py update-json`) silently. Report what was created/saved after the fact. Never ask "Сохраняю?" before any of these operations.

**Phase completion report — MANDATORY after each phase.** After completing each phase, output a visually distinct block so the user can scroll and immediately see what was done:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 1+2 — Анализ завершён
Fit: N/10 · VScore: N.N · Рекомендация: [value]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 2.5 — Objection Handling завершён
Resolved: N/N · Genuine gaps: [list]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 3+3.5 — CV сгенерирован
[Name] · [language] · [N] правок · CV.md + CV.pdf
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 3.6 — Signal Audit
Clean / N sentences removed · CV.md + CV.pdf updated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Phase 4 — Cover готов
[language] · [вариант] · Cover.md + Cover.pdf
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Phase 2.5 — Objection Handling (barrier resolution)

**Runs between Quick Scan and "Генерируем CV?" — BEFORE any CV is drafted.**
Purpose: surface and resolve weaknesses first, so Phase 3 writes a CV armed with real counter-arguments — not a CV that silently ignores the blockers.

### Trigger

Run whenever Phase 2 **Key Barriers ≠ нет** (any non-empty barriers — includes strong `apply`, not only `take a chance`).
Skip only when: `decline` (not worth it) OR clean `apply` with zero barriers.

### Input

- Phase 2 **Key Barriers**
- **Fit Breakdown** ⚠️ / ❌ items
- **Adaptation Plan**

### Process

1. Present the weak points compactly as a numbered list — for each: the gap + what the JD actually demands.
2. Ask the candidate (one message, per-item): *"По каким из них есть реальный опыт, которого нет в профиле?"*
3. For each barrier, classify the answer:
   - **✅ Resolved** — candidate gives real evidence not yet in PROFILE.md → capture it.
   - **❌ Genuine gap** — confirmed absent → Phase 3 must NOT fabricate; handle honestly. Candidate may decide not to apply.
4. Summarize: resolved (with new evidence) vs genuine gaps. Then proceed to "Генерируем CV?".

### Output / persistence

- **Resolved evidence → append to `skill/users/[id]/PROFILE.md`** (grows the profile; future vacancies benefit). Add under the relevant Experience/Skills entry or a `## Additional evidence` block. Factual only — never fabricated.
- **Per-vacancy → append an `## Phase 2.5: Objection Handling` block to `JD_analysis.md`** (resolved + genuine gaps + decision).
- Pass resolved objections into Phase 3 context (CV must surface these counter-arguments).
- Optional DB: store under `analysis_json` key `p2_5` (`{resolved:[...], gaps:[...]}`).
- **DB Profile write-back (EPIC-24 T5)** — after summarizing resolved evidence, merge into `progressive_profile`:
  ```bash
  python scripts/profile_merge.py --user-id [id] --evidence "[resolved evidence text]"
  # Or write evidence to temp file first:
  # python scripts/profile_merge.py --user-id [id] --evidence-file /tmp/p25_evidence.txt
  ```
  Only call when ≥1 resolved barriers with real evidence. Skip if all barriers are genuine gaps.
  Use `--dry-run` to preview before saving.

### Nature (per EPIC-21)

Cognitive + interactive (dialogue + judgment) → stays LLM. The barrier-list scaffolding is deterministic. Prompt: `prompts/[skill_type]/phase2_5_objections.md`.

---

## Company Type Detection → Lexicon Adaptation (Phase 3 Pre-flight)

Before generating the CV draft (Phase 3), identify the target company type from the JD:

- **Enterprise** — large org, regulated, formal hierarchy, structured processes, compliance overhead
- **Scale-up** — Series B+, growing, semi-structured, some process maturity
- **Startup** — early-stage (seed/Series A), small team, product not yet defined, high ambiguity
- **Founder-led** — founder still actively running product/delivery, direct collaboration, strong opinions, low bureaucracy (can be any stage)

These are distinct. A Founder-led company can be Series C. A Startup without founder involvement can already feel corporate.

Adjust CV lexicon accordingly. Vocabulary signals company-context fit immediately to the reader.

| Context | Enterprise | Scale-up | Startup | Founder-led |
|---------|------------|----------|---------|-------------|
| Team | "distributed cross-functional teams" | "cross-functional squads" | "small autonomous team" | "worked directly with founders" |
| Process | "structured delivery", "governance", "milestone-based" | "scaled agile", "OKR-driven" | "built from scratch", "0→1" | "greenfield", "no prior process" |
| Decisions | "stakeholder alignment", "executive visibility" | "data-informed prioritisation" | "rapid iteration", "validated assumptions" | "direct founder collaboration", "full autonomy" |
| Growth | "operational efficiency", "process maturity" | "growth at scale" | "PMF", "early traction" | "founder vision → product reality" |

Use enterprise vocabulary when: large company, regulated domain, multiple stakeholder layers, formal org.
Use founder-led vocabulary when: JD mentions founders, "direct access", "flat structure", "early team" — even at larger orgs.

Store detected type as: `COMPANY_TYPE = enterprise | scaleup | startup | founder-led` in working context — used in Phase 3.5 tone check.

---

## How to Execute Each Phase

Load the prompt file, read it fully, then execute against the provided input.

All prompt paths: `prompts/[skill_type]/phaseN.md` — read `skill_type` from active user PROFILE.md → `## Settings`.
ALL phases are skill_type-specific. No universal phase files remain in prompts/ root.

| Phase | Prompt file | Input |
|-------|------------|-------|
| Phase 1 | `prompts/[skill_type]/phase1_analysis.md` | JD text + active user PROFILE.md in context |
| Phase 2 | `prompts/[skill_type]/phase2_fit.md` | JD text + Phase 1 output |
| Phase 2.5 | `prompts/[skill_type]/phase2_5_objections.md` | Phase 2 Key Barriers + Fit Breakdown ⚠️/❌ + Adaptation Plan |
| Phase 3 | `prompts/[skill_type]/phase3_cv_draft.md` | JD text + JD_analysis.md + language + name + **resolved objections** |
| Phase 3.5 | `prompts/[skill_type]/phase3_5_review.md` | CV draft + JD_analysis.md |
| Phase 3.6 | `prompts/[skill_type]/phase3_6_signal_audit.md` | Saved CV (EXPERIENCE) + Signal Coverage Table from JD_analysis.md |
| Phase 4 | `prompts/[skill_type]/phase4_cover.md` | JD text + approved CV + JD_analysis.md |

---

## File Saving Rules

**Vacancy folder:** `vacancies/inbox/[user_id]/[Role — Company]/`

Read `user_id` from `skill/active_user` → `skill/users.yaml` → `id` field (e.g. `1`).

```
vacancies/
├── inbox/                           ← системный (RSS, Telegram, API — только система)
│   └── [user_id]/
│       └── [Role — Company]/
│           ├── JD.md                    ← user drops here (or Claude saves from URL)
│           ├── JD_analysis.md           ← Phase 1 + Phase 2 output (auto-save, no confirmation)
│           ├── [Full Name]_CV.md        ← English CV — e.g. Alex Bondarenko_CV.md
│           ├── [Full Name]_CV_UA.md     ← Ukrainian CV (if generated)
│           ├── [Full Name]_CV.pdf       ← generated PDF
│           ├── [Full Name]_Cover.md     ← cover (English, no suffix)
│           └── [Full Name]_Cover_UA.md  ← cover (Ukrainian)
└── inbox_manual/                    ← пользователь дропает вручную
```

**[user_id]** — read from `skill/active_user`. Plain integer string: `1`, `2`, etc.
**[Role — Company]** — extracted from JD during analysis. Format: `Product Manager — Acme Corp`. Em dash ( — ).
**Folder name format:** `{vacancy_id} — {Role — Company}` — e.g. `405 — Product Manager — MWDN`. ID from DB (upsert first, then mkdir).
**DB title** — stores `Role — Company` only (without ID prefix).

**inbox_manual processed files** move to `vacancies/inbox/[user_id]/[Role — Company]/` — same standard.

**JD_analysis.md — always starts with Quick Scan header:**

```markdown
## Quick Scan

**Fit score:** X/10
**VScore:** X.X/10
**Recommendation:** apply / decline / take a chance
**Category:** [archetype from Phase 1]
**Who they want:** [1 sentence]
**Key Barriers:** нет / [list]
**Hidden Risks:** нет / [list]
**Warnings:** нет / [list]
```

Then: full Phase 1 analysis → full Phase 2 fit assessment.

**Recommendation logic:** blockers ≠ нет OR fit < 5 → `decline` always (VScore cannot override). No blockers + fit 5–6: VScore ≥ 7.5 → `take a chance — premium opportunity`; VScore < 5.5 → `decline — not worth the effort`. Fit ≥ 7 + VScore < 5.5 → `apply — limited upside`. DB stores base value only (`apply` / `take a chance` / `decline`).

**Re-analysis (Повторить Phase 1+2):** if `JD_analysis.md` already exists in the vacancy folder, save the new analysis to `[vacancy_folder]/Claude Desktop/JD_analysis.md` — never overwrite the original. Create the subfolder silently.

**Phase 3.5 self-review — append to JD_analysis.md after user approval:**

```markdown
---

## Phase 3.5: CV Self-Review

Date: [date]

[Full self-review output]

**Decision:** [Changes applied / No changes — approved as-is]
```

---

## PDF Generation

Render via the **pdf-service** (`services/pdf/`, live). **NEVER** `../callback-cv/cv_to_pdf.py` — deprecated, external repo, has the old un-fixed renderer.

**HTTP (service running on :8002):**
```bash
python -c "import httpx,pathlib; p=pathlib.Path('vacancies/inbox/[user_id]/[Role — Company]/[Full Name]_CV.md'); r=httpx.post('http://localhost:8002/render',json={'markdown':p.read_text(encoding='utf-8')},timeout=30); r.raise_for_status(); p.with_suffix('.pdf').write_bytes(r.content)"
```

**In-process (no server needed, always uses fresh render.py code):**
```bash
CAREER_AGENT_FONTS=fonts/ python -c "import sys,pathlib; sys.path.insert(0,'services/pdf'); from render import render_to_bytes; p=pathlib.Path('vacancies/inbox/[user_id]/[Role — Company]/[Full Name]_CV.md'); p.with_suffix('.pdf').write_bytes(render_to_bytes(p.read_text(encoding='utf-8')))"
```

Same service renders **CVs and covers** — `render_md` is cover-aware (CV header only when a contacts-links line is present).
**Note:** the HTTP service has no `--reload`; after editing `render.py`, restart it or use the in-process form.

---

## Name Selection (before Phase 3)

1. Read PROFILE.md → `## Name variants` section. Count entries.
2. **Single variant** → use automatically, no ask.
3. **Multiple variants** → ask user to choose.

**Decision matrix:**

| JD language | Name variants | Pre-flight ask |
|-------------|---------------|----------------|
| English | 1 | Nothing — proceed directly |
| English | Multiple | Name only |
| Non-English | 1 | Language only |
| Non-English | Multiple | Language + name together |

**Name-only ask (English JD, multiple variants):**
```
Какое имя использовать?
  [1] [variant 1]
  [2] [variant 2]
```

**Language + name together (non-English JD, multiple variants):**
```
На каком языке готовить CV?
  [1] English — [English name variant]
  [2] [JD language] — [local name variant]
  [3] Оба — English: [English name] + [JD language]: [local name]
```

**Language only (non-English JD, single variant):**
```
На каком языке готовить CV?
  [1] English
  [2] [JD language]
  [3] Оба
```

Option "Оба" → two CVs + two covers generated sequentially.

---

## Analysis JSON — Structured DB write per phase

**After Phase 1+2 — save p1 + p2:**

```bash
python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p1 --data '{
  "company_type": "startup|scaleup|enterprise|founder-led",
  "role_archetype": "[Primary archetype label from 1.4]",
  "role_balance": {"strategy": N, "discovery": N, "execution": N, "coordination": N, "ops": N},
  "autonomy": "high|medium|low",
  "dominant_culture": "ownership|speed|alignment|process|innovation|predictability",
  "vacancy_score": N.N,
  "vacancy_dims": {
    "company_tier": N,
    "seniority": N,
    "market_scope": N,
    "company_type": N,
    "company_stage_fit": N,
    "domain_score": N,
    "remote_policy": N,
    "compensation": N
  }
}'

python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p2 --data '{
  "fit_score": N,
  "recommendation": "apply|take a chance|decline",
  "category": "[category string from Quick Scan]",
  "key_barriers": ["short label 1", "short label 2"],
  "hidden_risks": ["risk 1", "risk 2"],
  "warnings": ["warning 1", "warning 2"],
  "salary": "$X–Y or empty string",
  "fit_dimensions": {"domain": N, "execution": N, "strategy": N, "systems": N, "stakeholder": N}
}'
```

**key_barriers format:** short labels only, max 5 words each — e.g. `["A/B testing", "consumer product", "PSP/POS integrations"]`. These appear as chips in the tracker.
**fit_score:** integer (7, not "7/10").
**warnings/hidden_risks:** array of short strings, or empty array `[]` if none.

**After p1+p2 saved — update status (MANDATORY):**

```bash
python scripts/vacancy_track.py update --id $VACANCY_ID --status analyzed
```

> **Почему MANDATORY:** без этого шага вакансия остаётся в статусе `fetching` в DB и трекере,
> даже если анализ выполнен и analysis_json сохранён. Баг обнаружен на вакансии #461 (Navis)
> — трекер показывал company=MONTE-PRO и status=fetching после полного pipeline.
> Этот шаг ранее существовал только в секции URL-flow (ниже), но отсутствовал здесь,
> и Claude Desktop его пропускал. Исправлено 2026-07-02.

**After Phase 3.5 approval — save p3:**

```bash
python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p3 --data '{
  "name_variant": "Alex Bondarenko",
  "cv_language": "en|uk|ru",
  "changes_count": N
}'
```

**After Phase 4 approval — save p4:**

```bash
python scripts/vacancy_track.py update-json --id $VACANCY_ID --phase p4 --data '{
  "cover_language": "en|uk|ru"
}'
```

---

## Step 0 — Combined menu (always first)

**Every `/analyze` invocation starts here** — ONE message, two blocks, **no round-trip**.
Mirrors the `-v` combined display: Block 1 = profile/mode (`1–10`), Block 2 = actions (`11–20`).

**Before displaying — scan inbox** (populates Block 2):

```bash
python scripts/inbox_scan.py --user-id [user_id] --json
```

Read `skill/active_user` → name + slug. Display **both blocks side by side — vertical split (columns), NOT a horizontal ━━━ divider**:

```
👤 Alex Bondarenko (alex) · [режим ещё не выбран]

  Профиль / Режим              │   📥 Inbox — N вакансий
  ─────────────────────────    │   ──────────────────────────────
  [1] Локально (Claude Code)   │   [11] Role — Company 🆕
  [2] API (расход токенов)     │   [12] Role — Company ♻️
  [3] Другой профиль (-u)      │   [13] обработать все (batch)
                               │   [14] пропустить inbox → новая
```

Left column = Block 1 (`1–10`). Right column = Block 2 (`11–20`). `│` separates them.

**Inbox empty → right column collapses to** `[11] Загрузить новую вакансию — вставь JD или URL`.

### Routing

- **1/2** → set `MODE = local|api`. If no action given too → re-display Block 2 ("Что обрабатываем?").
- **3** → show user list (same as `-l`), stop — re-run with `-u`.
- **11–1X** → process that inbox item · `[batch]` = all · `[skip]` = new vacancy.
- **Combined** (e.g. `2 11`, `1, 13`) → mode + action in one step. **Preferred — kills round-trip.**
- **Action without mode** → default `MODE = local`. Show `[Локально]` in status lines.
- Selected mode applies to **entire session** — all phases, all inbox files, everything.
- **Exception:** `-l` (list users) and `-inbox` (list inbox) → skip Step 0, read-only.
- **`-v [id]`** has its own combined display (vacancy phase actions in Block 2).

**After Step 0 → Step 2 (analysis).** (Inbox scan already done above — no separate Step 1.)

---

## Inbox — Manual Vacancy Drop

**Folder:** `vacancies/inbox_manual/`
**Purpose:** user drops JD files here manually; system picks them up on `/analyze`.

### Inbox scan — part of Step 0 (Block 2), not a separate step

Inbox scan runs **inside Step 0** and populates Block 2 of the combined menu.
**No separate mode-then-inbox round-trip.** This is the Block 2 detail.

> ⚠️ **inbox = папки, не плоские файлы.** Drops лежат как `inbox_manual/Role — Company/<jd>.md`.
> НЕ сканируй `ls`/`find` руками (нерекурсивный `ls` пропустит подпапки → ложное "пусто").
> Каноническая команда — единственный допустимый способ scan:
>
> ```bash
> python scripts/inbox_scan.py --user-id [user_id] --json
> ```
>
> Возвращает массив: `title`, `source_url`, `file`, `raw_folder`, `seen`, `seen_path`.
> Dedup уже сделан: URL → поиск в `JD.md` и `JD_analysis.md`; без URL → совпадение по имени папки в `vacancies/inbox/{user_id}/`.
> `raw_folder` → точный аргумент для `vacancy_track.py delete-inbox --folder`.

1. Run `scripts/inbox_scan.py --user-id [user_id] --json`
2. **Empty array** → Block 2 = `[11] Загрузить новую вакансию`
3. **Items found** → render as Block 2 (`11`=first vac, `12`=second, … `[batch]`, `[skip→new]`):

```
📥 Inbox — N вакансий:
  [11] Role — Company 🆕
  [12] Role — Company ♻️
  [13] обработать все (batch)
  [14] пропустить inbox → новая вакансия
```

   Multi-select via any separator: `11`, `11,12`, `11 12`.
   Profile fixed by `active_user`/`-u` — never re-ask. Mode handled by Block 1.

4. **Always use Batch mode** — regardless of vacancy count (1, 2, or more). Run all selected vacancies through Phase 1+2, then show consolidated table. Ask Phase 3+4 after table.

---

### Batch Mode (any count)

**Trigger:** any inbox selection — 1 vacancy, 2, or more.

**Flow:**

```
Обрабатываем N вакансий [Локально]...
```
*(single line, no per-vacancy progress — desktop app, result matters not the spinner)*

Run **Phase 1+2 silently** for every selected vacancy:
- **Dedup:** use `seen`/`seen_path` from `inbox_scan.py` output (no manual grep)
  - `seen: true` → **do NOT upsert** (vacancy already registered — creating a duplicate is wrong). Note as `♻️ уже обработана` in Ключевой gap column. Skip analysis entirely.
  - `seen: false` → proceed with full pipeline below
- Register in DB: `vacancy_track.py upsert --title "Role — Company"` → captures `$VACANCY_ID`
- Create folder `vacancies/inbox/[user_id]/[ID] — [Role — Company]/`
- Save `JD.md` (original JD text) to that folder
- Run Phase 1+2
- Save `JD_analysis.md` to `vacancies/inbox/[user_id]/[ID] — [Role — Company]/`
- Update DB: `vacancy_track.py update --id $ID --status analyzed --path ...`
- Save p1+p2 JSON: `vacancy_track.py update-json --id $ID --phase p1 ...` and `--phase p2 ...`

⚠️ **All DB writes must complete before table is shown.** The user checks the tracker while thinking — it must already reflect the results. Table = confirmation that tracker is current, not a preview.

```
📊 Batch анализ — N вакансий [Локально]

 #  Компания — Роль                        Src    Fit   Рекоменд.       Уровень / $     Ключевой gap
──────────────────────────────────────────────────────────────────────────────────────────────────
15  SOLAR Digital — AI PM                 DOU   7/10  ✅ Подавать       Mid/Senior      n8n (минор)
11  Oradian — Senior PM (AI)              LI    6/10  ✅ Подавать       Mid–Senior      Fintech = плюс, не требование
12  Pencil — Sr PM Biz Engineering        LI    5/10  ⚠️ Рассмотреть   Senior          API PM gap; 100+ заявок
 7  Alliance Digital — PM                 DJ    5/10  ⚠️ Рассмотреть   Mid, ~$3K       Banking gap; $3K потолок
 5  Kyivstar.Tech — Sr PM KIP             LI    4/10  ❌ Пропустить    Senior          Sr+telco+identity = 3 блокера
...

Рекомендовано к подаче: #15, #11
```

**Table rules:**
- Sort: ✅ first → ⚠️ second → ❌ last; within group by fit score DESC
- `Уровень / $`: extract from JD if mentioned (Senior/Mid, salary range) — show "—" if absent
- `Ключевой gap`: max 1–2 phrases, no full sentences
- Use folder name as `Компания — Роль` (no truncation)
- `Src`: DOU / LI / DJ / — (if unknown)

**After table — ask naturally (no buttons):**

```
Рекомендовано к подаче: #X, #Y.
Какие обрабатываем дальше?
```

Wait for free-form answer: numbers, names, "все рекомендованные", "пропустить".
Proceed with Phase 3+4 for selected vacancies.

> **Note:** "Approve / Try chance" button pattern is for Telegram/web/mobile UI surfaces.
> In local Claude Code mode — natural language only. No menu needed.

**After Phase 1+2 + table — delete raw inbox_manual folders** regardless of Phase 3+4 decision.
Clean `Role — Company/` folders already created under `vacancies/inbox/{user_id}/` during analysis — raw staging folders are no longer needed:
```bash
python scripts/vacancy_track.py delete-inbox --folder "RAW_FOLDER_NAME"
```
Run once per processed raw folder (exact name as it appeared in `inbox_manual/`).

6. After table → Phase 3+4 for selected → "Продолжить с новой вакансией или завершить?"

### File naming convention (recommended for user)

```
vacancies/inbox_manual/
└── Role — Company/           ← user drops folder here; cleared after processing
```

If filename contains ` — ` (em dash) → use as vacancy folder name directly.
Otherwise → extract company/role from JD content during analysis.

---

## `-v [id]` — Resume pipeline for existing vacancy

```bash
/analyze -v 75
/analyze -vacancy 75
```

Inbox check **skipped**. Display **both blocks in one message** — no round-trip for mode confirmation.

```bash
python scripts/vacancy_track.py get --id [id]
```

### Numbering scheme

- **Block 1 (1–10):** profile + mode — informational header, rarely changed
- **Block 2 (11–20):** vacancy pipeline actions — main working block

Answer 1–10 → Block 1 action. Answer 11–20 → Block 2 action. Never ambiguous.

### Display format

```
👤 Alex Bondarenko (alex) · Локально

  [1] Сменить режим → API
  [2] Сменить профиль

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Вакансия #[id] [Локально]

[title]
[url]
Создана: [created_at date]

Выполнено:
  ✅ Phase 1+2 — анализ (fit [N]/10, rec: apply)
  ✅ Phase 3+3.5 — CV ([name_variant], [cv_language], [changes_count] правок)
  ❌ Phase 4 — cover не сгенерирован

Что делаем?
  [11] Phase 4 — написать cover
  [12] Повторить Phase 3+3.5 — новый CV
  [13] Повторить Phase 1+2 — новый анализ
  [14] Заново с нуля — Phase 1+2 → 3+3.5 → 4
```

### Block 1 logic

- `[1]` toggle mode (Локально ↔ API)
- `[2]` change profile → show user list, ask re-run with `-u`
- If toggled → re-display both blocks with updated mode

### Block 2 logic

Phase done = key present in `analysis_json` (`p2` → Phase 1+2, `p3` → Phase 3+3.5, `p4` → Phase 4).

Menu order: first ❌ phase at `[11]`, then remaining phases in reverse order, last = "Заново с нуля".

**"Заново с нуля"** → Phase 1+2 silent → Quick Scan → "Генерируем CV?" → normal pipeline. Use after prompt/rule/SKILL.md changes.

**Re-analysis save rule:** when running "Повторить Phase 1+2" or "Заново с нуля" on a vacancy that already has `JD_analysis.md` — save new analysis to `[vacancy_folder]/Claude Desktop/JD_analysis.md`. Never overwrite original. Same rule applies in cv_analyze.py (Python pipeline).

**JD source:** `[vacancy_folder]/JD.md` → absent → `JD_analysis.md` → absent → ask user.

Vacancy folder = parent dir of `markdown_path` from DB record.

---

## Loading Context

**Entry point: `/analyze`** — always use this command to start.

**Per-user overrides:** after loading base `skill/SKILL.md`, also load `skill/users/[id]/SKILL.md` if the file exists. Personal rules (language scope, exclusions) live there and extend the base mechanics.

| Command | Action |
|---------|--------|
| `/analyze` | **mode** → inbox → active user → load → start |
| `/analyze -v [id]` | **mode** → load vacancy by DB id → continue pipeline → skip inbox |
| `/analyze -u [id\|slug]` | **mode** → switch user → inbox → load → start |
| `/analyze -l` | show user list → stop (no mode ask) |
| `/analyze -inbox` | show inbox contents → stop (no mode ask) |

Do NOT load `@skill/SKILL.md` manually without going through `/analyze` —
wrong profile may be loaded.

---

## Difference from Telegram Pipeline

| | Claude Code skill | Telegram bot |
|--|------------------|-------------|
| Trigger | `/analyze` or natural language | RSS auto-discovery |
| Profile | `skill/users/[id]/PROFILE.md` | DB (after onboarding) |
| DB writes | Yes — via scripts/vacancy_track.py | Yes |
| PDF | Direct subprocess | CVAdapter → HTTP |
| Multi-user | Yes — `users.yaml` + `active_user` + `/analyze -u` | Yes — DB |
| Use when | Quick analysis, no infra needed | Full production pipeline |
