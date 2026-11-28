---
name: aws-billing-and-cost-management
description: Analyze AWS cost evidence and estimate workload costs with explicit pricing assumptions, usage drivers and approval boundaries.
source: https://github.com/aws/agent-toolkit-for-aws/tree/c51cbfe1a2e2c9f93a40dab35c7082caf3f0f021/skills/core-skills/aws-billing-and-cost-management
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# AWS cost analysis

Use supplied billing exports or already authorized read-only tools. Do not collect
credentials, install AWS MCP tooling or assume billing account access. Distinguish
cost analysis from writes: opt-ins, budget creation, anomaly configuration, purchases,
commitments and workload modifications need explicit authorization.

## Establish scope
Record account/organization scope, region, period, currency and whether figures are
blended/unblended/amortized and include credits, refunds, tax or commitments. Confirm
which usage and pricing data are observed versus estimated. Do not label a resource
free or zero-cost merely because a binding or control plane has no line-item fee.

## Workload estimate
List compute duty cycle and replicas; memory/CPU/GPU; storage capacity, requests and
retention; database instances/IO; network egress, cross-region/zone transfer, NAT and
load balancers; logs, metrics and tracing. State unit prices with source/date when
available, and leave unknowns unknown rather than inventing current pricing.

Use baseline/expected/peak scenarios. Show formulas, monthly duration assumptions,
headroom and sensitivity to traffic or scale. Separate one-time migration/build
costs from recurring operation. A scenario estimate is not a spending authorization.

## Optimization review
Tie recommendations to evidence: idle usage, excessive transfer, log retention,
overprovisioning or unsuitable scaling. Show savings assumptions and reliability
tradeoffs. Do not automatically stop resources, reduce redundancy, delete data,
change storage classes or buy reservations/Savings Plans.

Reconcile totals to the supplied data and explain missing tags, unavailable dates
or exclusions. Report observed spend separately from forecasts and confidence
bounds. Cost Explorer/API queries may themselves be billable; seek approval for
live queries or any action that incurs new cost. No new budgets are implied by
previously completed paid evaluations.
