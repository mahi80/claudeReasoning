---
name: web-design-guidelines
description: Review UI accessibility, focus, forms, motion, performance, responsive layout and locale handling against concrete interface checks.
source: https://github.com/vercel-labs/web-interface-guidelines/blob/434b7f91364665f2f733b310ec54809bf8f37937/command.md
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Web interface review

Review the requested files and rendered behavior if available. Repository design
requirements override stylistic preferences, not accessibility or security needs.
This is a compact adaptation of the pinned guidelines, not their complete rule set.
Do not fetch or update guidelines automatically or install browser tooling.
Browser execution and other tools retain the operator's approval boundaries.

## Accessibility and focus
- Semantic buttons for actions and links for navigation; labels for controls,
  accessible names for icon buttons and alt text for meaningful images.
- Use native keyboard behavior before adding custom handlers. Provide keyboard
  and simple pointer alternatives to drag/swipe interactions.
- Maintain heading hierarchy, visible focus, dialog focus management and a main
  content skip link. Overlays and sticky headers must not obscure focused controls.
- Hide decorative icons from assistive technology; announce asynchronous status
  updates appropriately. Meaningful media needs accessible alternatives.

## Forms and state
- Use correct input types, meaningful names and appropriate autocomplete. Do not
  block paste, disable password managers globally or hide validation errors.
- Preserve input on failure; show actionable inline errors and focus the first
  relevant error. Prevent duplicate submission without locking out recovery.
- Confirm destructive actions or provide a safe undo. Warn for meaningful unsaved
  changes. Reflect shareable filters/tabs/page state in URLs where appropriate,
  never credentials or sensitive payloads.

## Layout, performance and motion
- Handle empty, long and translated content; flex children may need min-width: 0.
  Fix unintended overflow rather than hiding unreachable content.
- Reserve image dimensions, prioritize important initial media and lazy-load lower
  content. Virtualize when measured list size makes rendering expensive.
- Batch layout reads/writes; avoid layout reads during render. Keep typing cheap.
- Respect reduced motion; limit non-essential autoplay and provide controls where
  needed. Animate deliberate properties rather than transition: all.
- Test narrow screens, touch targets, safe-area insets and hybrid input devices.
  Do not disable zoom, pull-to-refresh or native navigation indiscriminately.

## Locale and hydration
Use locale-aware date/number formatting. Avoid server/client time or random-value
mismatches. Give controlled inputs onChange; suppress hydration warnings only for
an intentional, narrowly understood mismatch. Check dark-mode native controls.

## Report
List file:line, the observed issue, affected behavior and a minimal remedy. Separate
source findings from browser-verified defects and stylistic suggestions. If no
browser interaction or screenshot inspection occurred, state that explicitly;
static review alone does not establish complete accessibility compliance.
