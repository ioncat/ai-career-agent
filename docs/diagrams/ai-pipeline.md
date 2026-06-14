# AI Pipeline

Six-phase Claude API pipeline. All static system content — `PROFILE.md` and every phase prompt — is prompt-cached; only per-vacancy text (JD + prior-phase output) is charged at full rate.

Phase prompts are **skill-type-specific**: `PROFILE.md` carries a `skill_type` field (e.g. `pm`, `generic`) that routes all phases to `prompts/[skill_type]/`.

```mermaid
flowchart TD
    JD["JD.md"] --> P1["Phase 1 — Deep Analysis\nobjections · hidden requirements · archetype signal"]
    PROF["PROFILE.md\n🔵 prompt cache"] --> P1
    PROF --> P3

    P1 --> VS["VScore — Vacancy Attractiveness\n8 dims: tier · seniority · domain · remote · comp…"]
    P1 --> P2["Phase 2 — Fit Scoring\nFit × VScore matrix · Barriers · Adaptation Plan"]
    VS --> P2
    P2 --> QS["Quick Scan → Telegram\nFit / VScore / Verdict / Barriers / Warnings"]

    QS -->|"apply / take a chance"| P25["Phase 2.5 — Objection Handling\nresolve barriers before CV · updates PROFILE.md"]
    QS -->|"decline"| Z["❌ Pipeline stops"]
    P25 --> P3["Phase 3 — CV Draft\nhidden from user"]
    P3 --> P35["Phase 3.5 — Self-Review\nword freq · tools gap · tone · Adaptation Plan check"]
    P35 --> PDF["CV.pdf → Telegram\nuser approves"]
    PDF --> P4["Phase 4 — Cover Letter → Telegram\ntwo variants · user picks"]
```

**3-way verdict:** `apply` · `take a chance` · `decline` — driven by Fit × VScore matrix  
**VScore (1–10):** vacancy attractiveness — company tier, seniority, market scope, domain fit, remote policy, compensation  
**Fit Breakdown:** per-requirement ✅/⚠️/❌ — pet-projects never equal commercial experience  
**Archetype-aware:** Founder Proxy vs Executor signal → different CV framing per vacancy
