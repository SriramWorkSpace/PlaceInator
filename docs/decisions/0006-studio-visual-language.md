# ADR 0006 — Studio visual language, superseding the GitHub-adjacent direction

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

`docs/specification.md` (the user's verbatim, never-edited source of truth) calls
for a flat, restrained visual language: "minimal, clean, GitHub-inspired," a
single accent color, subtle 1px borders, and explicitly warns against "overly
rounded 'AI SaaS' cards" and "excessive gradients." Earlier in the project the
user confirmed this direction directly, choosing "GitHub-adjacent" over two
warmer/rounder alternatives when asked. `src/styles/index.css` and every shared
component were built to that brief.

The user then supplied three reference screenshots of a Dribbble shot
("Synchronic — Studio Creative Practice System") and asked to match its
typography, fonts, and UI directly. That reference is close to the opposite of
the original brief on every axis it warned against: a serif display face for
headings, fully pill-shaped buttons, large card radii, a warm cream palette,
and a distinct accent color per section rather than one restrained accent.

Given three detailed, unambiguous reference images and an explicit "use the
same," this is read as a deliberate pivot rather than a subtle nudge, and
implemented as one. `specification.md` is not edited to match — it stays the
user's original written brief — but the implementation now departs from that
section of it. This ADR exists so that departure is a recorded decision, not
silent drift.

## Decision

Rebuild the design tokens and shared components around the reference's
language:

**Typography.** `Fraunces` (soft-axis variant) for display headings —
`.display-heading`, used by `Page`'s `<h1>` and `SectionCard`'s `<h2>`. `Inter`
remains the UI/body face, now genuinely self-hosted via `@fontsource-variable`
rather than referenced by name and hoping the OS had it installed (a real gap
in the prior setup, fixed as part of this work). Both ship as local variable
font files — no runtime dependency on a font CDN, consistent with the rest of
the app running offline-first.

**Color.** A warm cream palette (`--canvas` `#f2f0e8`, `--canvas-subtle`
`#faf9f4`) replaces the cold white/grey GitHub palette. A brand
indigo-purple (`--accent`) remains the single global accent for primary
actions and focus rings, but each of the seven sections now also carries its
own muted accent (`--section-dashboard`, `--section-jobs`, ... —
`src/lib/nav.ts`), driving the sidebar's icon badges and every page's eyebrow
label via `Page`'s automatic `navItemForPath` lookup.

**Shape.** `--radius-panel` (20px) for cards, `--radius-input` (14px) for
controls and tables, `--radius-pill` (999px) for buttons. `.btn` establishes a
48px comfort target with a visible 3px focus ring and press feedback, matching
the reference's own stated principle ("Controls share a 48px comfort target,
visible keyboard focus, and contrast-safe states").

**Structure.** The reference keeps all chrome — logo, navigation, and utility
controls — in one sidebar column rather than splitting it across a header and
a rail. The app's separate top bar was removed; the theme toggle, collapse
toggle, and profile button moved into the sidebar's footer.

**Recurring pattern.** "SECTION / Display Heading / description" repeats at
two scales: `Page` for the page itself, `SectionCard` for panels within it
(the reference's "Weekly Thread" / "Current Care" cards). A card's eyebrow
color defaults to its own page's section color, but can be overridden to
borrow another section's color when a card is deliberately cross-referencing
it — the reference's own "Current Care" panel on its Observe-equivalent page
borrows Tend's teal for exactly this reason.

## Consequences

- **Positive:** a distinctive, considered visual identity in place of a
  generic "developer tool" look; genuinely offline font loading (a real fix,
  not just a side effect); a reusable eyebrow/heading pattern that
  automatically threads section color through every page without each route
  file wiring it by hand.
- **Cost:** every shared component (`Page`, `Form`, `Table`, `AppShell`) and
  every route needed a pass; this was a full re-theme, not a token tweak.
- **specification.md's UI section (lines 767-807) is now aspirational text
  the implementation has moved past**, not a description of the app. Anyone
  reading the spec for how the app currently looks should read this ADR and
  `docs/architecture.md`'s Frontend section instead.
- Nine icon paths from the earlier icon-placement pass (ADR-adjacent work
  from two sessions prior) carry forward unchanged into the new visual
  language — they were already the correct semantic choices; only their
  color and container treatment changed (a solid mono icon becomes a
  section-tinted icon in a soft rounded badge).
