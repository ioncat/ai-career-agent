---
name: Fluid Desktop Workspace
colors:
  surface: '#fdf7ff'
  surface-dim: '#ded8e0'
  surface-bright: '#fdf7ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f8f2fa'
  surface-container: '#F3F3F7'
  surface-container-high: '#ece6ee'
  surface-container-highest: '#E6E6E9'
  on-surface: '#1d1b20'
  on-surface-variant: '#494551'
  inverse-surface: '#322f35'
  inverse-on-surface: '#f5eff7'
  outline: '#7a7582'
  outline-variant: '#cbc4d2'
  surface-tint: '#6750a4'
  primary: '#4f378a'
  on-primary: '#ffffff'
  primary-container: '#6750a4'
  on-primary-container: '#e0d2ff'
  inverse-primary: '#cfbcff'
  secondary: '#625b71'
  on-secondary: '#ffffff'
  secondary-container: '#e8def9'
  on-secondary-container: '#686177'
  tertiary: '#633b48'
  on-tertiary: '#ffffff'
  tertiary-container: '#7d5260'
  on-tertiary-container: '#ffcbda'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e9ddff'
  primary-fixed-dim: '#cfbcff'
  on-primary-fixed: '#22005d'
  on-primary-fixed-variant: '#4f378a'
  secondary-fixed: '#e8def9'
  secondary-fixed-dim: '#ccc2dc'
  on-secondary-fixed: '#1e192b'
  on-secondary-fixed-variant: '#4a4358'
  tertiary-fixed: '#ffd9e3'
  tertiary-fixed-dim: '#eeb8c8'
  on-tertiary-fixed: '#31111d'
  on-tertiary-fixed-variant: '#633b48'
  background: '#fdf7ff'
  on-background: '#1d1b20'
  surface-variant: '#e6e0e9'
  source-djinni: '#007BFF'
  source-dou: '#4CAF50'
  source-linkedin: '#004182'
typography:
  display-sm:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-medium:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '700'
    lineHeight: 24px
  title-small:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
  body-medium:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-medium:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-small:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.5px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  card-padding: 16px
  section-gap: 24px
  list-item-height-3line: 72px
  list-item-height-2line: 56px
  rail-width: 80px
  content-max-width: 1440px
  gutter: 12px
---

## Brand & Style

This design system is built upon **Material 3 + Fluid UI/UX** principles, specifically optimized for a high-density Windows desktop environment. The aesthetic prioritizes spatial depth and structural clarity through tonal layering rather than high-contrast separation.

The brand personality is **professional, efficient, and precise**, evoking a sense of "calm productivity" through a glass-like interface that floats above a decorative background canvas. 

**Key Style Pillars:**
- **Layered Depth:** Use of `surfaceContainer` and `surfaceContainerHighest` to create a hierarchical stack.
- **Glassmorphism:** Strategic use of backdrop blurs and semi-transparency for the main content block to maintain a connection with the decorative background.
- **Precision Information:** High-density data presentation with purposeful semantic coloring for rapid scanning of career match scores.
- **Functional Motion:** Micro-interactions (pulses, fades, smooth expansions) are reserved for system status and state changes, avoiding decorative distraction.

## Colors

The palette is derived from the **Material Design 3 Baseline**, utilizing tonal surfaces to define UI regions.

### Semantic Scoring Logic
Colors are mapped to specific score thresholds to provide immediate visual feedback:
- **Strong Match / Positive (≥ 7.5 or 8-10):** `primary`
- **Good Match / Neutral (5.5–7.4 or 6-7):** `secondary`
- **Weak Match / Caution (4-5):** `tertiary`
- **Poor Match / Critical (1-3):** `error`
- **Muted / Limited:** `outline` or `onSurfaceVariant`

### Tonal Surface Tiers
- **Canvas:** Decorative gradient or frosted glass background.
- **Content Block:** Elevated `surface` with shadow.
- **Navigation Rail:** Subtle elevation or `surfaceContainer`.
- **Selected States:** `surfaceContainerHighest` with a 3px `primary` accent border.

