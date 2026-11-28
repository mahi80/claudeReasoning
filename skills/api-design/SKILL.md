---
name: api-design
description: Design HTTP API contracts, validation, pagination, idempotency, errors and compatibility for backend coding tasks.
source: https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/api-design
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# HTTP API design

Read existing routes, schemas, authentication and client conventions before adding
an endpoint. Preserve documented contracts; avoid imposing a new framework or
versioning scheme. Execution, dependency changes and publication need approval.

## Contract
- Name resources consistently; distinguish collection and item routes. Use HTTP
  methods for their semantics: GET must not cause application mutations.
- Define request/response schemas, required fields, limits and meaningful status
  codes. Return a stable error shape with a machine-readable code, helpful message
  and request ID, never stack traces or secrets.
- Use server-derived authentication context and check authorization for the target
  resource and operation. A caller-supplied user/tenant ID is not proof of identity.
- Validate JSON, content type, body size and field bounds at the boundary. Reject
  unknown privilege-bearing fields rather than mass-assigning request objects.
- Use parameterized queries. Limit filtering and sorting to supported fields.

## Collections and reliability
- Bound page sizes; use stable ordering and a tie-breaker. Cursor pagination is
  useful for changing datasets, while offsets can be acceptable for small stable
  collections. Document which consistency guarantees clients receive.
- For retryable creation/payment operations, scope an idempotency key to identity
  and operation, bind it to request contents and handle concurrent duplicates.
  Never claim exactly-once delivery merely because a key exists.
- Set deadlines and bounded retries; retry only operations safe to repeat. Support
  conditional updates or version checks when concurrent edits could lose data.
- Keep transaction boundaries explicit and do not hold database locks across
  external API calls. Separate committed changes from asynchronous side effects.

## Test and document
Test authenticated success, forbidden cross-tenant access, malformed/oversized input,
empty collections, pagination boundaries, duplicates and concurrency where relevant.
Use local fake services; do not probe live accounts or run unbounded load tests.
Keep examples consistent with the implementation and include security/error paths,
not just happy-path snippets. State which checks were actually run.
