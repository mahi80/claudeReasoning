---
name: aws-containers
description: Plan AWS container workloads on ECS, Fargate or EKS with explicit workload, security, availability and cost tradeoffs.
source: https://github.com/aws/agent-toolkit-for-aws/tree/c51cbfe1a2e2c9f93a40dab35c7082caf3f0f021/skills/core-skills/aws-containers
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# AWS container workload planning

This is instruction-only planning guidance; it does not install or require the AWS
MCP skill router from upstream. Use only tools explicitly configured by the operator.
Do not access accounts, pull/push images or deploy services without authorization.

## Choose from workload constraints
Read existing architecture, required protocols, persistent state, traffic, regions,
availability, team expertise and budget. Compare ECS/Fargate for managed container
operation with EKS when Kubernetes ecosystem requirements justify its additional
operational burden. Do not choose a platform merely because an example uses it.

## Review the design
- Separate task execution/image-pull roles from application task permissions.
  Grant only necessary secret, storage and service access; avoid wildcard policies.
- Keep images in an approved registry with controlled provenance and tags/digests.
  Define scanning and rollout strategy without silently enabling paid services.
- Plan networking, ingress, service-to-service access and outbound requirements.
  NAT, load balancers, logging and transfer can dominate cost.
- Specify CPU/memory requirements, health/readiness checks, graceful shutdown,
  replicas, placement, autoscaling limits and failure behavior.
- Store durable data in appropriate managed storage rather than ephemeral task
  filesystems. Consider backup, retention and recovery before changing stateful
  workload ownership.
- Plan redacted application logs, metrics and traces with retention and cardinality
  limits. Do not ship private request bodies or credentials to logging systems.

## Deliver and verify
Generate a focused IaC/configuration proposal following project conventions. Use
local configuration validation and unit tests with approval; report missing provider
or account verification. State service choice, tradeoffs, cost drivers and proposed
rollout/recovery steps. Real cluster/service changes and purchases remain separate
operator decisions; a static plan is not evidence of a working AWS deployment.
