---
name: terraform-test
description: Design Terraform .tftest.hcl tests with explicit plan/apply behavior, provider mocks and bounded, isolated verification.
source: https://github.com/hashicorp/agent-skills/tree/5e30fa5c867ba6777c37e4206babfd08049c396f/plugins/terraform/skills/terraform-test
license: MPL-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Terraform tests

Copyright IBM Corp. 2026.
This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
A copy is included at skills/licenses/terraform-MPL-2.0.txt.

Read the installed Terraform version and project provider configuration. Native
.tftest.hcl support and mock/override features vary by version; check supported
syntax. Do not install, init, upgrade or access cloud accounts automatically.

## Start with isolated tests
Write run blocks with command = plan explicitly for configuration assertions;
Terraform test otherwise defaults to apply. A plan with real providers may access
live data sources and state, so plan mode alone does not make a test offline.
Mock every relevant provider, including aliases, or require separately approved
isolated credentials and targets before execution.

Use test variables for representative configurations and assert expected outputs,
resource attributes and required constraints. Include boundary conditions and
expect_failures for intended input validation/preconditions rather than swallowing
unexpected errors.

## Mock semantics
Terraform supports provider mocking in both plan and apply tests where the installed
version supports mocks. Computed mock attributes may be generated only at apply;
plan assertions need explicit supported overrides when those values are unknown.
Check version-specific override_during support rather than assuming mocked computed
values always exist during planning.

## Correct invocation
Use terraform test -filter=tests/example.tftest.hcl to select a test file. The filter
selects files, not individual run blocks. Do not use a positional test-file argument
or the undocumented -no-cleanup flag. Verify the installed command's help before
using additional options.

## Apply tests and cleanup
Only use real apply tests when needed, with explicit approval for resource creation,
cost, target account and destruction during cleanup. Use a disposable isolated
environment and predeclare time/resource bounds. Cleanup can fail and leave billable
resources; retain diagnostics and ask the operator to resolve them. Do not silently
apply destroy or force-unlock to make a failed test disappear.

For offline runs, use mocks and local fixtures plus approved execution. Preserve
failure output and report which providers were mocked, command mode, tests run and
remaining unverified behavior. Never claim a mock test proves a live deployment.
