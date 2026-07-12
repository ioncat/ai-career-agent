# Phase 3.6: Signal Audit

Run after CV is saved and PDF generated. Final quality gate before cover generation.

---

## Task

For each sentence in the EXPERIENCE section of the saved CV, assess whether it delivers value in the context of this JD's requirements — or leads the recruiter in the wrong direction.

**Value verdict per sentence:**
- ✅ Valuable — maps to a JD signal; strengthens the recruiter's perception that the candidate fits a specific requirement
- ⚠️ Weak — tangential; maps to no clear signal; adds noise without building the case
- 🗑️ Remove — maps to no JD signal at all, OR actively misleads by signaling a skill, archetype, or responsibility this JD is NOT hiring for

**Factual ≠ Relevant.** A sentence can be 100% true and still deserve removal if it takes space without building the case for this specific JD.

---

## Input

1. Saved CV text — full EXPERIENCE section
2. Signal Coverage Table from JD_analysis.md (Phase 2 output)

---

## Algorithm

1. Read the Signal Coverage Table — identify all JD signals (high / medium / low)
2. Read EXPERIENCE section role by role
3. For each sentence: map to a JD signal
   - Maps to a signal → ✅ valuable
   - No mapping found → ⚠️ weak (noise) or 🗑️ remove (misleads)
4. Check coverage: are all high/medium ✅/⚠️ signals present in at least one role?

---

## Output Format

### Phase 3.6 — Signal Audit

Per role — list only ⚠️ and 🗑️ findings. ✅ sentences not listed individually — counted in summary only.

**[Role — Company]**
- "[sentence excerpt]..." → ⚠️/🗑️ [signal label or "no signal"] — [one-line reason]

### Summary
✅ High/medium signals covered: N/N
⚠️ Weak sentences: N
🗑️ Sentences to remove: N
  - [Role]: "[excerpt]..."

---

If no issues:

`✅ Signal audit clean — all high/medium signals covered, no orphan or misleading sentences.`

---

## After audit

- **🗑️ found** → present to user, confirm, remove from CV, re-save CV.md + PDF
- **⚠️ only** → present to user, let them decide — do not auto-remove
- **Clean** → proceed directly to Phase 4
