# EPIC-28 — Flutter Mobile Port (Android/iOS)

**Status:** 📋 Planned. Not started, not scoped/estimated — recorded so the investigation from 2026-07-25 isn't re-done from scratch.

**Why:** README's stated platform strategy — "Same Flutter codebase compiles to Web and Mobile later — no rewrite" — is true for business logic/state (Riverpod providers, models, repositories), but the current UI shell is desktop-shaped and doesn't run on a phone as-is. This epic exists to hold that gap until it's actually prioritized.

---

## Findings from the 2026-07-25 discussion (grounded in code, not guesswork)

Three real blockers, not a build-target flag flip:

1. **`local_notifier` package is desktop-only** (Windows/macOS/Linux — stated directly in `pubspec.yaml`'s own comment). Needs swap to a mobile-capable package (e.g. `flutter_local_notifications`) for push/local notifications on Android/iOS. Contained — single call site (`flutter/lib/services/notification_service.dart`). Small.

2. **No adaptive layout — `app_shell.dart` is a fixed sidebar + `Row` (list + detail always side by side), zero responsive breakpoint logic** (`NavigationRail`/`BottomNavigationBar`/`LayoutBuilder`/`MediaQuery` width checks — none found in `app_shell.dart` or `vacancy_inbox_screen.dart`). On a real phone width (~360–430px) the current always-two-pane split simply doesn't fit.
   - **Turned out cheaper than it first looked**: `VacancyDetailScreen` and the list (`InboxVacancyList`/`VacancyInboxScreen`) are already separable, self-contained widgets — not entangled with each other, just currently siblings in one `Row`. The actual missing piece is a width-based branch: narrow width → show one of {list, detail} at a time via `Navigator.push`/conditional `IndexedStack` instead of both simultaneously; the persistent sidebar nav collapses to a bottom nav bar or drawer. This is composition, not new business logic — everything already reads from the same providers (`folderVacanciesProvider`, etc.) regardless of which shell renders them.
   - Today's whole badge/header overflow saga (2026-07-24 CHANGELOG) was fighting a DESKTOP narrow-panel width (~160–360px); real mobile widths/touch-target sizing/safe-area insets are a related but separate pass, not automatically solved by the adaptive-layout work above.

3. **Backend reachability is a deployment/architecture question, not a Flutter code question.** FastAPI currently runs locally alongside the desktop app. A phone can't casually run the same local backend the way desktop does — either the backend needs to live on a continuously-reachable host/server the phone can reach over network, or some other topology decision. Out of scope for the Flutter-side work in this epic; needs its own decision before mobile is actually usable, not just buildable.

**Already fine as-is, no action needed:** `http`, `file_picker`, `url_launcher`, `shared_preferences`, `google_fonts` — genuinely cross-platform.

## Scope (not designed yet)

- [ ] Swap `local_notifier` → mobile-capable notification package
- [ ] Add width-based adaptive branch in `app_shell.dart` (list ↔ detail push/pop below a breakpoint; sidebar → bottom nav/drawer)
- [ ] Mobile-specific pass on touch targets / safe-area insets for the badge/header work already done for desktop
- [ ] Decide backend topology for a phone client (separate decision, blocks real usability even once the Flutter side is done)

## Not started

No estimate, no milestone breakdown yet — pick up this file before re-investigating from scratch.