## Typography

The type system uses **Hanken Grotesk** for structural headings to provide a modern, sharp desktop feel, **Inter** for standard body text to ensure maximum legibility at smaller sizes, and **JetBrains Mono** for metadata and status lines to emphasize the technical/analytical nature of the tool.

- **Roles & Titles:** Use `titleMedium` with bold weight for primary card identifiers.
- **Companies & Content:** Use `bodyMedium` for the core information layer.
- **Metadata:** Use `labelSmall` for dates, sources, and secondary technical details.
- **Scores:** Use `displaySmall` or `headlineMedium` for hero score numbers in detail views.

## Layout & Spacing

The layout follows a **Master-Detail Desktop Pattern** set within a constrained content block.

- **Background Canvas:** A full-window decorative layer.
- **Floating Content Block:** A centered container with a maximum width of 1440px. This prevents line lengths from becoming unreadable on ultra-wide monitors.
- **Navigation:** A 80px `NavigationRail` fixed to the left.
- **Grid System:** 
  - List Column: Fixed width of ~360px.
  - Detail Column: Flexible, filling the remaining space of the content block.
- **Vertical Rhythm:** Components use a 4px or 8px base unit. Cards utilize 16px internal padding with a 24px gap between major sections.

## Elevation & Depth

Hierarchy is established through physical elevation and M3 tonal layering:

- **Level 0 (Canvas):** The base background layer.
- **Level 1 (Content Block):** Elevated with `elevation: 4` to `8`, using a soft `shadowColor` and a `BackdropFilter` (blur: 10-15px) to create a "glass" container feel.
- **Level 2 (Tonal Surfaces):** The Navigation Rail uses `surfaceContainer`, while the List and Detail areas use standard `surface`.
- **Level 3 (Interactive Elements):** Hovered cards gain subtle elevation. Selected list items transition to `surfaceContainerHighest` and receive a 3px primary accent border on the leading edge to indicate focus without requiring additional shadows.

## Shapes

The design system utilizes **Rounded (Level 2)** shapes for primary containers and **Stadium (Pill)** shapes for interactive status elements.

- **Content Block:** 16px (`rounded-lg`) border radius.
- **Cards:** 12px border radius.
- **Chips & Source Badges:** `StadiumBorder` (fully rounded ends) to distinguish them from structural containers.
- **VacScore Badge:** 6px radius to maintain a distinct "ticket" or "tag" appearance compared to the rounded chips.

## Components

### Chips & Badges
- **FitScoreChip:** StadiumBorder, height 24px. Uses semantic background colors (Primary/Secondary/Tertiary/Error) based on score.
- **VacScoreBadge:** RoundedRectangleBorder (6px), height 24px. Clear typography for "Score + Tier" label.
- **SourceBadge:** StadiumBorder, uses source-specific branded colors (Djinni: Blue, DOU: Green, LinkedIn: Navy).
- **RecommendationChip:** StadiumBorder with leading icon (Check, Bolt, or X).

### Cards
- **VacancyCard:** A multi-line list item.
  - **Selected State:** Background `surfaceContainerHighest` + 3px primary left border.
  - **Hover State:** Subtle shadow increase.
  - **Layout:** Dense 3-4 line arrangement using the defined typography roles.

### Indicators & Progress
- **FitDotBar:** A sequence of 10 dots (10px diameter, 4px gap). Filled dots use semantic scoring colors; empty dots use `surfaceVariant`.
- **PollingProgressBar:** A 2px bar flush to the top of the content block. Transitions between indeterminate (polling) and deterministic (countdown) states.
- **BackendStatusDot:** 10px circle with animated opacity pulses to indicate server health without layout shifts.

### Input & Form Factors
- **NavigationRail:** Icons-only or icons + short labels. 80px width.
- **StatusLine:** `labelMedium` text positioned above lists for persistent system context.