# career-agent — Glossary

> Project-wide vocabulary, one line per term. The prompts and code stay the source of truth for the rules; this file only fixes what each word means so the same term is not used for two things.
> Currently covers the North Star Signal Tree terms (moved here from `docs/discovery/north-star-signal-tree-discovery-2026-09-21.md` on 2026-10-04). Add new terms here, not in individual discovery docs.

## North Star Signal Tree

| Term | Meaning |
|---|---|
| **North Star** | The single sentence stating what result the company is buying with this hire (`[role] must [action] so that [outcome]`), or an honest "not found". Searched in `phase1_analysis.md` §1.0.5 Stage 1. Requirements & Qualifications outweigh Key Responsibilities when looking for it. |
| **Trunk** | The design-time name for the North Star. The prompts use "North Star"; "trunk" appears only in the early sections of the discovery doc. |
| **Branch** | One distinct cluster of JD requirements hanging off the North Star. One branch = one distinct function or ask; bundles are split in Phase 1 Stage 2, not later. |
| **Central / secondary** | Phase 1's judgment of whether a branch belongs to the North Star's own core or only supports it. `no North Star` when none was found. A judgment call, not a count or a position in the text. |
| **Branch weight** | Two independent judgments combined: JD-centrality (Phase 1) and candidate-distinctiveness (Phase 2). Neither is a formula. |
| **Distinctive?** | Phase 2's direct question per signal: would most competing candidates for this exact role also credibly claim this evidence, or is it hard for them to match? |
| **Lead signal** | The branch that is both `central` and has `Distinctive = yes` evidence in the profile. The CV leads with it. If none qualifies, the honest output is "No strong differentiator identified". |
| **Bold-signal** | Check of the JD for selective bold emphasis: if the author bolded only some items, attention shifts to them. Bolding every item by template is not a signal. Rule lives in `phase1_analysis.md` §1.0.5 Stage 1. |
| **Unlock condition** | A usage condition written on a profile fact (rare / default-omit / "include only when…"). Phase 2 checks it by the type of work the JD asks for, never by a shared word. |
| **JD-echo** | CV phrasing lifted from the JD's own wording instead of composed from the candidate's evidence. Caught mechanically by `detect_jd_echo()` and by Phase 3.7. |
| **Weak-signal overfit** | Pairing a low-importance, single-mention JD word with a narrow profile fact just because the words match. |
