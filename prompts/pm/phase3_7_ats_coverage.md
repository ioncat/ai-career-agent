# Phase 3.7: ATS Keyword Coverage (opt-in)

Runs after Phase 3.6 Signal Audit and before Phase 3.8 Editorial Audit, only when the user accepts the offer
(see Trigger). Goal: make sure the CV literally contains the JD's load-bearing terms wherever the profile
already holds real evidence for them. Automated screening matches literal words, and a synonym does not
count. This is the opposite goal to Phase 3.8's JD-Echo Risk check, which is why it runs first and hands
Phase 3.8 the list of terms it inserted (see Output).

---

## Trigger

Offered once, as a single question, after Phase 3.6. Runs only on a yes. Not run by default, not run in
`-lite`. It costs one extra model pass and not every vacancy needs it.

## Input

1. The saved CV (`.md`, after Phase 3.5 and 3.6).
2. The vacancy's `JD.md`.
3. The Signal Coverage Table from `JD_analysis.md`.
4. The profile (for the evidence lookup in Step 3).

## Step 1: Term list

Collect the JD's load-bearing terms: tools and platforms, methods and practices, domain nouns, named
artefacts, certifications. Take them from:
- the Requirements / Qualifications section;
- any term the JD mentions two or more times;
- Signal Coverage rows with importance high or medium.

A term is a word or a short phrase (one to three words) in the JD's own spelling. Skip boilerplate
(teamwork, communication), items the JD marks optional ("nice to have", "a plus"), and the role title
already carried by the headline. When the CV is written in a different language from the JD, use the term in
the CV's language, as its standard translation.

Requirements outweigh Responsibilities: a term that appears only under Responsibilities is skipped even if
it is repeated, and so is a Signal Coverage row that comes only from a Responsibilities line. Keep at most
15 terms, in this order: terms from Requirements, then high Signal Coverage rows, then medium rows, then
repeated terms.

## Step 2: Presence

For each term, check whether the CV contains it literally (case-insensitive; an inflected form of the same
word counts; an abbreviation counts only if the JD itself uses it). A synonym or a paraphrase does not. One occurrence is enough: never repeat a term to
raise its frequency.

## Step 3: Evidence for each missing term

Search the profile (every Experience block and the notes under it, the skills section) for real evidence of
the same thing under other words.

- **Evidence exists** -> propose inserting the literal term, using the smallest edit that works (see
  "Where the term goes" below).
- **Adjacent or partial evidence** (the profile states a neighbouring but different practice or skill, not the one the term names) -> do not insert. List it in the report as "adjacent, owner decides".
- **No evidence** -> do nothing. List it in the report only.

Rules for every proposed edit:
- Insert the term, not the JD's sentence (Phase 3's rule against copying JD phrases verbatim still holds).
- Never edit frozen text: Key results bullets, the AI tooling paragraph, locked or canonical blocks from the profile, the contacts line. A term that would need such an edit is not inserted; list it in the report as "not inserted: frozen text".
- No fabrication, no invented context (Phase 3's no-fabrication rule). The sentence must stay true as written.
- Do not insert a term for a signal that Phase 2 marked ❌ (Signal Coverage in_profile, Fit Breakdown) or recorded as a genuine gap, and never against the profile's Honest Gaps notes.
- A new sentence is allowed only as the last step of "Where the term goes", and it must earn its place
  (Phase 3's rule): no padding, no repeated terms.
- Name a tool only where the JD asks for it and the profile shows the candidate used it; never add a list of
  tools.
- A term that names a different discipline in another industry counts as evidence only if the profile's
  work is the discipline the JD means.
- A profile fact marked rare or default-omit is not unlocked by a keyword match alone (Unlock-condition
  check in `phase2_fit.md`).
- Keep the CV's voice rule, its language-level rule and the em-dash ban.

### Where the term goes

Take the first option that fits, from the smallest edit to the largest:
1. Add the term as one more item to an enumeration that already exists in the role where the evidence
   sits ("did A, B, C" becomes "did A, B, C, X"), or as a short clause to an existing sentence of that role.
2. Only if no existing sentence can carry it: a new short sentence in that role. It states only evidence
   the profile holds and maps to a JD signal. Be careful here.
3. If the evidence is not tied to a role (a skills list, a personal project): a clause in the Summary, never
   in the AI tooling paragraph, worded honestly ("in personal projects" for a personal project). For a
   certification: the CERTIFICATIONS section, only as the Phase 3 certification rule allows.
4. If none of these fits without inventing a fact: do not insert. List the term in the report as "no
   honest insertion point, owner decides".

## Step 4: Present and apply

Show a table: Term | Where it appears in the JD | In the CV? | Evidence in the profile | Proposed edit | Words added. End the table with the total number of words the proposed edits add to the CV, so the owner sees the cost of the keywords. Apply
an edit only after the user confirms the exact wording. After the confirmed edits: re-save the CV `.md` only
(no PDF), then re-run the mechanical lint (`core.cv_metrics.detect_mechanical_violations`), the
repetition check (`detect_phrase_repetition`) and the JD-echo check (`detect_jd_echo`). A JD-echo hit that
consists only of an inserted term is expected and is not a fix: Phase 3.5's rule that an echo hit must be
fixed does not apply to those terms. Any other hit is handled as in Phase 3.5. If a PDF was already rendered
for this CV, re-render it once after the confirmed edits (not after each one).

## Output

Append to `JD_analysis.md` under `## Phase 3.7: ATS Keyword Coverage`: the table, then one line
`Inserted terms: term one; term two` (leave it empty when nothing was inserted). Phase 3.8 reads that line
and does not report a phrase whose only overlap with the JD is one of those terms.

Phase report for the chat: terms checked, already present, inserted, adjacent (owner decides), not inserted
(frozen text), not claimable.
