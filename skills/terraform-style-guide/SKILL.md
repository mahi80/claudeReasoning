---
name: terraform-style-guide
description: Write and review readable Terraform modules with explicit inputs, outputs, provider constraints and least-privilege infrastructure configuration.
source: https://github.com/hashicorp/agent-skills/tree/5e30fa5c867ba6777c37e4206babfd08049c396f/plugins/terraform/skills/terraform-style-guide
license: MPL-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Terraform module style

This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
A copy is included at skills/licenses/terraform-MPL-2.0.txt.

Read the repository's Terraform version, providers, lockfile and module conventions.
Keep existing supported constraints; do not force latest versions or regenerate the
lockfile without reason and approval. This skill grants no cloud or shell access.

## Structure
Keep provider/version requirements, variables, main resources and outputs in the
project's established files. Group related resources coherently rather than splitting
mechanically. Name resources for their role; use consistent snake_case identifiers.
Document meaningful inputs, outputs and surprising constraints, not obvious syntax.

## Inputs and outputs
Use precise types, defaults only where meaningful, and validation for external
configuration boundaries. Label sensitive values but remember that sensitive output
redaction is not encryption: secrets can still be stored in state. Avoid outputting
credentials or private connection material.

## Resources and dependencies
Use references to express dependencies; depends_on only for a real hidden dependency.
Choose count for interchangeable instances, for_each with stable keys for distinct
identities. Changing keys or resource addresses can replace resources; use reviewed
moved blocks when supported rather than deleting state to silence a diff.
Keep stateful resources protected according to the workload; explain replacement,
deletion and retention behavior before proposing changes.

## Validation and safety
- fmt/validate require command approval; validate may require initialized plugins.
  Do not automatically init, download providers or upgrade dependencies.
- A plan can read real providers, remote state and secrets. It is not an offline
  sandbox. Obtain environment/account approval before planning against live state.
- Never auto-apply, destroy, import, force-unlock or manipulate remote state.
- Treat saved plans and state as sensitive artifacts; do not put them in commits.

Return the code changes, validation actually performed and any unresolved provider
or version constraints. Applying infrastructure is a separate operator decision.
