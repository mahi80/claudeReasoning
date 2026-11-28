---
name: security-review
description: Review application code for authentication, authorization, injection, secrets, uploads and trust-boundary vulnerabilities in authorized defensive work.
source: https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/security-review
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Defensive application security review

Review the requested code and authorized local fixtures. Do not scan third-party
systems, test real credentials, perform destructive tests or run unbounded traffic.
A skill does not authorize command execution, account access or tool installation.

## Trace boundaries
Map external inputs, authenticated identity, sensitive data, privileged operations
and output sinks. Read the actual framework configuration and installed versions;
do not paste security snippets without checking their API and threat model.

## Checks
- Authenticate server-side and derive identity from the authenticated context.
  Never trust requesterId/userId from the request as proof of identity. Authorize
  every resource operation, including tenant isolation and privileged fields.
- Validate external input type and size. Parameterize SQL; avoid shell interpolation
  and unsafe deserialization. Resolve and confine file paths after symlink handling.
- Render untrusted text through appropriate escaping; avoid raw HTML insertion.
  URL validation must consider scheme and destination, not only string syntax.
- For uploads, do not trust client MIME or extension: inspect file signatures and
  decode with a bounded parser. Enforce size/count limits, safe storage names and
  archive expansion bounds; reject traversal and unexpected executable content.
- Keep credentials out of source, fixtures, logs, traces, URLs and client bundles.
  Error responses must not reveal stack traces or private data. Do not dump env.
- Use Secure and HttpOnly cookies where appropriate. Choose SameSite for actual
  cross-site flows and add CSRF protection where needed; Strict is not universal.
- Bound retries, request sizes and expensive operations. Use rate limits appropriate
  to identity and endpoint; never verify them with an uncontrolled live load test.
- Check cancellation, temporary-file cleanup and access revocation without bypassing
  the application's own approval and authorization mechanisms.

## Verify and report
Use deterministic synthetic boundary tests, including forbidden cross-tenant access
and malformed inputs. Inspect existing dependency audit output if authorized, but
do not automatically run audit fix, update packages or alter lockfiles.
For each finding cite file:line, triggering conditions, impact and a minimal remedy.
Separate reproduced issues from hypotheses. No findings is not a security certificate;
report scope, checks actually performed and remaining uncertainty.
