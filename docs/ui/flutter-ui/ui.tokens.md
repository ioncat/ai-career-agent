# UI Design Tokens — Career Agent Flutter Desktop

Reference for Google Stitch mockups and Flutter theme.
All colors reference Material 3 color roles where possible.

---

## Fit Score — color by value

| Score | Color role | Hex (light) | Label |
|-------|-----------|-------------|-------|
| 8–10  | success / green | #2E7D32 | Strong fit |
| 6–7   | primary / teal  | #00695C | Good fit |
| 4–5   | warning / amber | #E65100 | Weak fit |
| 1–3   | error / red     | #C62828 | Poor fit |

Used in: FitScoreChip, FitDotBar, QuickScanPanel background tint.

---

## VacScore (Vacancy Score) — tier by value

| Score    | Tier    | Color  | Hex (light) | Badge label |
|----------|---------|--------|-------------|-------------|
| ≥ 7.5    | Premium | green  | #388E3C     | Premium     |
| 5.5–7.4  | Solid   | amber  | #F57C00     | Solid       |
| < 5.5    | Limited | gray   | #757575     | Limited     |

Used in: VacScoreBadge, vacancy list column.

---

## Recommendation — chip color + icon

| Value          | Color  | Icon | Display label examples |
|----------------|--------|------|------------------------|
| apply          | green  | ✅   | "apply", "apply — strong match", "apply — limited upside" |
| take_a_chance  | amber  | ⚡   | "take a chance", "take a chance — premium opportunity" |
| decline        | gray   | ✗    | "decline", "decline — not worth the effort" |

Used in: RecommendationChip (list + detail).

---

## Source badges

| Source   | Color  | Hex     |
|----------|--------|---------|
| Djinni   | blue   | #1565C0 |
| DOU.ua   | green  | #2E7D32 |
| LinkedIn | navy   | #0A3D62 |
| Other    | gray   | #616161 |

---

## Role Balance — bar chart segments

| Segment      | Color  | Hex     |
|--------------|--------|---------|
| Strategy     | blue   | #1976D2 |
| Discovery    | purple | #7B1FA2 |
| Execution    | green  | #388E3C |
| Stakeholder  | orange | #F57C00 |
| Operational  | gray   | #757575 |

---

## Barrier severity — list icons + tint

| Type         | Icon | Color  | Tint bg |
|--------------|------|--------|---------|
| Key Barrier  | ⚠️   | amber  | #FFF8E1 |
| Hidden Risk  | 🔴   | red    | #FFEBEE |
| Warning      | 💡   | blue   | #E3F2FD |

---

## Typography (Material 3 type scale)

| Element                  | Type role        |
|--------------------------|------------------|
| Role + Company (card)    | titleMedium      |
| Screen title             | headlineSmall    |
| Section headers (detail) | titleSmall       |
| Body text / barriers     | bodyMedium       |
| Metadata (date, source)  | labelSmall       |
| Fit score number (large) | displaySmall     |
| VacScore number          | headlineMedium   |

---

## Spacing (Material 3 defaults)

- Card padding: 16px
- Section gap: 24px
- List item height: 72px (3-line card)
- NavigationRail width: 72px (icons only) / 256px (expanded with labels)
- StickyActionBar height: 64px

---

## Status chips — vacancy status in UI

| DB status    | Chip label    | Color  |
|--------------|---------------|--------|
| queued       | Ожидание...   | gray   |
| fetching     | Загрузка...   | blue   |
| analyzed     | Анализ готов  | green  |
| cv_generated | CV готов      | teal   |
| applied      | Отправлено    | purple |
| declined     | Отклонено     | gray   |

---

## FitDotBar spec

10 dots, filled = score value.

```
Score 7/10 → ●●●●●●●○○○
```

Dot size: 10px, gap: 4px, total width: 136px.
Filled color: from Fit Score color table above.
Empty color: surface variant (#E0E0E0 light / #424242 dark).

---

End.
