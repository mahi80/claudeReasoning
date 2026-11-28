---
name: azure-prepare
description: Prepare application and infrastructure code for Azure hosting from workload requirements without automatically creating resources or deploying.
source: https://github.com/microsoft/azure-skills/tree/7847020998043c6231929b364c35393b7cdab270/skills/azure-prepare
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Azure application preparation

Read the repository's runtime, delivery tooling and existing Azure conventions.
Do not require azd if the project already uses another delivery path. This skill
prepares code and plans only; it grants no subscription access or deployment rights.

## Discover requirements
Identify HTTP/background workloads, state, authentication, secrets, ingress/egress,
regions, availability, scale and budget. Compare suitable Azure services against
these constraints rather than generating a fixed architecture for every app.
Record assumptions and unresolved decisions in the user's existing planning format;
do not force a deployment-plan document or authoritative inter-skill handoff.

## Prepare focused changes
- Keep application build/start commands consistent with supported runtime versions
  and existing lockfiles. Add only configuration required for the selected service.
- Define health/readiness behavior, graceful shutdown and startup dependencies.
  Service availability is different from application correctness.
- Prefer managed identity and least-privilege resource access where supported.
  Reference approved secret storage; never embed connection secrets or keys.
- Separate public ingress, private dependencies and required outbound access.
  Consider networking complexity, transfer charges and platform limits.
- Generate IaC using the project's chosen approach, with explicit naming/location,
  stateful-data retention, scaling bounds and observability assumptions.
- Avoid automatic telemetry/resource creation, subscription/provider registration,
  login, secret insertion or changes to IAM.

## Validation and delivery
Use approved local builds, tests and configuration checks. Validate commands against
the installed tool version. Even a what-if or lookup can access a live subscription
and reveal sensitive values; obtain authorization first.

Report proposed service choice, cost drivers, required operator configuration and
checks actually performed. Deploy, create, import and destroy are separate approvals;
a generated template is not a verified deployment or an authorization to spend.
