---
name: feature-planning
description: Turn a product or project plan into a numbered feature list with acceptance checks and a "this run" selection; load in the plan stage.
---

# Feature planning

Read the whole plan first. If a plan is long it is split into parts under docs/plan/;
read every part. Then write docs/plan/features.md in exactly this shape:

# Features
Source: docs/plan.md (and parts). Written by the delivery agent for review.

## 1. <short feature name> (this run)
- Outcome: what a user or operator can do afterwards, one sentence.
- Acceptance: <check name> passes; <what the new test proves>.
- Size: S (one file and its test) | M (two to four files) | L (needs splitting)
- Depends on: none | feature numbers
- Files: paths you expect to create or change

## 2. <name> (later)
...

## Rules
- Every feature in the plan appears once, in dependency order, numbered from 1.
- Acceptance names one of the configured checks given in the task, never a manual step.
- "this run" is the set that fits one branch: two to four files, each under about 150
  lines, tests included, finished within about twenty tool calls. Usually one or two
  S or M features. Everything else is "later", in the order it should be built.
- A feature that needs a credential, a network service or a cloud account is "later"
  unless the plan says the service already exists; the agent has none of these.
- Split an L feature into S or M parts before choosing.
- Do not invent requirements. Where the plan is unclear, add "- Question: ..." under the
  feature and choose a safe default.
- Do not edit the plan itself. The feature list is for a person to review and change.
