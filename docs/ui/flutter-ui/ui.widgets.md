# UI Widget Map — Career Agent Flutter Desktop

Stack:
- Flutter 3.x (Windows Desktop)
- Material 3
- Riverpod (state management)
- flutter_markdown (CV/cover rendering)
- flutter_local_notifications (Windows toasts)

---

## Layout

### AppShell
Root widget. Wraps everything.

Contains:
- NavigationRail (left)
- MainContentArea (right)
- ToastListener (listens for new vacancy notifications)

---

### NavigationRail
Left sidebar, always visible.

Items:
- InboxNavItem (with unread badge)
- InProgressNavItem
- AppliedNavItem
- ArchiveNavItem
- Divider
- SettingsNavItem

Props:
- selectedIndex
- unreadCount

---

### TopBar
Per-screen header.

Elements:
- Left: screen title + vacancy count
- Below title: StatusLine (polling status text)
- Right: RefreshButton + BackendStatusDot

Props:
- title
- count
- onRefresh

---

### PollingProgressBar
2px line at top of content area. Shows polling rhythm to user.

States:
- countdown: AnimationController fills 0→1 over `pollInterval` seconds, color = primary.withOpacity(0.3)
- polling: LinearProgressIndicator indeterminate (standard animated)
- done: reset to 0, restart countdown

Driven by: `pollingTimerProvider`

---

### StatusLine
Single-line text below screen title. Updates every second.

States (enum PollingStatus):
- idle → "🔄 Обновлено: X мин назад · следующее через Yс"
- polling → "⏳ Проверяем новые вакансии..."
- found(n) → "✨ Найдено N новые вакансии · только что"
- empty → "✓ Нет новых вакансий · только что"
- error → "⚠️ Не удалось получить данные · повтор через 30с"

Props:
- status: PollingStatus
- lastUpdatedAt: DateTime?
- secondsUntilNext: int
- newCount: int

---

### BackendStatusDot
Small animated status indicator in TopBar right corner.

States:
- online → green dot with CSS-style pulse animation
- offline → red dot, static, tooltip "Сервер недоступен — проверь localhost:8080"
- checking → gray dot, opacity blink

Behavior:
- Polls `GET /health` every 60s via separate `healthCheckProvider`
- On offline: RefreshButton disabled
- On online → offline transition: show SnackBar "Сервер недоступен"

Props:
- status: HealthStatus (online / offline / checking)

---

## Vacancy List

### VacancyListScreen
Composed of:
- TopBar
- FilterBar
- VacancyList or EmptyState

---

### FilterBar
Controls:
- SortDropdown (date / fit / vacscore)
- RecommendationFilter (All / Apply / Take a chance / Decline)
- SourceFilter (All / Djinni / DOU.ua / LinkedIn)

---

### VacancyList
Scrollable list.

Contains:
- VacancyCard[] (one per vacancy)

---

### VacancyCard
Single vacancy row in list.

Blocks:
- RoleCompanyTitle
- SourceBadge
- FitScoreChip
- VacScoreBadge
- RecommendationChip
- PublishedLabel (relative time)
- KeyBarrierPreview (first barrier, truncated)

Actions:
- onTap → open detail
- onArchive (swipe/context menu)

Props:
- vacancy: VacancyListItem

States:
- default
- unread (bold title)
- hovered

---

### EmptyState
Shown when folder has no vacancies.

Props:
- folder (inbox / in_progress / applied / archive)
- message (per folder)

---

## Score & Recommendation Widgets

### FitScoreChip
Colored chip: "Fit 7/10"

Color logic:
- score >= 7 → green
- score >= 5 → amber
- score < 5 → red

Props:
- score: int

---

### VacScoreBadge
Colored badge: "VScore 8.1"

Color logic:
- score >= 7.5 → green (Premium)
- score >= 5.5 → amber (Solid)
- score < 5.5 → gray (Limited)

Props:
- score: double

---

### RecommendationChip
Colored chip with icon.

Variants:
- apply → green + ✅ icon
- take_a_chance → amber + ⚡ icon
- decline → gray + ✗ icon

Props:
- recommendation: String (base value)
- label: String (display label)

---

### FitDotBar
Visual dot bar: ●●●●●○○○○○

Props:
- score: int (1–10)
- filledColor
- emptyColor

---

### VacScoreTable
8-row table: dimension name + score + max.

Props:
- dims: VacScoreDims

---

### RoleBalanceChart
Horizontal stacked bar showing % breakdown.

Segments:
- Strategy (blue)
- Discovery (purple)
- Execution (green)
- Stakeholder (orange)
- Operational (gray)

Props:
- balance: Map<String, int>

---

### FitDimensionsTable
6-row table: dimension + score/10 + mini bar.

Props:
- fitDims: FitDimensions

