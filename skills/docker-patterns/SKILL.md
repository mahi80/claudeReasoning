---
name: docker-patterns
description: Write and review Dockerfiles and Compose configurations for reproducible, least-privilege local and production containers.
source: https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/docker-patterns
license: MIT, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# Container development

Inspect the repository's runtime, lockfiles and existing container conventions.
Generate configuration without automatically building, pulling, starting or pushing
images. Docker commands can access the host and network; require operator approval.
Do not install plugins, relay authentication or change global npm configuration.

## Dockerfiles
- Use a suitable supported base and project-approved version/digest. Do not force
  the latest image or downgrade dependencies to match a sample.
- Use multi-stage builds when they materially reduce runtime size. Keep lockfile-
  based dependency installation deterministic and order layers for useful caching.
- Add a .dockerignore that excludes credentials, local environments, caches and
  irrelevant artifacts while retaining required build inputs.
- Never COPY secrets or bake tokens into ARG/ENV/layers. Use an approved build-secret
  mechanism when needed; image history can expose supposedly deleted content.
- Run as a non-root user where compatible. Avoid privileged mode, host mounts and
  Docker-socket access. Use only necessary filesystem permissions and capabilities.
- Use exec-form entrypoints and make signal/shutdown behavior explicit.

## Compose and service lifecycle
Use service DNS names rather than localhost between containers. Keep development
ports local unless exposure is requested. Use named volumes for intentional durable
state and distinguish them from disposable caches. Define readiness/health checks
and bounded retries; depends_on alone is not proof an app or database is ready.
Set meaningful resource limits supported by the intended runtime.

## Verification and safety
Review rendered configuration and build logs for missing inputs and secrets, then
use an approved disposable environment for health, restart and signal tests.
Never run prune, system cleanup, volume deletion or down -v as a routine fix.
Never replace another user's container or erase persistent database volumes.
Publishing to registries and production rollout are separate approvals. State
whether configuration was only reviewed or actually built and exercised.
