# /analyze — Career Agent Pipeline

Single entry point for the local CV pipeline.
Handles mode selection, user selection, and pipeline start in one command.

---

## Step 0 — Combined menu (always first)

**Every `/analyze` run begins here** — ONE message, two blocks, no round-trip.
Mirrors the `-v` combined display: Block 1 = profile/mode (`1–10`), Block 2 = actions (`11–20`).

**Before displaying — scan inbox** (populates Block 2):

```bash
python scripts/inbox_scan.py --user-id [user_id] --json
```

Read `skill/active_user` → ID → `skill/users.yaml` → name + slug. Then display **both blocks side by side — vertical split (columns), NOT a horizontal ━━━ divider**:

```
👤 Alex Bondarenko (alex) · [режим ещё не выбран] · 📄 Markdown

  Профиль / Режим              │   📥 Inbox — N вакансий
  ─────────────────────────    │   ──────────────────────────────
  [1] Локально (Claude Code)   │   [11] Role — Company 🆕
  [2] API (расход токенов)     │   [12] Role — Company ♻️
  [3] Другой профиль (-u)      │   [13] обработать все (batch)
  [4] Профиль: Markdown        │   [14] пропустить inbox → новая
  [5] Профиль: DB              │   [15] Загрузить по URL
                               │   [16] Обновить inbox
```

Left column = Block 1 (`1–10`). Right column = Block 2 (`11–20`). `│` separates them.

**Profile source default:** `Markdown` (PROFILE.md). Header shows current source: `📄 Markdown` or `🗄️ DB`. Active profile source shown with `●`: `[4] ● Профиль: Markdown` or `[5] ● Профиль: DB`.

**If inbox empty — right column collapses to:**
```
  Профиль / Режим              │   📥 Inbox пуст
  ─────────────────────────    │   ──────────────────────────────
  [1] Локально (Claude Code)   │   [11] Загрузить новую вакансию
  [2] API (расход токенов)     │        — вставь JD или URL
  [3] Другой профиль (-u)      │   [12] Вакансия по ID
  [4] Профиль: Markdown        │        — введи номер
  [5] Профиль: DB              │
```

### Routing (numbering is unambiguous)

- **Answer 1/2** → set `MODE = local|api`. If an action wasn't also given → re-display Block 2 only ("Что обрабатываем?").
- **Answer 3** → show user list (same as `-l`), stop — user re-runs with `-u`.
- **Answer 4** → set `PROFILE_SOURCE = md`. Re-display Step 0 with updated header.
- **Answer 5** → set `PROFILE_SOURCE = db`. Re-display Step 0 with updated header.
- **Combined answer** (e.g. `1 5`, `2 11`, `1 5 11`) → set mode AND/OR profile source AND/OR act in one step. Preferred — kills the round-trip. Example: `1 5` = Локально + DB profile; `1 5 11` = Локально + DB + process first inbox item.
- **Answer 11–1X (a vacancy)** → process that inbox item. `[batch]` = all, `[skip→new]` = пропустить inbox, `[URL]` = вставь JD/URL → старт, `[refresh]` = пересканировать inbox_manual → перерисовать Block 2.
- **Answer 12 (inbox empty) / `[N+3]` (inbox with items) — "Вакансия по ID"** → ask user "Введи ID вакансии:". User replies with integer ID → proceed exactly as `/analyze -v [id]`: run `vacancy_track.py get --id [id]`, show vacancy combined menu. Not found → show `❌ Вакансия #[id] не найдена в DB.`
- **Action given without mode** → default `MODE = local` (most common). Show `[Локально]` in status lines.
- **Action given without mode** → default `MODE = local` (most common). Show `[Локально]` in status lines.

- Selected mode applies to **all phases and all inbox files** in this invocation.
- Display selected mode in all subsequent status lines: `[Локально]` or `[API]`.
- **Skip Step 0 for:** `-l` (list users), `-inbox` (list inbox only) — read-only, no pipeline.
- **`-v [id]`** has its own combined display (vacancy phase actions in Block 2) — see `-v` section.

---

## Flags

