---
name: Craft Enterprise
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#464555'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#3a495f'
  on-tertiary: '#ffffff'
  tertiary-container: '#516177'
  on-tertiary-container: '#ccdcf7'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#d3e4fe'
  tertiary-fixed-dim: '#b7c8e1'
  on-tertiary-fixed: '#0b1c30'
  on-tertiary-fixed-variant: '#38485d'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.025em
  display-lg-mobile:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.015em
  stat-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  stat-lg-mobile:
    fontFamily: Inter
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  body-base:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: -0.006em
  body-medium:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: -0.006em
  body-bold:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.006em
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.05em
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system embodies high-craft engineering precision for mission-critical enterprise platforms. It merges corporate authority with tactile micro-interactions, evoking quiet confidence, sovereign security, and instantaneous responsiveness. Designed for technical founders, systems architects, and engineering leadership, the interface feels calm, deliberate, and frictionless.

The aesthetic fuses **Modern Enterprise Minimalism** with **Tactile Craft**. Visual weight is achieved through optical balance rather than heavy chrome: structural pure white cards elevate quietly over a luminous slate foundation, framed by hairline border rings and multi-tier ambient shadows. Every interactive touchpoint provides spatial integrity and physical continuity—buttons deflect subtly under pressure, contextual menus expand directly from their trigger origins, and status badges convey enterprise compliance with clarity.

## Colors

The palette uses a cool, high-luminance slate canvas paired with electric indigo accents and midnight slate contrast anchors.

- **Primary (`#4F46E5` Electric Indigo)**: Commands focal actions and high-value conversion flows. Its hover variant (`#4338CA`) deepens visual density, while its pressed state (`#3730A3`) pairs with tactile deflection. Light tint containers (`#EEF2FF`) host active states and selected list pills.
- **Secondary (`#0F172A` Slate Midnight)**: Provides high-contrast utility controls, crisp inverted badge elements, and primary typographic weight.
- **Tertiary (`#64748B` Metadata Slate)**: Governs auxiliary structural cues, column captions, and trailing metrics.
- **Neutral Canvas (`#F8FAFC` Slate Base)**: An ultra-clean, glare-free root foundation. Cards and elevated modular surfaces lift above it in pure white (`#FFFFFF`), separated by hairline boundary rings (`#E2E8F0`).

### Semantic Tokens
- **Emerald Success (`#10B981`)**: Utilized for SOC-2/ISO compliance indicators, production health metrics, and completed deployments. Container: `#ECFDF5`, border: `#A7F3D0`, text: `#065F46`.
- **Amber Caution (`#F59E0B`)**: Rate limits, non-blocking cluster alerts, and expiring credential markers. Container: `#FFFBEB`, border: `#FDE68A`, text: `#92400E`.
- **Critical Rose (`#EF4444`)**: Breaches, failed workflows, and destructive commands. Container: `#FEF2F2`, border: `#FECACA`, text: `#991B1B`.
- **Sky Audit (`#0284C7`)**: Secure enclave tracking and system logs. Container: `#F0F9FF`, border: `#BAE6FD`, text: `#075985`.

## Typography

Typography prioritizes rapid legibility across dense enterprise dashboards. It utilizes **Inter** across all typographic levels, with monospaced numerals (`tnum`) applied across tables and telemetry metrics to guarantee columnar alignment.

### Optical Tracking Rhythm
- **Tight Headings**: Negative tracking (`-0.025em` to `-0.015em`) binds display scale titles into solid visual blocks, preventing typographic drift across wide enterprise canvases.
- **Balanced Body**: Neutral-to-subtle negative tracking (`-0.006em`) at 14px provides rapid horizontal reading comfort with a proportional 1.43 line-height ratio.
- **Expanded Micro-Labels**: Upper-cased category badges, column tags, and status caps carry wide tracking (`+0.05em`) to retain crisp shape legibility at 11px.

## Layout & Spacing

This design system uses an **adaptive 12-column fluid grid** nested inside a constrained workbench container (standard: 1280px, expanded: 1440px). Vertical and horizontal rhythm relies on a strict 4px/8px modular scale.

### Responsive Breakpoints & Adapters
- **Desktop (1024px - 1440px+)**: 12 columns, 24px (`1.5rem`) gutters, 32px (`2rem`) margins. Persistent 240px collateral navigation sidebar with fluid central canvas. Data displays feature multi-column metric ribbons and expansive table views.
- **Tablet (640px - 1023px)**: 6 or 8 columns, 24px gutters, 24px margins. Metrics collapse into a 2-column matrix; navigation transitions to a collapsable drawer or slim rail.
- **Mobile (&lt; 640px)**: Single column stack, 16px (`1rem`) gutters and section margins. Tables allow contained horizontal scrolling, metric groups stack vertically, and touch targets enforce a minimum 44px hit-box.

Whitespace strategy balances dense inner card structures (36px–44px row heights) with calm outer margins (32px section separation), preserving visual breathing room during complex operational tasks.

## Elevation & Depth

Visual hierarchy uses **tonal layer stacking**, **ambient tinted diffusion**, and **hairline rim boundaries**. Pure drop shadows are replaced with multi-tier composite elevations.

