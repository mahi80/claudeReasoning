---
name: distributed-tracing
description: Add and review OpenTelemetry tracing with correct context propagation, bounded sampling, redaction and service lifecycle handling.
source: https://github.com/wshobson/agents/tree/c96b5f6552dba32e4492307493ee613581430715/plugins/observability-monitoring/skills/distributed-tracing
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Distributed tracing

Inspect installed OpenTelemetry SDK/instrumentation versions and existing collector
configuration. Use supported exporters, typically OTLP to an approved collector;
do not paste deprecated Jaeger exporter examples. No automatic backend installation,
resource creation, account access or telemetry uploads.

## Instrument the real path
Define service identity and environment. Create spans around meaningful operations
and propagate the supported trace context across HTTP, queues and background tasks.
Keep context local to each concurrent request; use proper parent relationships or
links for asynchronous fan-out. End spans on success, exception and cancellation.
Avoid duplicate instrumentation and unbounded span creation in loops.

## Useful, safe attributes
Record bounded operation names, status, duration and non-sensitive identifiers.
Never include credentials, cookies, private prompts, payload bodies, raw SQL values
or unnecessary personal data. Control attribute lengths and cardinality; truncation
alone is not redaction. Treat incoming trace headers as untrusted external data,
not as authenticated identity or permission to bypass sampling policy.

## Reliability and overhead
Choose explicit sampling, queue/batch bounds, export timeouts and shutdown flush
behavior. Export failures must not crash the main application or retry forever.
Account for retention, ingestion and network cost. Configure endpoints/TLS/auth
through operator-managed settings rather than hardcoding secrets.

## Verify locally
Use a fake/in-memory exporter with approval to check span names, parentage, error
status, cancellation, propagation and redaction. Measure overhead on the same
workload before claiming improvement. Generated collector manifests still require
normal schema/selector validation and review; no unreviewed upstream deployment
examples are bundled.

Report which paths were instrumented, tests performed, sampling/retention assumptions
and whether any collector or live backend was actually exercised. Observability
configuration and a green SDK import do not prove end-to-end trace delivery.
