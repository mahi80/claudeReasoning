---
name: cloud-run
description: Prepare and review Google Cloud Run services, container behavior, authentication, scaling and deployment configuration without automatic cloud writes.
source: https://github.com/GoogleCloudPlatform/cloud-run-mcp/tree/7fec3954ca060b3491f6262b9e9bc15333d7f15e/skills/cloud-run
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Google Cloud Run preparation

Read the application's language, container build and existing GCP configuration.
Do not install gcloud/MCP tooling, run login or mutate default project/region settings.
Confirm project, region and environment from operator-provided evidence; ambient
credentials are not authorization.

## Container contract
- Listen on the service's configured PORT on the appropriate interface, not a
  hardcoded localhost-only port. Start promptly and handle termination gracefully.
- Treat instance-local files as ephemeral; use approved durable storage for state.
  Do not assume a request will return to the same instance.
- Bound concurrency to the application and dependency pools. Consider request
  timeout, CPU allocation, startup probes and min/max instance limits.
- Keep secrets outside source and image layers. Use an explicitly scoped service
  identity and least-privilege access to dependencies.

## Service configuration
Make ingress and caller authentication explicit. Public access/IAM changes are
security decisions, not defaults. Plan networking, database connections, outbound
traffic and observability with cost and connection limits in mind. Distinguish
Cloud Run services from jobs; choose behavior appropriate to the workload.

## Validation and rollout proposal
Run approved local tests/configuration validation with installed tools. Building or
pulling an image may incur network/cost and still needs approval. Live service reads
require authorized account access; deploy, IAM, secret updates, traffic changes and
delete are separate writes requiring confirmation.

Propose immutable image identity, revision strategy, expected health checks and how
traffic would return to a prior healthy revision. Do not auto-execute rollback or
delete resources. Report local verification separately from untested cloud behavior.
This skill does not bundle a provider adapter or a runnable deployment pipeline.
