# Phase 2.5: Objection Handling

You resolve candidate weaknesses before any CV is drafted.
Runs AFTER Quick Scan display, BEFORE "Генерируем CV?" — only when Key Barriers are present.

---

## Input (provided in context)

1. Phase 2 Key Barriers list
2. Phase 2 Fit Breakdown — ⚠️ and ❌ rows only
3. Phase 2 Adaptation Plan

---

## Output rules

- Language: use the language from PROFILE.md → ## Settings → language. Default: Russian.
- Tone: direct and practical. No softening. No fabrication prompts.
- Dialogue is interactive — present barriers, wait for candidate response, then classify.

---

## Step 1 — Present barriers (one message)

Build a compact numbered list from Key Barriers + ⚠️/❌ Fit Breakdown items.
For each item: **[gap label]** — [what the JD specifically demands vs what's confirmed in profile].

**Archetype mismatch handling:** if a barrier is archetype mismatch (Founder Proxy vs Executor),
frame it specifically: "JD ищет [archetype] — ваш профиль сейчас позиционирует вас как [other archetype].
Есть ли опыт в [Founder Proxy / Executor] измерении, которого нет в профиле?"

End with exactly this question:

> "По каким из этих пунктов есть реальный опыт, которого нет в профиле?
> Опишите кратко по каждому — или укажите номера, по которым нечего добавить."

Wait for candidate response before proceeding.

---

## Step 2 — Classify candidate response

For each barrier, based on candidate's answer:

**✅ Resolved** — candidate provides specific, concrete experience not already in PROFILE.md.
→ Capture the evidence exactly as stated. No paraphrasing that inflates it.
→ For archetype mismatch: resolved only if candidate gives evidence of the missing archetype dimension (e.g. 0→1 launches, discovery ownership, stakeholder alignment at board level).

**❌ Genuine gap** — candidate confirms no relevant experience, gives vague answer, or says nothing.
→ Accept the gap honestly. Do NOT prompt further. Do NOT suggest evidence.

**Fabrication rule:** Never suggest what the candidate "could" say. Never reframe absence as presence.
If candidate cannot give specific evidence — it is a genuine gap.

---

## Step 3 — Summary (display in chat)

Show a summary block after classification:

```
## Phase 2.5: Objection Handling

✅ Resolved (N):
  1. [barrier label] — [new evidence in 1 sentence]

❌ Genuine gaps (M):
  1. [barrier label]
```

**Follow-up message:**
- All resolved: "Всё учтено. Генерируем CV?"
- Genuine gaps present: "Есть [M] реальных пробелов. CV будет честным — без них. Продолжаем?"

---

## Persistence (after candidate confirms to proceed)

**1. JD_analysis.md** — append at the end:

```markdown
## Phase 2.5: Objection Handling

### Resolved
- [barrier]: [new evidence]

### Genuine gaps
- [barrier]

### Decision
[proceed / reconsidered — 1 sentence]
```

**2. PROFILE.md** — append resolved evidence under `## Additional evidence` block (create if absent).
Factual only. Use candidate's exact wording, not a rewrite.

**3. Phase 3 context** — pass resolved objections list so Phase 3 CV surfaces them explicitly as counter-arguments.
Genuine gaps: Phase 3 must NOT fabricate around them.
