# Hiring is broken. You can fix your side.

**Career Agent** — *For your next career move*

Job search has become needlessly hard. Employers bury their real pain inside generic JDs. Candidates fire off generic CVs hoping something lands. Both sides drown in noise.

**Our belief:** a good match is a conversation of relevance. The employer states the problem they need solved. The candidate understands it and responds with their strongest, most relevant evidence.

**Today** Career Agent serves the candidate side: it reads the employer's real intent out of the JD, judges honest fit, and surfaces the candidate's strongest relevant story — or tells them to walk away.

**North star:** close the loop on both sides, so employers and candidates reach the most relevant offers to each other.

---

## Who it's for

**Primary ICP:** PdM (Product Manager) · PO (Product Owner)
**Extended ICP:** PM (Project Manager) · BA (Business Analyst) · other non-technical roles

Core focus is PdM / PO: fit analysis understands product archetypes (Delivery vs Discovery, Execution vs Founder Proxy), evaluates product-specific experience signals, and adapts CV framing to what the role actually needs. PM, BA, and adjacent roles supported via `skill_type: generic` prompts.

---

## The Problem

Job seekers spend hours tailoring CVs **before** knowing if they're even a strong candidate.

Most tools help you write faster. This system answers two questions, in order:

1. **Should you apply?** — an honest read of the vacancy and your real fit. Weak odds → it tells you to skip.
2. **How do you win this one?** — if worth it, a CV that puts your strongest, most relevant sides forward.

The leverage is your profile: onboard once, and Career Agent turns deep JD analysis into a winning pitch — automatically, for every vacancy.

---

## Product Vision

**Career Agent is a focused vertical service** — purpose-built for PM job search. Tight pipeline by design: each phase solves a specific problem for the job seeker, nothing more.

---

## How it works

**1. JD Extraction** — automatic via RSS push, or manual (URL / JD paste in Telegram).

**2. Deep Analysis (Phase 1)** — employer's real pain, hidden requirements, role archetype, **VScore** (vacancy attractiveness, 8 dims).

**3. Fit Scoring (Phase 2)** — Fit × VScore matrix → verdict: `apply` · `take a chance` · `decline`. Key Barriers + Adaptation Plan. `decline` → pipeline stops, no CV wasted.

**4. Objection Handling (Phase 2.5)** — if barriers exist: resolve gaps interactively before writing anything. Resolved evidence saved to PROFILE.md.

**5. CV Draft (Phase 3, hidden)** — tailored to JD pain and Adaptation Plan.

**6. Self-Review (Phase 3.5)** — word frequency check, tools gap, tone vs archetype. First time user sees the CV.

**7. Approval → CV.pdf → Telegram**

**8. Cover Letter (Phase 4)** — two variants (narrative + bullets), user picks.

### Diagrams

| | |
|-|-|
| [User Journey](docs/diagrams/user-journey.md) | RSS → Telegram → approve/skip flow |
| [AI Pipeline](docs/diagrams/ai-pipeline.md) | 6-phase pipeline — VScore, Fit × VScore, decision gates |
| [Architecture](docs/diagrams/architecture.md) | Service topology — career-agent · parser · pdf · job-monitor |
| [System Flow](docs/system-flow.md) | Full decision logic end-to-end |

---

## Product Decisions

| Decision | Alternative | Reason |
|----------|-------------|--------|
| **PdM / PO as primary ICP** (PM, BA as extended) | Serve all roles equally | PdM / PO job search has role-specific archetypes (Founder Proxy vs Executor, discovery vs delivery bias), domain signals, and lexicon that generic tools miss. Vertical depth beats horizontal breadth. PM and BA supported via generic skill_type — not the core optimization target. |
| **Decision-first pipeline** — analyze fit before generating anything | Generate CV for every vacancy | Effort should follow a go/no-go verdict, not precede it. Don't optimize a document the user shouldn't send. |
| **RSS-first workflow** — jobs are pushed to the user | Manual vacancy search | Users should *evaluate* opportunities, not spend time *finding* them. |
| **Telegram as primary UI** | Web app / dedicated client | Zero install, already in the user's pocket, native push + inline approve/skip buttons. The interaction is decisions, not browsing. |
| **Channel-agnostic architecture** | Telegram-only forever | Telegram is primary today (CIS/EU). PWA and WhatsApp added as adapters when needed — tools layer unchanged. |
| **Monorepo — all services inside** | Permanent external dependencies | All user-built services live inside `services/`. Audit before migrating — cut dead code, keep only what the pipeline needs. |
| **Human-in-the-loop on irreversible steps** | Full auto-apply | The user owns the apply/skip and CV-approval calls. Automation removes toil, not judgment. |

---

## Architecture

→ [Architecture diagram](docs/diagrams/architecture.md)

| Layer | Tech |
|-------|------|
| AI | Claude Sonnet 4.6 · PydanticAI · prompt caching (profile + all phase prompts) |
| UI | Telegram (aiogram 3.x) · Web tracker (FastAPI + HTMX) |
| HTTP | httpx async |
| Storage | SQLite + filesystem |
| Deploy | Docker Compose — career-agent · services/ |
