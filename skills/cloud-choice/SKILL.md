---
name: cloud-choice
description: Choose a cloud or platform from the plan's constraints and record it as a proposed ADR; load in the platform stage.
---

# Cloud or platform choice

You have no network, no prices and no account data. Decide from what the plan and
docs/constraints.md state, make every assumption explicit, and propose; a person
accepts the ADR before anything is deployed.

## Rubric (score each option 0-2, in a table in the ADR)
1. Required managed services the plan names (database, queue, object store, auth).
2. Existing accounts, contracts or skills the plan or constraints mention.
3. Data residency and compliance requirements.
4. Cost ceiling and expected load (small, steady, or bursty).
5. Operational burden the team accepts (servers, containers, or functions only).
6. Portability: how hard a later move would be.

## Deployment shapes
- Static site plus API: object storage with a CDN and a small API service.
- Container service: one or more containers on a managed runtime, a managed database.
- Functions: event-driven handlers behind an API gateway, managed queue and store.
- Virtual machines: only when the plan requires software that cannot run in the above.

## The ADR (docs/adr/0001-platform.md, Status: Proposed)
Follow the adr skill's template. In Decision, name the platform, the deployment shape
and the service mapping (plan requirement -> managed service). In Consequences, name
what the pipeline will need: a container registry or storage bucket, a deploy identity
via OIDC, and the secrets a person must create, by name. In Alternatives considered,
show the rubric table. In Assumptions to confirm, list every fact you assumed (budget,
region, accounts, team skills) as a checkbox line a person can tick.

## Never
- Deploy anything or write a credential; the deploy job in CI, configured by a person,
  does that later.
- Claim prices, quotas or availability you cannot see; write them as assumptions.
- Choose by vendor preference; the rubric decides and the table shows it.