| Flag | Alias | Behavior |
|------|-------|----------|
| *(no args)* | | **Mode** → inbox → active user → load → start |
| `-n` | `-now` | Same as no args (explicit) |
| `-u [id\|slug]` | `-user [id\|slug]` | **Mode** → switch user → inbox → load → start |
| `-v [id]` | `-vacancy [id]` | **Mode** → load vacancy by DB id → continue pipeline → skip inbox |
| `-l` | `-list` | Show user list → stop (no pipeline, no mode ask) |
| `-pdf [name?]` | | Regenerate PDFs → stop (no pipeline, no mode ask) |
| `-inbox` | | Show inbox contents only → stop (no pipeline, no mode ask) |

---

## `-l` / `-list` — Show user list

Read `skill/active_user`, `skill/users.yaml`, scan `skill/users/` directory.

Display:

```
👥 Career Agent — пользователи

  ID    Name               Slug      Profile
  1     Alex Bondarenko    alex      ✅        ← активный
  2     Maria Beleshko     maria     ✅

/analyze -u [id|slug]   — переключить и начать
/analyze                — начать с активным
```

Profile status: `✅` if `skill/users/[id]/PROFILE.md` exists and non-empty. `⚠️ missing` if not.
Unregistered folders (on disk, not in yaml): show as `(unregistered)` — cannot switch until added to `users.yaml`.

Stop after display. Do not start pipeline.

---

## `-u` / `-user` — Switch user then start

Read `skill/users.yaml`. Match argument against `id` or `slug`.

**Not found:**
```
❌ Пользователь "[arg]" не найден.
Запусти /analyze -l для списка.
```
Stop.

**Found — switch:**
Write new ID to `skill/active_user` (overwrite, one line, no trailing spaces).

```
✅ Переключено: [name] ([slug])
```

Then proceed to **Load & Start** below.

---

## No args / `-n` / `-now` — Use active user

Run **Step 0** (profile + mode confirm) above — active user already known.

After mode selected → proceed to **Inbox check** → **Load & Start**.

---

## Load & Start

**Profile source** is set by `PROFILE_SOURCE` session variable (default: `md`).

### If `PROFILE_SOURCE = md` (Markdown — default)

1. Check profile: `skill/users/[id]/PROFILE.md` — must exist and be non-empty.

   If missing or placeholder:
   ```
   ⚠️ Профиль не заполнен: skill/users/[id]/PROFILE.md
   Заполни профиль и повтори команду.
   ```
   Stop.

2. Load `skill/SKILL.md` — pipeline rules and orchestration.
3. Read `skill/users/[id]/PROFILE.md` into context — candidate profile.

4. Display:
   ```
   ✅ [name] — профиль загружен [📄 Markdown].
   Загружай вакансию: вставь текст JD или дай URL.
   ```

### If `PROFILE_SOURCE = db` (DB profile)

1. Read `progressive_profile` from DB:
   ```bash
   python -c "import sqlite3,json; db=sqlite3.connect('db/agent.db'); r=db.execute('SELECT progressive_profile FROM users WHERE id=?',([user_id],)).fetchone(); print(r[0] if r else '')"
   ```

   If NULL or empty:
   ```
   ⚠️ DB-профиль не заполнен для user_id=[id].
   Переключись на Markdown [4] или заполни DB-профиль.
   ```
   Stop.

2. Load `skill/SKILL.md` — pipeline rules and orchestration.
3. Parse `progressive_profile` JSON → inject into context as structured candidate profile.
   All phases use this instead of PROFILE.md for candidate experience/framing.
   Settings (language, skill_type, name variants) still read from `skill/users/[id]/PROFILE.md`.

4. Display:
   ```
   ✅ [name] — профиль загружен [🗄️ DB · N ролей].
   Загружай вакансию: вставь текст JD или дай URL.
   ```

5. Follow pipeline rules from `skill/SKILL.md` exactly.

---

## `-v [id]` / `-vacancy [id]` — Resume pipeline for existing vacancy

Look up vacancy in DB. Display **both blocks in one message** — no round-trip for mode confirmation.

```bash
python scripts/vacancy_track.py get --id [id]
```

**Not found:**
```
❌ Вакансия #[id] не найдена в DB.
Запусти /analyze для обработки новой вакансии.
```
Stop.

---

### Combined single-message display

Show **Block 1** (profile/mode — informational) and **Block 2** (vacancy actions — working) in one response.

**Numbering:**
- Block 1 items: **1–10** (change profile or mode)
- Block 2 items: **11–20** (pipeline actions for this vacancy)

