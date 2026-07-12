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

## Notes

- **Settings screen:** currently shows all LLM/provider config — intended for dev/testing only. Once this EPIC lands, Settings route is gated on `admin` role. Regular users never see it.
- **Start with:** design section in this file — decisions, data model, API contracts, billing flow. No code until design is approved.
