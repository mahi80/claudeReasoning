---
name: workers-best-practices
description: Write and review Cloudflare Workers code with request isolation, streaming, bindings, safe authentication and lifecycle cleanup.
source: https://github.com/cloudflare/skills/tree/ff191de7d903788eceaf516a514ae7d3b56b924a/skills/workers-best-practices
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Cloudflare Workers development

Read the project's Wrangler version, compatibility date, bindings and installed
libraries. Use generated types when available; do not force a Zod version or change
compatibility dates blindly. Never automatically login, insert secrets or deploy.

## Runtime correctness
- Keep request-specific mutable state inside the request handler; isolates can be
  reused and concurrent requests must not share private state.
- Stream responses when buffering would violate memory/latency goals. Avoid reading
  an unbounded request/response body; validate content type and size at the boundary.
- Use the execution context's supported waitUntil for necessary bounded background
  work, but do not treat it as a durable queue or unlimited execution guarantee.
- Use bindings instead of unnecessary public network hops where appropriate. Bindings
  can still have service/request/storage charges; never call them zero-cost blindly.
- Handle cancellation, errors and cleanup. Close/release database and Hyperdrive
  clients according to the installed driver; do not leak a connection per request.

## Security
Authentication must actually verify the credential and derive a trusted principal;
a placeholder that always returns true is not acceptable. Authorize resource access
separately. Use an available constant-time comparison for secrets/signatures, with
correct encoding and length handling, or a vetted verification API. Never compare
raw user-supplied identity strings as authentication.

Keep credentials in operator-managed secret bindings, not source or logs. Validate
upstream destinations and redirects if proxying user input. Restrict CORS to the
application's intended trust model and keep private cache entries isolated by user.

## Verification
Use approved local tooling and fake bindings for normal, unauthorized, malformed,
oversized and cancelled requests. Verify streaming and cleanup where relevant.
Remote preview, resource creation and deployment need separate approval and may
incur costs. Report code/test evidence and unverified platform behavior; this
instruction-only skill does not install Cloudflare integrations.