### Surface Tiers
- **Canvas Base (`#F8FAFC`)**: Structural backdrop upon which all elements rest.
- **Elevated Surfaces (`#FFFFFF`)**: Metric panels, main table enclosures, and form containers. Surrounded by a 1px hairline border (`#E2E8F0`) and layered soft shadows:
  `0 0 0 1px rgba(15, 23, 42, 0.04), 0 1px 2px 0 rgba(15, 23, 42, 0.03), 0 4px 12px 0 rgba(15, 23, 42, 0.04)`
- **Interactive Float Layer**: Popovers, contextual dropdowns, and flyout menus. Elevated above working cards using an ambient lift:
  `0 0 0 1px rgba(15, 23, 42, 0.06), 0 8px 24px -4px rgba(15, 23, 42, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.04)`
- **Frosted Chrome**: Sticky headers, command bars, and floating controls employ `backdrop-filter: blur(12px) saturate(1.4)` on `rgba(255, 255, 255, 0.85)` surfaces, finished with a 1px border-bottom (`#E2E8F0`).

### Specular Lighting
Interactive solids (such as primary buttons) incorporate subtle physical highlights: an interior top hairline rim (`box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2)`) that mimics physical beveling under a light source.

## Shapes

The design system adopts a **soft, disciplined geometry (`roundedness: 1`)**, reflecting institutional rigor and modern software craftsmanship. Structural components avoid ballooned radiuses, prioritizing compact efficiency.

- **Controls & Inputs (`rounded-sm` / 6px)**: Buttons, text inputs, selection controls, and dropdown triggers use clean 6px radiuses.
- **Containers & Modals (`rounded-DEFAULT` 8px / `rounded-lg` 12px)**: Metric tiles, content cards, and utility drawers maintain an 8px to 12px radius, preserving clean geometric relationships when nesting inputs inside containers.
- **Status Pills & Chips (`rounded-full` / 9999px)**: Verification tags, SOC-2 compliance badges, and active tab indicator capsules use fully circular pill contours to stand apart from structural rectangular cards.

## Components

### Buttons
- **Primary**: Solid Electric Indigo fill (`#4F46E5`), `#FFFFFF` text, 6px radius, `box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2), 0 1px 2px rgba(0, 0, 0, 0.05)`. Hover shifts to `#4338CA`. Active state triggers `transform: scale(0.97)` over a `160ms cubic-bezier(0.23, 1, 0.32, 1)` transition.
- **Secondary**: Pure white canvas (`#FFFFFF`), 1px solid `#E2E8F0` border, `#0F172A` text, and subtle ambient lift (`0 1px 2px rgba(0, 0, 0, 0.05)`). Hover background `#F8FAFC`. Active state depresses to `scale(0.97)`.
- **Ghost**: Transparent background, `#475569` text, transitioning to `#F1F5F9` background on hover.

### Inputs & Form Fields
- Height: 38px, background `#FFFFFF`, border `1px solid #CBD5E1`, corner radius 6px.
- Focus State: Replaces browser rings with an anti-aliased dual-layer perimeter:
  `box-shadow: 0 0 0 2px #FFFFFF, 0 0 0 4px #4F46E5, 0 1px 2px 0 rgba(0, 0, 0, 0.05); border-color: #4F46E5; outline: none;`
- Placeholder text: `#94A3B8`, typography 14px (`body-base`).

### Cards & Modular Containers
- Constructed on `#FFFFFF` with a 1px perimeter border (`#E2E8F0`) and 10px-12px corner radiuses.
- Padding: 20px–24px for structural sections; 16px for condensed telemetry widgets.
- Composite ambient shadow ensures depth without visual muddiness.

### Enterprise Compliance & Status Badges
- Height: 22px, pill-radius (`9999px`), padding `0 8px`.
- Security Badges (e.g., SOC-2, ISO): Background `#ECFDF5`, border `1px solid #A7F3D0`, text `#065F46`, font `11px label-caps`. Left-aligned with a 6px pulsing emerald status pip.
- Neutral Tag: Background `#F1F5F9`, border `1px solid #E2E8F0`, text `#475569`.

### Selection Controls (Checkboxes & Radios)
- Checkboxes: 16x16px box, 4px corner radius, border `1px solid #CBD5E1`. Checked state fills `#4F46E5` with a sharp white check glyph. Focus ring matches input token.
- Radios: 16x16px circle, border `1px solid #CBD5E1`, with an inset 6px white dot over `#4F46E5` when selected.

### Lists & Data Tables
- Table headers: Background `#F8FAFC`, border-bottom `1px solid #E2E8F0`, typography 11px (`label-caps`) in `#64748B`.
- Rows: Height 44px, border-bottom `1px solid #F1F5F9`, `#0F172A` body text. Hover background `#F8FAFC`. Active selection yields `#EEF2FF` tint with a 2px left border in `#4F46E5`.

### Micro-Interactions & Popovers
- Anchored Popovers: Animate dynamically from their anchor point (`transform-origin: var(--transform-origin)`), opening from `scale(0.95)` with opacity 0 to `scale(1)` with opacity 1 over 180ms ease-out.
- Notification Toasts: Positioned bottom-right on elevated `#FFFFFF` with 8px radius, layered shadow (`0 8px 24px rgba(0, 0, 0, 0.08)`), and interruptible smooth translation transitions.