Answer 1–10 → routes to Block 1. Answer 11–20 → routes to Block 2. Never ambiguous.

**Example output:**

```
👤 Alex Bondarenko (alex) · Локально

  [1] Сменить режим → API
  [2] Сменить профиль

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Вакансия #75 [Локально]

Product Manager (CRM) — JustMarkets Tech
https://djinni.co/jobs/829358-product-manager-srm
Создана: 2026-06-03

Выполнено:
  ✅ Phase 1+2 — анализ (fit 7/10, rec: apply)
  ✅ Phase 3+3.5 — CV (Alex Bondarenko, en, 0 правок)
  ✅ Phase 4 — cover (en)

Что делаем?
  [11] Повторить Phase 4 — новый cover
  [12] Повторить Phase 3+3.5 — новый CV
  [13] Повторить Phase 1+2 — новый анализ
  [14] Заново с нуля — Phase 1+2 → 3+3.5 → 4
```

---

### Block 1 — Profile/Mode (items 1–10)

Always exactly:
- `[1]` Сменить режим → [other mode] (if current = Локально → show API; if API → show Локально)
- `[2]` Сменить профиль

If user picks `[1]` → toggle MODE, re-display both blocks with updated mode header.
If user picks `[2]` → show user list inline (same as `-l`), ask to re-run with `-u`.

**In most cases user ignores Block 1** — profile and mode are already correct.

---

### Block 2 — Vacancy actions (items 11–20)

**Phase status rules:**
- `p2` in analysis_json → ✅ Phase 1+2 done (show fit_score + recommendation)
- `p3` in analysis_json → ✅ Phase 3+3.5 done (show name_variant + cv_language + changes_count)
- `p4` in analysis_json → ✅ Phase 4 done (show cover_language)
- Missing key → ❌ that phase not done

**Menu ordering:**
- `[11]` = first ❌ phase (if any). If none → `[11]` = Повторить Phase 4
- Remaining phases in reverse pipeline order
- Last item always = "Заново с нуля — Phase 1+2 → 3+3.5 → 4"

**After user selects — proceed directly to that phase:**
- Phase 1+2 → run Phase 1+2 (re-read JD.md; re-save JD_analysis.md)
- Phase 3+3.5 → ask name/language pre-flight → run Phase 3+3.5
- Phase 4 → run Phase 4
- "Заново с нуля" → Phase 1+2 silent → Quick Scan → "Генерируем CV?" → normal pipeline

**JD source for re-runs:**
- `[vacancy_folder]/JD.md` if exists
- Otherwise `JD_analysis.md` for context reconstruction
- If neither → ask user to paste JD

**Inbox check skipped entirely** when `-v` is used.

---

## `-pdf [name?]` — Regenerate all PDFs for a vacancy

Converts every eligible `.md` file in a vacancy folder to PDF.
**Eligible files:** `JD_analysis.md` + `*_CV.md` + `*_CV_UA.md` (covers excluded).

### No argument — show vacancy list

Scan `vacancies/` directory. List folders that contain at least one eligible `.md` file:

```
📄 Выбери вакансию для генерации PDF:

  1. AlphaNova — Junior Publishing Manager
       JD_analysis.md  →  JD_analysis.pdf
  2. Stripe — Product Manager
       JD_analysis.md  →  JD_analysis.pdf
       Alex_CV.md      →  Alex_CV.pdf

Введи номер или часть названия.
```

Wait for input. Then proceed.

### With argument — match vacancy folder

Match argument (partial, case-insensitive) against folder names in `vacancies/`.

**No match:**
```
❌ Вакансия "[arg]" не найдена. Запусти /analyze -pdf для списка.
```

**Multiple matches:** show filtered list, ask to clarify.

**One match — regenerate:**

For each eligible `.md` in the folder, render via the **pdf-service** (`services/pdf/`) — NEVER `../callback-cv/cv_to_pdf.py` (deprecated, external repo):
```bash
CAREER_AGENT_FONTS=fonts/ python -c "import sys,pathlib; sys.path.insert(0,'services/pdf'); from render import render_to_bytes; p=pathlib.Path('vacancies/[user_id]/[Company — Role]/[file].md'); p.with_suffix('.pdf').write_bytes(render_to_bytes(p.read_text(encoding='utf-8')))"
```
(Or POST the markdown to `http://localhost:8002/render` if the service is running.)

