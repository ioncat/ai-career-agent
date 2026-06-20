# UI Screens — Career Agent Flutter Desktop

Design system: Material 3
Platform: Windows Desktop (Flutter)
Backend: FastAPI localhost (no auth, single user)

---

## Global Layout

```
┌─────────────────────────────────────────────────────┐
│  NavigationRail (72px)  │  Main Content Area        │
│                         │                           │
│  📥 Inbox          [3]  │  (active screen)          │
│  🔄 In Progress         │                           │
│  ✅ Applied             │                           │
│  🗃️ Archive            │                           │
│                         │                           │
│  ─────────────          │                           │
│  ⚙️ Settings           │                           │
└─────────────────────────────────────────────────────┘
```

NavigationRail items:
- **Inbox** — vacancies with Phase 1+2 done, user hasn't acted yet (`status=analyzed`)
- **In Progress** — CV generated, not yet applied (`status=cv_generated`)
- **Applied** — submitted CV (`status=applied`)
- **Archive** — declined or dropped (`status=declined`)
- **Settings** — app config

Badge on Inbox: count of unread (new since last seen).

Top bar (per screen):
- Screen title + vacancy count
- Refresh button (manual poll trigger)
- Last updated timestamp

---

## Screen 1 — VacancyInbox

Route: `/inbox` (default)

Purpose:
Primary working screen. Shows analyzed vacancies. User decides: generate CV, decline, or move to archive.

Blocks:
- Toolbar: title "Inbox", count badge, Refresh button, Sort/Filter controls
- VacancyList: scrollable list of VacancyCard widgets
- EmptyState: shown when no vacancies in folder

VacancyCard fields:
- Role + Company (bold)
- Source badge (Djinni / DOU.ua / LinkedIn)
- Fit score chip (1–10, color-coded)
- VacScore badge (0–10, tier color)
- Recommendation chip (apply / take a chance / decline)
- Published date (relative: "2 дня назад")
- Key barrier preview (first item, truncated)

Actions per card:
- Tap → open VacancyDetail
- Swipe right / context menu → Move to Archive
- Long press → quick action menu

Sort options:
- По дате (default: newest first)
- По Fit score (desc)
- По VacScore (desc)

Filter:
- Recommendation: All / Apply / Take a chance / Decline
- Source: All / Djinni / DOU.ua / LinkedIn

Data:
- `GET /api/vacancies?status=analyzed&since={timestamp}`
- Fields used: id, role, company, site, fit_score, vacancy_score, recommendation, recommendation_label, published_at, key_barriers[0]

Rules:
- Polling every 30s via Timer; on new vacancies → Windows toast notification
- Manual Refresh button invalidates cache and re-fetches immediately

---

## Screen 2 — VacancyDetail

Route: `/vacancy/:id`

Purpose:
Deep read of Phase 1+2 analysis. User decides whether to proceed with CV generation.

Layout: single scrollable column, sections separated by dividers.

Blocks:

### Header card
- Role title + Company
- Source link (opens browser)
- Published date
- Status chip

### Quick Scan panel
- Fit score: large number + dot-bar visualization (●●●●●○○○○○)
- VacScore: number + tier label (Premium / Solid / Limited)
- Recommendation chip (colored) + label ("apply — strong match")
- Category: e.g. "Execution-heavy Platform/Systems PM · Remote"

### Who they want
- 1–2 sentence summary from `who_they_want`

### Vacancy Score breakdown (collapsible)
8-dim table:
| Dimension | Score | Max |
- company_tier, seniority, market_scope, company_type, company_stage_fit, domain_score, remote_policy, compensation

### Role Balance (collapsible)
- Horizontal bar chart: Strategy / Discovery / Execution / Stakeholder / Operational

### Fit Dimensions (collapsible)
6-dim table: domain_fit, execution_fit, strategy_fit, systems_fit, stakeholder_fit, overall_fit

### Barriers section
- Key Barriers list (⚠️ per item)
- Hidden Risks list (🔴 per item)
- Warnings list (💡 per item)

### Bottom action bar (sticky)
- [Generate CV] — primary action → navigates to CVGeneration
- [Decline] — moves to Archive
- [Open JD] — opens source URL in browser

Data:
- `GET /api/vacancies/{id}/analysis`
- Full AnalysisJson: p1 (role, company, north_star, vacscore_dims, vacancy_score, role_balance, dominant_culture), p2 (fit_score, recommendation, recommendation_label, category, who_they_want, key_barriers, hidden_risks, warnings, fit_dimensions)

