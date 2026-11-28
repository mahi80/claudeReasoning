---
name: frontend-design
description: Design and implement intentional, responsive interfaces matching a product brief, with accessible typography, layout and interaction.
source: https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/frontend-design
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Intentional frontend design

Read the product brief and existing interface before choosing a visual direction.
Respect its design system, framework and installed dependencies. Do not replace a
brand or component system just to make the page distinctive.

## Plan the visual language
Identify audience, primary task and real subject matter. Choose a compact set of
color, typography, spacing and layout tokens appropriate to that brief. Use one
memorable visual idea and keep the rest disciplined. Avoid stock treatments applied
regardless of content: identical card grids, decorative gradients, numbered labels
for non-sequential content or motion on every section.

Use real provided content where available. Label illustrative data honestly; do not
invent customer claims, testimonials, metrics or third-party endorsements.

## Build
- Establish clear hierarchy and readable line lengths, usually under 80 characters.
  Select fonts already available or licensed for the requested use; do not fetch
  remote fonts or imagery without authorization.
- Keep structural devices meaningful: labels identify, rules group and numbers
  represent an actual sequence. Do not decorate at the expense of comprehension.
- Use semantic controls, visible keyboard focus, labeled inputs, adequate contrast
  and touch targets. Honor reduced motion and do not rely only on color for state.
- Make layouts responsive and resilient to empty, loading, error and long-content
  states. Preserve user input when a request fails.
- Keep CSS specificity and spacing predictable. Prefer layout primitives over JS
  measurements; reserve animation for feedback or a justified focal moment.
- Write action labels that name the outcome: Save changes rather than Submit.
  Errors identify the issue and the next step; empty states offer a useful action.

## Critique and verify
Compare the implemented page with the brief, then remove decoration that serves no
purpose. With approved browser tooling, test the main action, keyboard navigation,
narrow/wide screens, long text and failure states. Inspect console errors and visual
clipping. Do not claim UI verification from source inspection or type checking.
If browser tooling is unavailable, report that limitation explicitly. This skill
never authorizes installs, server exposure or publication.
