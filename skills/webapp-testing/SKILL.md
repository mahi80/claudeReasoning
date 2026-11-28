---
name: webapp-testing
description: Test local web application flows with installed browser tooling, including interactions, screenshots, console errors and edge cases.
source: https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/webapp-testing
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Local web application testing

Use configured browser MCP tools if available, or installed Playwright. Do not
install browsers, plugins or packages automatically. Shell execution, server startup
and network access retain operator approval requirements. Never test a production
write path without explicit authorization.

## Prepare
Read the repository's startup and test configuration. Identify the actual local
port rather than guessing. Prefer a running development server; do not kill another
process to free a port. If you start a server, bind locally, track that exact process
and stop only the process you own after testing.

Use a disposable test account and fixtures. Do not collect live credentials or
print private headers, cookies, tokens or full response bodies in logs.

## Inspect, then act
1. Open the actual application and wait for a specific visible readiness element.
   Do not require networkidle: polling, SSE and WebSockets may never become idle.
2. Inspect the rendered DOM or accessible snapshot before choosing controls.
3. Prefer role/name, label and stable test-ID locators over brittle CSS positions.
4. Fill or click through the real flow. Reinspect after navigation or rerendering;
   stale elements are not proof the action succeeded.
5. Assert visible outcomes and persisted state, not merely the absence of errors.
   Use bounded locator assertions rather than arbitrary sleeps.

## Coverage
Test the golden path plus meaningful edges: blank/malformed input, double-submit,
request failure, empty data, long content and relevant mobile widths. Verify focus,
keyboard access, validation feedback and that nearby flows still work. Capture
browser console errors and failed requests with sensitive data redacted.

With Playwright, isolate browser contexts and close them in a finally block. Keep
screenshots and traces under a unique workspace output directory. Do not use fixed
/tmp paths, unreviewed server-wrapper helpers or blanket process termination.

## Evidence
Report the tested URL, flows, assertions and failures without exposing credentials.
A screenshot supports visual review only if actually inspected; it does not prove
interaction behavior. If the browser, dependencies or execution approval are absent,
provide the test script and state that browser testing was not run.
