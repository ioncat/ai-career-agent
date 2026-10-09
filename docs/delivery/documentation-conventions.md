# Documentation Conventions — Tasks, Changelog, Epics

**Status:** working contract. Claude Code MUST follow these rules whenever it touches
CHANGELOG.md or epic files, and whenever it records an open task. Referenced from `CLAUDE.md`.

Complements [product-delivery-conventions.md](product-delivery-conventions.md)
(User Story structure) — this document covers **where records live and when they are written**.

> **From 2026-10-09 open tasks live in Linear** (one writer: the dispatcher). `BACKLOG.md` is deprecated: every entry has moved to the board (VBA-12 to VBA-81) and the file is a pointer only. Do not add anything to it.

---

## 1. Document map

| Document | Location | Contains | Never contains |
|---|---|---|---|
| **Task tracker** | Linear, team `VBA` (see `AGENT_RULES.md`, rule 20) | Open work: issues with status, priority, role label | History, delivered features |
| **BACKLOG.md** | `docs/delivery/BACKLOG.md` | Deprecated pointer to the board (kept until nothing links to it) | Everything else |
| **CHANGELOG.md** | `docs/delivery/CHANGELOG.md` | Delivered features + fixes, reverse-chron by date | Plans, open tasks |
| **Epics** | `docs/delivery/Epics/EPIC-NN-slug.md` | Full design specs for epic-sized work | — |
| **Ideas** | `docs/discovery/*.md` | Designs not yet committed to (experiments, P3 concepts) | — |
| **Sessions** | `.claude/sessions/` | Per-session logs (gitignored) | — |
| **Effort log** | `docs/effort-log.md` | Time tracking per session | — |

Nothing project-management-related lives in the repo root. Root = code, README, CLAUDE.md.

---

## 2. Open tasks (Linear)

- A task is a Linear issue in team `VBA`; the dispatcher writes it (rule 20), the owner may write too. Roadmap steps are projects `01` to `11`, work outside the steps goes to the project `General`.
- Priority: P0 Urgent, P1 High, P2 Medium, P3 and parked ideas Low. Role and topic labels, `needs-owner` for what waits for the owner.
- A design that outgrows an issue description goes to `Epics/` or `docs/discovery/` and the issue links it.
- Delivered: close the issue (the dispatcher closes it) and add the CHANGELOG bullet, which names the `VBA-n`.
- Obsolete or superseded: cancel the issue; keep the design in `docs/discovery/` if it is worth keeping.
- Prohibited: delivered work as open issues; duplicates of work already in CHANGELOG; open tasks written into files in the repo.

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
| Epic closes | Add closure bullet; update the epic file status; close its Linear project or issues |

### Prohibited

- ❌ Editing past entries (history is append-only; corrections = new entry)
- ❌ Planned/unfinished work ("will be added later")

---

## 4. Epic rules

**Epic-sized** = multi-session work, touches >1 subsystem, or needs a design decision record.

- File: `docs/delivery/Epics/EPIC-NN-short-slug.md`. Numbers are sequential, never reused.
- Header always carries status: `📋 Planned` / `🚧 In Progress` / `✅ Done YYYY-MM-DD` / `🚫 Dropped`.
- Task list lives in the epic file; Linear holds the issues and links to it.
- On completion: mark tasks ✅ in the epic file, flip status, add CHANGELOG bullet,
  close the Linear issues.
- Ideas not yet committed to are NOT epics — they live in `docs/discovery/` until promoted.

---

## 5. Lifecycle (summary)

```
idea → docs/discovery/*.md (optional) → Linear issue (priority, project)
     → work starts → status In Progress
     → delivered  → issue closed in Linear + CHANGELOG bullet (same session)
     → epic done  → epic status flipped + CHANGELOG closure bullet
```

Session-end checklist (Claude Code, every session with delivery):
1. CHANGELOG bullet written for every delivered feature
2. Linear: delivered issues closed (the dispatcher closes them)
3. `.claude/sessions/` log created
4. `docs/effort-log.md` updated if session is significant
