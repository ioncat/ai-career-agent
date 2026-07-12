---
name: Career Agent
colors:
  surface: '#f9f9ff'
  surface-dim: '#d8dae2'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3fc'
  surface-container: '#ecedf6'
  surface-container-high: '#e6e8f0'
  surface-container-highest: '#e0e2ea'
  on-surface: '#181c21'
  on-surface-variant: '#414752'
  inverse-surface: '#2d3037'
  inverse-on-surface: '#eff0f9'
  outline: '#717783'
  outline-variant: '#c1c6d4'
  surface-tint: '#005faf'
  primary: '#005dac'
  on-primary: '#ffffff'
  primary-container: '#1976d2'
  on-primary-container: '#fffdff'
  inverse-primary: '#a5c8ff'
  secondary: '#046b5e'
  on-secondary: '#ffffff'
  secondary-container: '#9defde'
  on-secondary-container: '#0f6f62'
  tertiary: '#8a31b1'
  on-tertiary: '#ffffff'
  tertiary-container: '#a64dcc'
  on-tertiary-container: '#fffdff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d4e3ff'
  primary-fixed-dim: '#a5c8ff'
  on-primary-fixed: '#001c3a'
  on-primary-fixed-variant: '#004786'
  secondary-fixed: '#a0f2e1'
  secondary-fixed-dim: '#84d5c5'
  on-secondary-fixed: '#00201b'
  on-secondary-fixed-variant: '#005046'
  tertiary-fixed: '#f8d8ff'
  tertiary-fixed-dim: '#ebb2ff'
  on-tertiary-fixed: '#320047'
  on-tertiary-fixed-variant: '#721199'
  background: '#f9f9ff'
  on-background: '#181c21'
  surface-variant: '#e0e2ea'
  fit-high: '#2E7D32'
  fit-mid-high: '#00695C'
  fit-mid-low: '#E65100'
  fit-low: '#C62828'
  tier-premium: '#388E3C'
  tier-solid: '#F57C00'
  tier-limited: '#757575'
  source-djinni: '#1565C0'
  source-dou: '#2E7D32'
  source-linkedin: '#0A3D62'
  source-other: '#616161'
  segment-strategy: '#1976D2'
  segment-discovery: '#7B1FA2'
  segment-execution: '#388E3C'
  segment-stakeholder: '#F57C00'
  segment-operational: '#757575'
typography:
  display-sm:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  title-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.5px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  nav-rail-width: 256px
  card-padding: 16px
  section-gap: 24px
  list-item-height: 72px
  gutter-md: 16px
  margin-lg: 24px
---

## Brand & Style

The design system is engineered for a high-density, professional environment, specifically tailored for a Flutter desktop application. The brand personality is efficient, data-driven, and authoritative, serving as a specialized tool for career management.

The design style follows a **Corporate / Modern** aesthetic, strictly adhering to Material 3 principles but optimized for desktop information density. The UI emphasizes clarity and utility over decorative flair, using a "Master-Detail" architecture to manage complex datasets without overwhelming the user. Visual interest is derived from functional data visualization—such as status dots, score chips, and progress bars—rather than illustrative elements.

The emotional response should be one of confidence and productivity. The interface feels "quiet" in its neutral states but provides immediate, high-contrast feedback through a semantic color system when data requires attention.

## Colors

The color system is heavily functional. While the primary brand color is a professional Blue (#1976D2), the UI is governed by a semantic logic that communicates value and risk through color.

- **Backgrounds:** Use clean, neutral tones (off-whites and light greys) to ensure the master-detail layout maintains visual separation without heavy borders.
- **Data Semantics:** Green is reserved for high scores and "apply" recommendations. Amber indicates warnings, mid-range scores, or "take a chance" statuses. Red is strictly for low scores or system errors.
- **Source Identity:** Specific brand colors are used for external platform identification (LinkedIn Navy, Djinni Blue, DOU Green) to allow for instant peripheral recognition of data sources.
- **Role Balance:** A secondary palette of distinct hues is used to segment role responsibilities (Strategy, Discovery, Execution, etc.) within horizontal bar visualizations.

## Typography

This design system utilizes **Inter** for all roles to provide a systematic, neutral, and highly legible experience across various data densities.

- **Hierarchy:** Screen titles use `headline-sm` to maintain a professional scale. `display-sm` is reserved for large numerical scores where emphasis is critical.
- **Card Content:** `title-md` is the primary anchor for vacancy roles, while `label-sm` handles the heavy lifting for metadata like dates, source labels, and secondary tags.
- **Alignment:** Desktop-specific spacing ensures that multi-line cards (3-4 lines) remain readable. Tracking (letter-spacing) is increased slightly on `label-sm` to improve clarity at small sizes.

## Layout & Spacing

The layout follows a **Fixed Grid** desktop model optimized for a 12-column structure or a Master-Detail split.

- **Navigation:** A fixed `NavigationRail` on the left (256px) provides persistent access to primary categories with visible labels.
- **Master-Detail:** The main content area is divided into a scrollable list (Master) and a content preview (Detail). 
- **Rhythm:** An 8px base grid is used for spacing. Vertical list items are standardized at 72px for a consistent scrolling cadence.
- **Density:** Padding is intentionally compact (16px in cards) to allow more information to be visible above the fold without sacrificing touch/click targets.

## Elevation & Depth

Hierarchy is established through **Tonal Layers** rather than heavy shadows.

- **Surfaces:** The main background uses the base surface color. Cards and Detail containers use a slightly elevated "Surface Container" tone to create subtle separation.
- **Shadows:** Standard state uses zero elevation or a very low-contrast outline. Hover states on cards trigger a soft, diffused ambient shadow to indicate interactivity.
- **Interaction:** Active or "Unread" states bypass depth in favor of color-based cues, such as a high-contrast primary color border on the left edge of a list item.

## Shapes

The shape language is **Soft (0.25rem)** to maintain a structured, professional feel that fits the Windows desktop environment.

- **Chips & Badges:** Use `StadiumBorder` (fully rounded) for status and recommendation chips to distinguish them from structural elements.
- **Cards & Containers:** Use a 6px - 8px radius. This provides a modern touch without appearing overly "bubbly," ensuring the edges align well with the straight lines of a desktop monitor.
- **Visual Indicators:** Score dots and status indicators are perfect circles to differentiate them from interactive text-based components.

## Components

- **Vacancy Cards:** These are the primary data units. They must support 4 lines of content: Role/Source, Company/Scores, Recommendations/Date, and an optional Barrier line. Unread cards feature a 4px left-hand accent bar.
- **FitScore & VacScore:** These components translate numbers into color. FitScore uses a stadium chip; VacScore uses a 6px rounded badge. Both must dynamically update their background and text color based on the value thresholds.
- **Status Dots:** Small (10px) circles with functional animations. The "online" state pulses slowly, while the "checking" state blinks to show active processing without distracting the user.
- **Progress Indicators:** A 2px `PollingProgressBar` is placed at the very top of the content area. It remains hidden when idle, appearing only to show the countdown to the next refresh or the active indeterminate state of a fetch.
- **Source Badges:** Small-scale labels using `label-sm` typography, themed to the platform (Djinni, LinkedIn, etc.), positioned in the top-right of cards for quick filtering by eye.