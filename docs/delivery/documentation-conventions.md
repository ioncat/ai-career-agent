# Documentation Conventions — Backlog, Changelog, Epics

**Status:** working contract. Claude Code MUST follow these rules whenever it touches
BACKLOG.md, CHANGELOG.md, or epic files. Referenced from `CLAUDE.md`.

Complements [product-delivery-conventions.md](product-delivery-conventions.md)
(User Story structure) — this document covers **where records live and when they are written**.

---

## 1. Document map

| Document | Location | Contains | Never contains |
|---|---|---|---|
| **BACKLOG.md** | `docs/delivery/BACKLOG.md` | Active work only: Now / P0–P2 / Icebox / Bugs | History, delivered features, full design specs |
| **CHANGELOG.md** | `docs/delivery/CHANGELOG.md` | Delivered features + fixes, reverse-chron by date | Plans, open tasks |
| **Epics** | `docs/delivery/Epics/EPIC-NN-slug.md` | Full design specs for epic-sized work | — |
| **Ideas** | `docs/discovery/*.md` | Designs not yet committed to (experiments, P3 concepts) | — |
| **Sessions** | `.claude/sessions/` | Per-session logs (gitignored) | — |
| **Effort log** | `docs/effort-log.md` | Time tracking per session | — |

Nothing project-management-related lives in the repo root. Root = code, README, CLAUDE.md.

---

## 2. BACKLOG.md rules

### Structure (fixed section order)

```markdown
# career-agent — Backlog
> Last updated: YYYY-MM-DD

## 📌 Now            ← 1–3 items currently being worked on
## 🔴 P0             ← blockers / must-do-next
## 🟠 P1             ← high value, next in line
## 🟡 P2             ← valuable, not urgent
## 🐛 Bugs           ← known defects, each with repro + fix sketch
## 🧊 Icebox         ← P3+, one line each
## 📚 Epics overview ← table: epic / status / link
```

### Entry format

Max **10 lines** per entry:

```markdown
### <Title> (added YYYY-MM-DD)
**What:** one sentence.
**Why:** one sentence (user/business value).
**Scope:** 3–6 checklist bullets or a link.
**Spec:** link to Epics/*.md or docs/discovery/*.md (if design > 10 lines).
```

Priorities follow Global Rule 5: 🔴 blocker / 🟠 high / 🟡 normal / 🟢 low,
with explicit dependencies ("blocked by X") where they exist.

### When to write

| Event | Action |
|---|---|
| New task/idea agreed in session | Add entry to correct priority section, same session |
| Work starts on a task | Move entry to `## 📌 Now` |
| Task delivered | **Delete** entry from BACKLOG + add CHANGELOG entry (same session, atomically) |
| Task obsolete/superseded | Delete entry; if the design is worth keeping → move text to `docs/discovery/` |
| Design grows past ~10 lines | Move full text to `Epics/` or `docs/discovery/`, leave entry + link |
| Session ends | Verify `Last updated` date; verify no delivered work still listed as open |

### Prohibited

- ❌ Delivered/done sections inside BACKLOG (that's CHANGELOG's job)
- ❌ Full design docs inline (tables of DB migrations, 50-line specs → Epics/)
- ❌ Duplicate entries for work already delivered — check CHANGELOG before adding
- ❌ "✅ Done (date)" markers on entries — done means deleted from backlog

---

## 3. CHANGELOG.md rules

### Structure

Reverse-chronological, one `## YYYY-MM-DD` section per delivery date.
Multiple sessions same day → suffix `(session 2)`.

### Entry format

One bullet per feature/fix:

```markdown
- **<Feature name>**: what changed; key files/symbols; test delta if relevant
```

- Features: **mandatory**, same session as delivery (Global Rule 7).
- Bug fixes: **mandatory**, same session as delivery; prefix `**Bug fix — ...**` and include root cause.
- Epic completion: one bullet `**EPIC-NN complete/closed**` + link to the epic file.

### When to write

| Event | Action |
|---|---|
| Feature delivered (tests pass) | Add bullet under today's date, same session |
| Bug fixed with non-obvious root cause | Add bullet with root cause explanation |
| Epic closes | Add closure bullet; update epic file status; update BACKLOG epics table |

### Prohibited

- ❌ Editing past entries (history is append-only; corrections = new entry)
- ❌ Planned/unfinished work ("will be added later")

---

## 4. Epic rules

**Epic-sized** = multi-session work, touches >1 subsystem, or needs a design decision record.

- File: `docs/delivery/Epics/EPIC-NN-short-slug.md`. Numbers are sequential, never reused.
- Header always carries status: `📋 Planned` / `🚧 In Progress` / `✅ Done YYYY-MM-DD` / `🚫 Dropped`.
- Task list lives in the epic file; BACKLOG holds one entry linking to it.
- On completion: mark tasks ✅ in the epic file, flip status, add CHANGELOG bullet,
  remove/update the BACKLOG entry.
- Ideas not yet committed to are NOT epics — they live in `docs/discovery/` until promoted.

---

## 5. Lifecycle (summary)

```
idea → docs/discovery/*.md (optional) → BACKLOG entry (priority section)
     → work starts → entry moves to "Now"
     → delivered  → entry deleted + CHANGELOG bullet (same session)
     → epic done  → epic status flipped + CHANGELOG closure bullet
```

Session-end checklist (Claude Code, every session with delivery):
1. CHANGELOG bullet written for every delivered feature
2. BACKLOG: delivered entries removed, `Last updated` bumped
3. `.claude/sessions/` log created
4. `docs/effort-log.md` updated if session is significant