Report result:
```
📄 AlphaNova — Junior Publishing Manager

  ✅ JD_analysis.pdf
  ✅ Alex_CV.pdf
  ❌ Maria_CV.pdf — ошибка: [message]
```

Stop after report. Do not start pipeline.

---

## Inbox — Manual Vacancy Drop

**Folder:** `vacancies/inbox_manual/`
Checked automatically on every `/analyze` run (before loading profile).

### `-inbox` — Show inbox contents only

Run the canonical scanner (human output), then stop:

```bash
python scripts/inbox_scan.py --user-id [user_id]
```

```
📥 Inbox — vacancies/inbox_manual/ (N шт.):

  1. Role — Company   🆕 новая
  2. Role — Company   ♻️ уже обработана

/analyze      — запустить с активным профилем
/analyze -u   — запустить с другим профилем
```

Stop after display.

### Auto-check on `/analyze` (no args, `-n`, `-u`)

**Inbox scan is part of Step 0** — it populates Block 2 of the combined menu.
There is **no separate mode-then-inbox round-trip**. This section is the detail of Block 2.

> ⚠️ **inbox = папки, не плоские файлы.** Drops лежат как `inbox_manual/Role — Company/<jd>.md`.
> НЕ сканируй через `ls`/`find` руками — нерекурсивный `ls` пропустит подпапки.
> Каноническая команда scan (рекурсивная + dedup, единая точка истины):

```bash
python scripts/inbox_scan.py --user-id [user_id] --json
```

1. Run `scripts/inbox_scan.py --user-id [user_id] --json` — returns array of drops
   (each: `title`, `source_url`, `file`, `raw_folder`, `seen`, `seen_path`).
   Dedup already done per item (`seen`/`seen_path` = match in `vacancies/inbox/{user_id}/*/JD.md`).
2. **Empty array** → Block 2 = `[11] Загрузить новую вакансию`. Proceed to load & start.
3. **Items found** → render as Block 2 (`11` = first vacancy, `12` = second, … `[N+11]` = batch, last = skip→new).
   Per-item `seen` handling:
   - Already seen → Sequential: ask skip/reprocess · Batch: skip silently, mark `♻️ уже обработана`
   - `raw_folder` → exact arg for `vacancy_track.py delete-inbox --folder` after processing
4. Block 2 menu (rendered inside the Step 0 combined message):

```
📥 Inbox — N вакансий:
  [11] Role — Company 🆕
  [12] Role — Company ♻️
  [13] обработать все (batch)
  [14] пропустить inbox → новая вакансия
  [N+1] Загрузить по URL — вставь JD-ссылку или текст
  [N+2] Обновить inbox — пересканировать inbox_manual
  [N+3] Вакансия по ID — введи номер
```

   Multi-select inbox items via any separator: `11`, `11,12`, `11 12`.

   **[N+1] Загрузить по URL:** пользователь вставляет URL или текст JD → pipeline стартует как для новой вакансии.
   **[N+2] Обновить inbox:** пересканировать `inbox_manual/` и перерисовать Block 2 с актуальным списком. Полезно если пользователь только что дропнул файл.
   **[N+3] Вакансия по ID:** спросить "Введи ID вакансии:" → юзер вводит номер → proceed as `-v [id]`.

5. Profile is fixed by `active_user` / `-u` — never re-ask it here.
   *(mode handled by Block 1 — do not ask separately)*

6. **Choose processing mode** based on selected count:
   - **1–2 vacancies** → Sequential mode (process one by one, full analysis shown per vacancy)
   - **3+ vacancies** → Batch mode (Phase 1+2 silent for all → consolidated table → ask to proceed)

   See `skill/SKILL.md` → "Batch Mode" and "Sequential Mode" for full step-by-step.

7. After all processed → "Продолжить с новой вакансией или завершить?"

**File naming tip:** name file `Company — Role.md` → used as vacancy folder name directly.

---

## Adding a New User

1. Create `skill/users/[id]/PROFILE.md` — fill with candidate profile.
2. Add entry to `skill/users.yaml`:
   ```yaml
   - id: "003"
     name: "Full Name"
     slug: "shortname"
   ```
3. Run `/analyze -u shortname` to switch and start.

IDs are sequential integers as strings (`1`, `2`, ...). Match DB `user_id` directly.
