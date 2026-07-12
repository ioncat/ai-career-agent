# Google Stitch Brief — Career Agent Flutter Desktop

## System prompt (paste this first)

"Windows Desktop app, Flutter, Material 3 + Fluid UI/UX aesthetic. Master-detail layout with NavigationRail. Information-dense UI. Content block floats on a decorative background canvas — elevated, with shadow and rounded corners (glass/depth feel). Tonal surface layering throughout. Functional animations only: fade-in on list updates, smooth expand/collapse, 2px progress bar during polling. No decorative animations, no page transition slides. Generate Flutter widget code only — no full screens, no navigation wrappers."

---

## Design aesthetic

**Material 3 + Fluid UI/UX.**

Key principles:
- **Depth via elevation** — content block floats above the background canvas with shadow, not just color separation
- **Tonal surfaces** — Material 3 `surfaceTint` creates tonal layering (Rail slightly elevated vs List vs Detail)
- **Glass feel** — semi-transparent surfaces over decorative background using `BackdropFilter` + `ImageFilter.blur` where applicable
- **Background canvas** — decorative (gradient, subtle texture, or frosted glass effect) — exact style TBD in design phase; NOT a plain flat fill
- **Constrained content** — content block has a max-width to prevent UI from stretching on large monitors (27"+); user-configurable in Settings

---

## Layout overview

**Full-window canvas** (decorative background, fills entire window) +
**constrained content block** (floats centered on canvas, max-width configurable, default ~1440px):

```
╔══════════════════════════════════════════════════════════╗
║  [decorative background — gradient / glass / TBD]        ║
║                                                          ║
║   ┌──────────────────────────────────────────────┐       ║
║   │ [content block — elevated, shadow, surface]  │       ║
║   │                                              │       ║
║   │ ┌────────┬──────────────┬─────────────────┐ │       ║
║   │ │  Rail  │  List col    │  Detail col     │ │       ║
║   │ │ ~80px  │   ~360px     │   flex          │ │       ║
║   │ └────────┴──────────────┴─────────────────┘ │       ║
║   └──────────────────────────────────────────────┘       ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

Content block elevation: `Material` widget, `elevation: 4–8`, `shadowColor`, rounded corners `borderRadius: 16`.

**Top of content block (spans all columns):**
- 2px `PollingProgressBar` — flush to top edge of content block
- `StatusLine` — single text line above list column

No AppBar. No Drawer.

---

## What to generate

Atomic widgets only. One widget per request.

1. FitScoreChip
2. VacScoreBadge
3. RecommendationChip
4. VacancyCard
5. SourceBadge
6. FitDotBar
7. PollingProgressBar
8. BackendStatusDot
9. StatusLine

---

## Semantic color rules (use Material 3 ColorScheme tokens — no hardcoded hex)

### Fit score (int 1–10)
| Range | Semantic       | Token                          |
|-------|----------------|-------------------------------|
| 8–10  | strong match   | `colorScheme.primary`          |
| 6–7   | good match     | `colorScheme.secondary`        |
| 4–5   | weak match     | `colorScheme.tertiary`         |
| 1–3   | poor match     | `colorScheme.error`            |

### VacScore tier (double 0–10)
| Range    | Tier    | Semantic    | Token                   |
|----------|---------|-------------|------------------------|
| ≥ 7.5    | Premium | positive    | `colorScheme.primary`   |
| 5.5–7.4  | Solid   | neutral     | `colorScheme.secondary` |
| < 5.5    | Limited | muted       | `colorScheme.outline`   |

### Recommendation
| Value         | Semantic | Token                   |
|---------------|----------|------------------------|
| apply         | success  | `colorScheme.primary`   |
| take_a_chance | caution  | `colorScheme.tertiary`  |
| decline       | muted    | `colorScheme.outline`   |

### Source
| Source   | Semantic |
|----------|----------|
| Djinni   | info (blue family)  |
| DOU.ua   | success (green family) |
| LinkedIn | brand (navy family) |
| Other    | muted               |

Use `colorScheme` container/onContainer pairs for badge backgrounds.

---

## Typography (Material 3 type scale)

| Element                    | Role              |
|----------------------------|-------------------|
| Role title (card)          | `titleMedium`     |
| Company name               | `bodyMedium`      |
| Screen / section header    | `titleSmall`      |
| Body text, barrier text    | `bodyMedium`      |
| Date, source label         | `labelSmall`      |
| Fit score number (detail)  | `displaySmall`    |
| VacScore number (detail)   | `headlineMedium`  |
| StatusLine text            | `labelMedium`     |

---

## Spacing

- Card padding: 16px
- Section gap: 24px
- List item height: 72px (3-line card), 56px (2-line)
- Rail width: 80px (icons only, labels below icon)

---

## Widget specs

### FitScoreChip
Compact chip showing fit score.

Props: `score` (int 1–10)
Color: semantic from Fit score table above
Label: `"Fit {score}/10"`
Shape: StadiumBorder
Size: compact (height ~24px)

---

### VacScoreBadge
Rectangular badge showing vacancy score + tier label.

Props: `score` (double 0–10)
Color: semantic from VacScore tier table above
Label: `"{score} {tier}"` — e.g. `"7.5 Premium"`, `"5.2 Limited"`
Shape: RoundedRectangleBorder radius 6
Size: compact (height ~24px)

---

### RecommendationChip
Chip with icon and full recommendation label.

Props: `recommendation` (String: `apply` / `take_a_chance` / `decline`), `label` (String)
Color: semantic from Recommendation table above
Icon: ✅ apply · ⚡ take_a_chance · ✗ decline
Label: display full `label` string e.g. `"apply — strong match"`
Shape: StadiumBorder

---

### VacancyCard
List item for the vacancy list column (~360px wide).

Props:
- `role` (String)
- `company` (String)
- `site` (String: djinni / dou / linkedin / other)
- `fitScore` (int)
- `vacancyScore` (double)
- `recommendation` (String)
- `recommendationLabel` (String)
- `publishedAt` (String — relative, e.g. `"2 дні тому"`)
- `keyBarrier` (String? — first barrier only, may be null)
- `isSelected` (bool)

Layout (3-line card, left border accent when selected):
- Line 1: `role` (titleMedium bold) + `SourceBadge` (right-aligned)
- Line 2: `company` (bodyMedium, muted) + `FitScoreChip` + `VacScoreBadge`
- Line 3: `RecommendationChip` + `publishedAt` (labelSmall, muted)
- Line 4 (optional): ⚠️ `keyBarrier` (labelSmall, caution color, max 1 line truncated)

States:
- default: flat
- hovered: slight elevation shadow
- selected: left accent border (3px, `colorScheme.primary`), `surfaceContainerHighest` background

---

### SourceBadge
Small pill badge: source platform name.

Props: `site` (String)
Color: semantic from Source table above — use container/onContainer pair
Label: `"Djinni"` / `"DOU.ua"` / `"LinkedIn"` / `"Other"`
Typography: labelSmall
Shape: StadiumBorder

---

### FitDotBar
Row of 10 dots representing fit score.

Props: `score` (int 1–10)
Dot: diameter 10px, gap 4px
Filled dots: count = score, color = semantic from Fit score table
Empty dots: `colorScheme.surfaceVariant`
Total: 10 dots, fixed width 136px

Example score 7: `●●●●●●●○○○`

---

### PollingProgressBar
2px horizontal bar at the very top of the window.

Props:
- `state` (PollingBarState: `countdown` / `polling` / `idle`)
- `intervalSeconds` (int)
- `elapsed` (int — seconds since last poll)

States:
- `countdown`: deterministic LinearProgressIndicator, value = `elapsed / intervalSeconds`, color `colorScheme.primary.withOpacity(0.35)`
- `polling`: indeterminate LinearProgressIndicator, color `colorScheme.primary`
- `idle`: hidden (height 0, no animation)

Height: 2px. No border radius. Flush to window top edge.

---

### BackendStatusDot
10px animated status indicator dot.

Props: `status` (HealthStatus: `online` / `offline` / `checking`)

Variants:
- `online`: `colorScheme.primary` filled circle, repeating opacity pulse 0.6→1.0 over 1.5s
- `offline`: `colorScheme.error` filled circle, static
- `checking`: `colorScheme.outline` filled circle, opacity blink 0.3→1.0 over 0.8s

Tooltip: `"Сервер доступен"` / `"Сервер недоступен"` / `"Проверяем..."`

---

### StatusLine
Single-line status text, sits above the list column.

Props: `status` (PollingStatus), `lastUpdatedAt` (DateTime?), `secondsUntilNext` (int), `newCount` (int)

Text per state:
- `idle`:    `"🔄 Обновлено: {X} мин назад · следующее через {Y}с"`
- `polling`: `"⏳ Проверяем новые вакансии..."`
- `found`:   `"✨ Найдено {n} новых вакансий · только что"`
- `empty`:   `"✓ Нет новых вакансий · только что"`
- `error`:   `"⚠️ Не удалось получить данные · повтор через {Y}с"`

Typography: labelMedium, `colorScheme.onSurface.withOpacity(0.6)`

---

End.
