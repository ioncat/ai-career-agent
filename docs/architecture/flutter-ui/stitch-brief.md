# Google Stitch Brief — Career Agent Flutter Desktop

## System prompt (paste this first)

"Windows Desktop app, Flutter, Material 3. NavigationRail left sidebar, master-detail layout, information-dense UI. Functional animations only: fade-in on list updates, smooth expand/collapse, thin progress bar during loading. No decorative animations, no page transition slides. Generate Flutter widget code."

---

## What to generate

Atomic widgets only. No full screens. No navigation wrappers.

1. ColorScheme + ThemeData (from tokens below)
2. FitScoreChip
3. VacScoreBadge
4. RecommendationChip
5. VacancyCard
6. SourceBadge
7. FitDotBar
8. PollingProgressBar
9. BackendStatusDot
10. StatusLine

---

## Color tokens

### Fit Score (by value)

| Score | Color  | Hex     |
|-------|--------|---------|
| 8–10  | green  | #2E7D32 |
| 6–7   | teal   | #00695C |
| 4–5   | amber  | #E65100 |
| 1–3   | red    | #C62828 |

### VacScore tier (by value)

| Score   | Tier    | Color  | Hex     |
|---------|---------|--------|---------|
| ≥ 7.5   | Premium | green  | #388E3C |
| 5.5–7.4 | Solid   | amber  | #F57C00 |
| < 5.5   | Limited | gray   | #757575 |

### Recommendation

| Value         | Color  | Hex     | Icon |
|---------------|--------|---------|------|
| apply         | green  | #2E7D32 | ✅   |
| take_a_chance | amber  | #F57C00 | ⚡   |
| decline       | gray   | #757575 | ✗    |

### Source badges

| Source   | Color  | Hex     |
|----------|--------|---------|
| Djinni   | blue   | #1565C0 |
| DOU.ua   | green  | #2E7D32 |
| LinkedIn | navy   | #0A3D62 |
| Other    | gray   | #616161 |

### Role Balance bar segments

| Segment     | Hex     |
|-------------|---------|
| Strategy    | #1976D2 |
| Discovery   | #7B1FA2 |
| Execution   | #388E3C |
| Stakeholder | #F57C00 |
| Operational | #757575 |

---

## Typography (Material 3 type scale)

| Element                 | Role           |
|-------------------------|----------------|
| Role + Company (card)   | titleMedium    |
| Screen title            | headlineSmall  |
| Section headers         | titleSmall     |
| Body / barrier text     | bodyMedium     |
| Date, source label      | labelSmall     |
| Fit score (large)       | displaySmall   |
| VacScore number         | headlineMedium |

---

## Spacing

- Card padding: 16px
- Section gap: 24px
- List item height: 72px
- NavigationRail width: 256px (labels visible)

---

## Widget specs

### FitScoreChip
Colored chip displaying fit score.

Props: `score` (int 1–10)
Color: from Fit Score token table above
Label: "Fit {score}/10"
Shape: StadiumBorder
Size: compact

---

### VacScoreBadge
Colored badge displaying vacancy score.

Props: `score` (double 0–10)
Color: from VacScore tier table above
Label: "{score} {tier}" e.g. "8.1 Premium"
Shape: RoundedRectangleBorder radius 6

---

### RecommendationChip
Colored chip with icon and label.

Props: `recommendation` (String: apply / take_a_chance / decline), `label` (String)
Color + icon: from Recommendation table above
Label: display the full `label` string e.g. "apply — strong match"
Shape: StadiumBorder

---

### VacancyCard
List item card for vacancy.

Props:
- role: String
- company: String
- site: String (djinni / dou / linkedin / other)
- fitScore: int
- vacancyScore: double
- recommendation: String
- recommendationLabel: String
- publishedAt: String (relative: "2 дня назад")
- keyBarrier: String? (first barrier, may be null)

Layout (3-line card):
- Line 1: role (titleMedium, bold) + SourceBadge (right)
- Line 2: company (bodyMedium) + FitScoreChip + VacScoreBadge
- Line 3: RecommendationChip + publishedAt (labelSmall, muted)
- Line 4 (optional): keyBarrier with ⚠️ icon (labelSmall, amber, truncated 1 line)

States: default / hovered (elevated shadow) / unread (left accent border, primary color)

---

### SourceBadge
Small colored chip: source name.

Props: `site` (String)
Color: from Source badges table
Label: "Djinni" / "DOU.ua" / "LinkedIn" / "Other"
Size: small, labelSmall typography

---

### FitDotBar
10-dot visual bar representing score.

Props: `score` (int 1–10)
Dot size: 10px, gap: 4px
Filled dots: score count, color from Fit Score table
Empty dots: grey #E0E0E0
Total width: 136px

Example score 7: ●●●●●●●○○○

---

### PollingProgressBar
2px horizontal line at top of content area.

States:
- countdown: deterministic progress 0→1 over `intervalSeconds`, color primary.withOpacity(0.3)
- polling: indeterminate LinearProgressIndicator, color primary
- idle (just updated): hidden or 0%

Props:
- state: PollingBarState (countdown / polling / idle)
- intervalSeconds: int
- elapsed: int (seconds since last poll)

---

### BackendStatusDot
Small animated status dot.

Props: `status` (HealthStatus: online / offline / checking)

Variants:
- online: 10px green circle (#388E3C) with repeating opacity pulse animation (0.6→1.0, 1.5s)
- offline: 10px red circle (#C62828), static
- checking: 10px gray circle (#9E9E9E), opacity blink (0.3→1.0, 0.8s)

Tooltip: "Сервер доступен" / "Сервер недоступен" / "Проверяем..."

---

### StatusLine
Single-line status text below screen title.

Props: `status` (PollingStatus), `lastUpdatedAt` (DateTime?), `secondsUntilNext` (int), `newCount` (int)

Text per state:
- idle:      "🔄 Обновлено: {X} мин назад · следующее через {Y}с"
- polling:   "⏳ Проверяем новые вакансии..."
- found(n):  "✨ Найдено {n} новые вакансии · только что"
- empty:     "✓ Нет новых вакансий · только что"
- error:     "⚠️ Не удалось получить данные · повтор через {Y}с"

Typography: labelMedium, muted color (onSurface.withOpacity(0.6))

---

End.