Rules:
- If p2 is null → show "Analysis in progress" skeleton
- Collapsible sections default: Barriers open, dims collapsed

---

## Screen 3 — ObjectionHandling (Phase 2.5)

Route: `/vacancy/:id/objections`

Purpose:
Interactive barrier resolution before CV generation. User responds to each Key Barrier — responses feed into CV draft.

Blocks:
- Progress indicator: "Barrier 1 of N"
- Barrier card: barrier text (bold) + context from JD
- Response input: multiline text field ("Как вы это закрываете?")
- [Next] / [Skip] buttons
- Final screen: Adaptation Brief (AI-generated summary of resolved objections)

Actions:
- Submit response per barrier → POST to backend (Phase 2.5)
- Skip barrier → mark as unresolved
- View Adaptation Brief → collapses into VacancyDetail as extra section
- [Proceed to CV] → navigates to CVGeneration

Data:
- Barriers from `analysis_json.p2.key_barriers`
- POST `/api/vacancies/{id}/objection` (Phase 2.5 — not yet implemented in backend)

Rules:
- Only accessible when p2 exists and key_barriers non-empty
- Can be skipped entirely → goes straight to CV generation

---

## Screen 4 — CVGeneration

Route: `/vacancy/:id/cv`

Purpose:
Trigger Phase 3+3.5 (CV draft + self-review). Preview result. Download PDF.

Blocks:

### Pre-flight panel (before generation)
- Name variant input (default from profile)
- Language selector: EN / UA / Both
- [Generate CV] button

### In-progress state
- Linear progress indicator
- Status text: "Phase 3: drafting CV..." / "Phase 3.5: self-review..."
- Elapsed timer

### Result panel (after generation)
- CV.md rendered as formatted text (Markdown viewer widget)
- Download PDF button → triggers PDF render via backend
- Regenerate button (re-runs Phase 3+3.5)
- [Generate Cover Letter] → navigates to CoverLetter

Data:
- `GET /api/vacancies/{id}/cv` — cv_md, cover_md, pdf_available
- `POST /api/vacancies/{id}/generate` (Phase 3+3.5 trigger — not yet in backend)
- PDF download: `GET /api/vacancies/{id}/cv/pdf`

Rules:
- If cv_md already exists → show result panel directly (skip pre-flight)
- Regenerate shows confirmation dialog ("Перезаписать существующий CV?")

---

## Screen 5 — CoverLetter

Route: `/vacancy/:id/cover`

Purpose:
View and regenerate Phase 4 cover letter.

Blocks:
- Cover.md rendered (Markdown viewer)
- Language selector: EN / UA
- [Regenerate] button
- [Copy to clipboard] button

Data:
- `GET /api/vacancies/{id}/cv` → cover_md field
- `POST /api/vacancies/{id}/cover` (Phase 4 trigger)

Rules:
- Only accessible after Phase 3 (CV must exist)

---

## Screen 6 — Settings

Route: `/settings`

Purpose:
App configuration.

Blocks:

### Connection
- API URL (default: http://localhost:8080)
- [Test connection] button → GET /health

### Polling
- Interval selector: 15s / 30s / 60s / 5m
- Enable desktop notifications toggle

### User
- Active user display (read from API)
- skill_type display

### About
- App version
- Backend version (from /health)

Actions:
- Save settings → persisted to SharedPreferences
- Test connection → shows OK / error inline

Data:
- SharedPreferences (local)
- `GET /health` for connection test

---

## Navigation Rules

App open → VacancyInbox (default)
NavigationRail tap → switch folder (no push, replace main content)
VacancyCard tap → push VacancyDetail onto main area
VacancyDetail [Generate CV] → push CVGeneration
CVGeneration [Generate Cover] → push CoverLetter

Back navigation: standard Flutter back button or breadcrumb in top bar.

---

## Status → Folder mapping

| DB status      | NavigationRail folder |
|----------------|-----------------------|
| queued         | hidden (fetching)     |
| fetching       | hidden (fetching)     |
| analyzed       | Inbox                 |
| cv_generated   | In Progress           |
| applied        | Applied               |
| declined       | Archive               |

---

## UI Principles

- Desktop-first: wide layout, NavigationRail not BottomNav
- No animations required for MVP
- Collapsible sections for information density
- Color-coded semantics: green/amber/gray for scores (not decorative)
- Markdown rendered natively (flutter_markdown)
- No login screen — single user, localhost

---

End.
