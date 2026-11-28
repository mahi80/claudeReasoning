---
name: vercel-react-best-practices
description: Improve React and Next.js performance by removing waterfalls, reducing bundles and avoiding unnecessary server work and rerenders.
source: https://github.com/vercel-labs/agent-skills/tree/5a37a6329fbad3666c3207392a6a7c0110e92efb/skills/react-best-practices
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# React and Next.js performance

Read the project's installed React/Next.js versions before choosing APIs. Improve
measured bottlenecks without changing behavior, introducing dependencies or exposing
private data. Profiling and execution still need the harness's approval.

## Priorities
1. Remove waterfalls. Check cheap conditions before awaiting costly work. Start
   independent requests together with Promise.all; await only where needed. Do not
   parallelize dependent work or unbounded lists. Use supported Suspense boundaries
   to stream independent sections without hiding errors.
2. Reduce the initial bundle. Prefer analyzable imports, split genuinely heavy
   optional UI with supported dynamic imports, and defer non-essential analytics.
   Confirm package exports permit direct imports before replacing a barrel import.
3. Minimize server work. Deduplicate per-request fetches with framework-supported
   caching and serialize only necessary props. Authenticate and authorize server
   actions exactly like API routes. Never put mutable per-user request state in
   module globals or share private cached responses across users.
4. Avoid duplicate client requests and listeners. Reuse the project's data-fetching
   layer instead of adding SWR solely for this skill. Bound retries and clean up
   subscriptions. Version persisted state; never store secrets in localStorage.
5. Avoid unnecessary rerenders. Derive values during render rather than syncing
   derived state in effects. Use functional state updates, lazy initialization and
   stable effect dependencies. Keep event-driven work in handlers. Memoize expensive
   work only with evidence; simple expressions rarely need memoization.
6. Render large lists efficiently and reserve image dimensions to avoid layout
   shift. Batch DOM reads and writes. Keep input responsive with supported deferred
   values/transitions. Avoid inline component definitions that reset state.
7. Optimize JS only after higher-impact issues. Use Map/Set for repeated lookup,
   early exits and bounded caching; do not add complex micro-optimizations blindly.

## Correctness gates
Keep SSR/client markup compatible. Fix hydration causes rather than broadly using
suppressHydrationWarning. Handle loading, errors, empty results and cancellation.
Do not remove accessibility, validation or authorization for a faster benchmark.

Compare before/after with the same workload, build mode and device constraints.
Verify functional flows and relevant tests. Report measured changes separately
from expected improvements; if profiling or browser checks were not run, say so.
