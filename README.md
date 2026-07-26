# Career Agent

**AI job search counselor for PdM · PO**

> Personal tool, actively evolving as I use it in my own job search.

Reads vacancies deeply, scores honest fit, and generates targeted CVs — so candidates apply to the right roles and win them.

---

![Career Agent — Flutter Desktop UI](docs/screenshots/Flutter%20Main%20Screen.png)

---

## Who it's for

**Primary target user:** PdM (Product Manager) · PO (Product Owner)
**Also supports:** PM (Project Manager) · BA (Business Analyst) · other non-technical roles

Core focus is PdM / PO: fit analysis understands product archetypes (Delivery vs Discovery, Execution vs Founder Proxy), evaluates product-specific experience signals, and adapts CV framing to what the role actually needs. PM, BA, and adjacent roles supported via `skill_type: generic` prompts.

---

## The Problem

An active search means evaluating 30–100 vacancies. Most candidates decide emotionally — real barriers get missed, wrong roles get pursued. Then 30–90 minutes per CV, often wasted.

Real example: self-assessed at 10/10 fit → system returned 4/10. Delta = 6 points, one hidden requirement.

---

## Product Vision

Career Agent builds a picture of the candidate — through structured onboarding, LinkedIn/CV data, and evidence surfaced during the pipeline. That knowledge compounds with every session.

When fit is real: a targeted CV from actual experience, cross-checked against the vacancy's requirements, delivered as PDF. No fabricated claims. The user approves — or requests edits. Everything else is automated.

**Candidates spend time on decisions, not on writing.**

---

## How it works

**1. JD Discovery & Extraction** — automatic via RSS push, or manual (URL paste in Flutter).

**2. Deep Analysis (Phase 1)** — employer's real pain, hidden requirements, role archetype, **VScore** (vacancy attractiveness, 8 dims).

**3. Fit Scoring (Phase 2)** — Fit × VScore matrix → recommendation: `apply` · `take a chance` · `decline`. Key Barriers + Adaptation Plan. `decline` → pipeline stops, no CV wasted.

**4. Objection Handling (Phase 2.5)** — if barriers exist: resolve gaps interactively before writing anything. Resolved evidence saved to PROFILE.md.

**5. CV Draft (Phase 3, hidden)** — tailored to JD pain and Adaptation Plan.

**6. Self-Review (Phase 3.5)** — word frequency check, tools gap, tone vs archetype. First time user sees the CV.

**7. Approval → CV.pdf** — preview in Flutter, PDF download.

**8. Cover Letter (Phase 4) → Cover.pdf**

### Diagrams

| | |
|-|-|
| [User Journey](docs/diagrams/user-journey.md) | RSS → auto-analysis → Flutter → approve/skip flow |
| [AI Pipeline](docs/diagrams/ai-pipeline.md) | 6-phase pipeline — VScore, Fit × VScore, decision gates |
| [Architecture](docs/diagrams/architecture.md) | Service topology — career-agent · parser · pdf · job-monitor |
| [System Flow](docs/system-flow.md) | Full decision logic end-to-end |

### Project docs

| | |
|-|-|
| [Backlog](docs/delivery/BACKLOG.md) | Active work — Now / P0–P2 / Bugs / Icebox + epics overview |
| [Changelog](docs/delivery/CHANGELOG.md) | Delivered features, reverse-chronological |
| [Epics](docs/delivery/Epics/) | Design specs for epic-sized work |
| [Documentation conventions](docs/delivery/documentation-conventions.md) | How backlog / changelog / epics are maintained |

---

## Product Decisions

| Decision | Alternative | Reason |
|----------|-------------|--------|
| **PdM / PO as primary target user** (PM, BA also supported) | Serve all roles equally | PdM / PO job search has role-specific archetypes (a ten-label taxonomy — Founder Proxy, Executor, Discovery-heavy, Platform/Systems PM, Growth PM, and others, combinable in pairs), domain signals, and lexicon that generic tools often miss. Vertical depth beats horizontal breadth. PM and BA supported via generic skill_type — not the core optimization target. |
| **Decision-first pipeline** — analyze fit before generating anything | Generate CV for every vacancy | Effort should follow a go/no-go recommendation, not precede it. Don't optimize a document the user shouldn't send. |
| **RSS-first workflow** — jobs are pushed to the user | Manual vacancy search | Users should *evaluate* opportunities, not spend time *finding* them. RSS integration is deliberately scoped to a couple of popular job boards, not broad coverage — anything else goes in via manual paste, since wider integration isn't the current focus. |
| **Flutter Desktop as primary UI** | Telegram bot / web app | Local desktop app: zero hosting, zero HTTPS, no external dependency. Same Flutter codebase compiles to Web and Mobile later — no rewrite. RSS → auto-analysis → system tray notification → user opens app and decides. |
| **Telegram → push-only, then removed** | Telegram as permanent UI | Telegram stays for push notifications during Flutter MVP phase. Removed in Phase D — the interaction model moves to Flutter entirely. |
| **Monorepo — all services inside** | Permanent external dependencies | All user-built services live inside `services/`. Audit before migrating — cut dead code, keep only what the pipeline needs. |
| **Human-in-the-loop on irreversible steps** | Full auto-apply | The user owns the apply/skip and CV-approval calls. Automation removes toil, not judgment — and unattended, uncontrolled API calls are a real cost risk this design deliberately avoids. |

---

## Architecture

→ [Architecture diagram](docs/diagrams/architecture.md)

| Layer | Tech |
|-------|------|
| AI | Claude (Anthropic API) · local models via Ollama · PydanticAI · prompt caching |
| UI | Flutter Desktop (primary) · Web tracker (FastAPI + HTMX, read-only) |
| Backend | FastAPI — JSON endpoints for Flutter (`/api/vacancies`, `/api/vacancies/{id}/analysis`, `/api/vacancies/{id}/cv`) |
| HTTP | httpx async (backend) · http (Flutter) |
| Storage | SQLite + filesystem |
| Deploy | Docker Compose — career-agent · services/ |