---

## Vacancy Detail

### VacancyDetailScreen
Composed of:
- DetailTopBar (role + company + back button)
- Scrollable column:
  - QuickScanPanel
  - WhoTheyWantCard
  - VacScoreSection (collapsible)
  - RoleBalanceSection (collapsible)
  - FitDimensionsSection (collapsible)
  - BarriersSection (always open)
- StickyActionBar

---

### QuickScanPanel
Top summary card.

Contains:
- FitDotBar (large)
- FitScoreChip (large)
- VacScoreBadge (large)
- RecommendationChip
- CategoryLabel

---

### BarriersSection
Three sub-lists:

KeyBarriersList:
- items: List<String>
- icon: ⚠️
- color: amber

HiddenRisksList:
- items: List<String>
- icon: 🔴
- color: red

WarningsList:
- items: List<String>
- icon: 💡
- color: blue

Props:
- barriers: Phase2Data

---

### CollapsibleSection
Reusable wrapper.

Props:
- title
- initiallyExpanded: bool
- child: Widget

---

### StickyActionBar
Bottom action bar in VacancyDetail.

Buttons:
- GenerateCVButton (primary, filled)
- DeclineButton (secondary, outlined)
- OpenJDButton (text button)

Props:
- vacancyId
- sourceUrl

---

## CV & Cover

### CVGenerationScreen
Composed of:
- PreflightPanel (if no CV yet)
- GenerationProgress (during generation)
- CVResultPanel (after generation)

---

### PreflightPanel
Fields:
- NameVariantInput (text field)
- LanguageSelector (EN / UA / Both — SegmentedButton)
- GenerateCVButton

---

### GenerationProgress
States:
- phase3 ("Drafting CV...")
- phase35 ("Self-review...")
- done

Contains:
- LinearProgressIndicator
- StatusLabel
- ElapsedTimer

---

### CVResultPanel
Contains:
- MarkdownViewer (CV.md content)
- DownloadPDFButton
- RegenerateButton
- GenerateCoverButton

---

### MarkdownViewer
Renders .md as formatted text.

Uses: flutter_markdown package.
Style: clean, no decorative chrome.

Props:
- markdownContent: String

---

### CoverLetterScreen
Contains:
- LanguageSelector
- MarkdownViewer (cover content)
- CopyToClipboardButton
- RegenerateButton

---

## Objection Handling

### ObjectionHandlingScreen
Contains:
- BarrierProgressIndicator (1 of N)
- BarrierCard
- ResponseInput
- NavigationButtons (Next / Skip)

Or (final state):
- AdaptationBriefPanel

---

### BarrierCard
Shows single barrier.

Props:
- barrier: String
- index: int
- total: int

---

### AdaptationBriefPanel
Shows AI-generated adaptation brief after all barriers resolved.

Contains:
- MarkdownViewer
- ProceedToCVButton

---

## Settings

### SettingsScreen
Sections:
- ConnectionSection
- PollingSection
- UserSection
- AboutSection

---

### ConnectionSection
Fields:
- APIUrlField (text input, default http://localhost:8080)
- TestConnectionButton

States:
- idle
- testing
- ok (green checkmark)
- error (red message)

---

### PollingSection
Controls:
- IntervalSelector (SegmentedButton: 15s / 30s / 60s / 5m)
- NotificationsToggle (Switch)

---

## Shared / Utility

### SourceBadge
Colored small chip: Djinni (blue) / DOU.ua (green) / LinkedIn (navy) / Other (gray)

Props:
- site: String

---

### RelativeTimeLabel
Shows "2 дня назад", "только что", etc.

Props:
- dateTime: DateTime

---

### ConfirmDialog
Standard confirmation.

Props:
- title
- message
- confirmLabel
- cancelLabel
- onConfirm

---

### ErrorBanner
Inline error display.

Props:
- message
- onRetry (optional)

---

### LoadingShimmer
Placeholder skeleton for loading states.

Props:
- height
- width

---

## State / Data Layer (non-UI)

providers/
- vacancyListProvider.dart — AsyncNotifierProvider, polling + refresh
- vacancyDetailProvider.dart — AsyncNotifierProvider(id), per-vacancy cache
- cvProvider.dart — CV + cover content per vacancy
- pollingTimerProvider.dart — background Timer.periodic (30s, vacancies)
- healthCheckProvider.dart — backend /health poll (60s), exposes HealthStatus
- settingsProvider.dart — SharedPreferences wrapper

repositories/
- vacancies.repo.dart — GET /api/vacancies, GET /api/vacancies/{id}/analysis
- cv.repo.dart — GET /api/vacancies/{id}/cv
- generation.repo.dart — POST triggers for Phase 3, 4

Providers never call HTTP directly — always through repositories.

---

End.
