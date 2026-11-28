---
name: adr
description: Architecture decision records: when to write one, the template the lint enforces, numbering and the index; load whenever a design decision is made.
---

# Architecture decision records

Write an ADR whenever you choose between options a reviewer could question: the
platform, a framework or library, a data store or schema shape, the CI design, quality
thresholds, a deviation from the plan. A small local choice needs none.

## File and name
docs/adr/NNNN-slug.md: four digits, then lowercase words joined by hyphens, for example
docs/adr/0002-postgres-for-orders.md. Numbers are unique and increase; read
docs/adr/README.md to find the next one. Keep each record under 1500 characters so it
fits one write_file and survives summarisation (the lint rejects more than 6000 bytes).

## Template (the lint checks the first line, the two fields and the five headings in order)

# NNNN. Short title as a noun phrase or in the imperative
Status: Proposed
Date: YYYY-MM-DD

## Context
Two to four sentences: the forces, requirements and constraints that matter.

## Decision
What was decided, in one or two sentences, and the main reason.

## Consequences
What becomes easier, what becomes harder, what must follow (work items, costs, risks).

## Alternatives considered
One line per alternative and why it lost. A table is fine.

## Assumptions to confirm
- [ ] Each fact assumed, as a checkbox a reviewer can tick. Write "None." if none.

## Status values
Proposed (new), Accepted (a person accepted it), Rejected, Deprecated, Superseded by
NNNN. Only a person changes Proposed to Accepted. Never edit an Accepted record's
Decision; write a new record that supersedes it.

## Index
docs/adr/README.md lists every record, one line each:
- [0001](0001-platform.md) Platform: managed container service (Proposed)
Add the new line when you add a record. The lint fails when a record is missing from
the index or the index names a file that does not exist.
