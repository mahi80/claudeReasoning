---
name: k8s-manifest-generator
description: Generate and review Kubernetes workload, Service and configuration manifests with explicit selectors, security, resources and probes.
source: https://github.com/wshobson/agents/tree/c96b5f6552dba32e4492307493ee613581430715/plugins/kubernetes-operations/skills/k8s-manifest-generator
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Kubernetes manifest development

Read target Kubernetes version, namespace, existing labels and workload conventions.
Write YAML first; this skill does not authorize cluster access, apply/delete commands,
new tooling or a deployment. Do not copy unreviewed upstream assets.

## Workload correctness
- Choose Deployment for appropriate stateless replicated workloads; assess state
  identity/storage before using StatefulSet. Do not assume all apps can scale safely.
- Match spec.selector.matchLabels with spec.template.metadata.labels exactly.
  Keep immutable selectors stable when editing existing Deployments.
- Define container image identity, ports, realistic requests/limits and shutdown.
  Readiness controls traffic; liveness can restart a container. Avoid probes that
  create restart storms because an external dependency is briefly unavailable.
- Use startup probes where appropriate for slow initialization. Avoid hardcoded
  timings that conflict with actual application startup behavior.
- Services must select intended pods and target the correct container port. Keep
  public exposure explicit; use project-approved ingress/TLS patterns.

## Security and state
Prefer non-root execution, minimal capabilities, disabled privilege escalation and
read-only roots where compatible. Avoid privileged pods, hostPath and unnecessary
service-account tokens. Set RBAC/network policies appropriate to the workload.
Do not store secret values in YAML: Kubernetes Secret base64 is not encryption.
Preserve PVCs, backups and retention; deleting a workload or namespace can destroy
state depending on controller/storage behavior.

## Validation boundaries
Use approved local schema/YAML checks with installed tools. kubectl run and
--dry-run=server contact a real cluster; even validation can invoke admission
webhooks. Some client commands still discover schemas from the API server. Do not
claim offline validation without checking those dependencies and the active context.

Report selectors, configuration checks and assumptions; distinguish syntactic
validity from rollout health. Actual cluster reads/writes, rollout and cleanup are
separate operator-approved operations. Never delete resources to bypass a failure.
