# Skill Types — Comparison Reference

> Reference: what's in PM skill vs Generic skill.
> Use when designing new skill types or adding prompts.

---

## PM Skill vs Generic Skill

| Компонент | PM Skill | Generic Skill | Generic: нет |
|-----------|----------|---------------|--------------|
| **Phase 1 — Role Archetype** | Founder proxy / Platform PM / Feature PM / Technical PM / Growth PM / Delivery-coordinator | Executor / Coordinator / Specialist / Strategist | ❌ PM-specific archetypes |
| **Phase 1 — Role Balance** | Strategy / Discovery / Execution / Stakeholder / Ops | Research-Analysis / Execution / Coordination / Operational | ❌ Discovery % как PM-концепция |
| **Phase 2 — Archetype mismatch** | Blocker если JD ищет Founder Proxy, кандидат Executor | — | ❌ Archetype delta / dual-archetype concept |
| **Phase 2 — Fit criteria** | PM domain: roadmap, discovery, delivery ownership | Role requirements: domain match, experience level, hard skills | ❌ PM-domain expertise как критерий |
| **Phase 2 — Adaptation** | Archetype reframing (surface founder/executor evidence) | Generic positioning: highlight most relevant experience | ❌ Archetype-based reframing |
| **CV — AI tooling paragraph** | Включается при AI/digital signal в вакансии | — | ❌ AI tooling paragraph |
| **CV — Skills section** | ❌ Никогда (PM convention) | ✅ Включается если релевантно (EA, SWE, Design) | |
| **CV — GitHub portfolio** | Если релевантно | — | ❌ GitHub по умолчанию |
| **Quick Scan — Category** | PM archetype label | Role type label | ❌ PM-specific label vocabulary |
| **Jargon rule** | PM/HR jargon: скрин, оффер, онбординг, пайплайн | HR jargon только: скрин, оффер, онбординг | ❌ Product jargon (бэклог, роадмап, спринт) |

---

## Skill Types Registry

| skill_type | Описание | Prompts folder | Статус |
|------------|----------|----------------|--------|
| `pm` | Product Manager / Product Owner / Product Director | `prompts/pm/` | ✅ Active |
| `generic` | EA, Admin, Operations, Sales, Design, любая не-PM роль | `prompts/generic/` | 🔧 In progress |

---

## Universal Components (все skill types)

Фазы и компоненты, которые **не меняются** между skill types:

- Phase 1: Company Pain Points
- Phase 1: Company Maturity Signals
- Phase 1: Expectations Analysis (1.5)
- Phase 1: Language Analysis (1.6)
- Phase 2: Fit Breakdown table (структура)
- Phase 2: Quick Scan (структура, кроме Category label)
- Phase 3: CV rules (все, кроме AI tooling и Skills section)
- Phase 3.5: CV Self-Review
- Phase 4: Cover Message

Файлы: `prompts/phase3_cv_draft.md`, `prompts/phase3_5_review.md`, `prompts/phase4_cover.md`

---

## Adding a New Skill Type

1. Create `prompts/[skill_type]/phase1_analysis.md`
2. Create `prompts/[skill_type]/phase2_fit.md`
3. Add entry to this table
4. Set `skill_type: [type]` in user's PROFILE.md → `## Settings`
5. Update `/analyze` command to route by `skill_type`
