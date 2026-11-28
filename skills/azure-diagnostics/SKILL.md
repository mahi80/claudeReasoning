---
name: azure-diagnostics
description: Diagnose Azure application failures using approved logs, deployment evidence, health signals and runtime configuration without automatic remediation.
source: https://github.com/microsoft/azure-skills/tree/7847020998043c6231929b364c35393b7cdab270/skills/azure-diagnostics
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Azure diagnostics

Work in evidence-only mode first. Use supplied logs and configuration or explicitly
authorized read-only telemetry tools. Do not log in, create resources, restart apps,
change networking/IAM, collect credentials or deploy fixes automatically.

## Establish the incident
Record service, environment, time window, symptom, affected request IDs and recent
changes. Verify platform status separately from application health: a running
container or healthy service control plane does not prove a working user request.

## Follow the failing path
- Build/deployment: image/version, entrypoint, required runtime, missing files and
  startup logs. Compare the deployed artifact with the intended commit.
- Ingress: DNS, TLS, routing, ports and health probes. Separate connection failures
  from application responses and authentication/authorization failures.
- Runtime: resource limits, readiness, crashes, cold starts, scaling and shutdown.
- Dependencies: managed identity/RBAC, database/storage reachability, deadlines,
  exhausted pools and upstream errors. Do not mistake denied access for absence
  of data or service availability.
- Telemetry: correlate logs, metrics and traces by stable identifiers and time.
  Keep platform logs separate from application events and deployment changes.

Use bounded queries and time windows. Redact connection strings, tokens, cookies,
private prompts and personal data before placing output in a trace or report. Do
not dump full settings or arbitrary request bodies. Missing telemetry is a limitation,
not proof the request succeeded.

## Test hypotheses
Compare a working request/environment and one suspect change. Propose the smallest
verification step that can discriminate causes. Any live probe or mutation needs
approval, particularly production operations. Avoid restarting as a diagnostic
shortcut that erases evidence.

Report observed facts, probable cause with confidence, exact supporting evidence,
remaining gaps and a scoped remediation proposal. Keep instrumentation guidance
separate from creating Application Insights or changing retention/cost settings.
