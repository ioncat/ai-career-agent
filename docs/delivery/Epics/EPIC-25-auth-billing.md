# EPIC-25 — Authentication, User Management & Billing

**Status:** 📋 Planned. Design-first — DO NOT implement without a design doc approved.

**Why:** Required before any commercial use. Blocks: user isolation, billing, role-based access to admin features.

---

## Scope (to be designed)

- Auth mechanism — JWT / OAuth / magic link (TBD)
- Role model — at minimum `user` / `admin`; admin sees Settings screen, regular user does not
- Billing — per-vacancy pricing; Stripe or equivalent (TBD)
- Session management — Flutter secure token storage
- DB: extend `users` table or separate auth DB (TBD)

## Critical pre-design decisions

1. Single-tenant (one company, many users) vs. multi-tenant (many companies)?
2. Self-hosted auth vs. Supabase / Auth0?
3. Billing unit: per vacancy analyzed? per CV generated? subscription?
4. **Admin surface split** (see note below) — role-gated route in the same Flutter app, or a separate admin console?

## Notes

- **Dual-client problem (added 2026-07-13):** the Flutter app is now both the end-user client (inbox, analysis, CV) AND the system-admin client (Settings: provider/model/effort — billing- and safety-relevant). This EPIC must draw the line: a regular user must never see or flip the LLM provider (that is the API-leak class of risk). Decision 4 above. Industrial norm: admin surface separated or RBAC-gated, never open to every user.
- **Settings screen:** currently shows all LLM/provider config — intended for dev/testing only. Once this EPIC lands, Settings route is gated on `admin` role. Regular users never see it.
- **Config store:** provider/model/effort truth moves fully to DB via `core/config_store.py` (see BACKLOG "Config single source of truth"). Per-user provider becomes a DB row by definition once multi-user exists — this EPIC inherits that seam.
- **Start with:** design section in this file — decisions, data model, API contracts, billing flow. No code until design is approved.
