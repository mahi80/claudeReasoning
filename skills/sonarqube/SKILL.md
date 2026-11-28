---
name: sonarqube
description: Configure the SonarQube project file, the coverage report and the CI quality-gate job, and record the thresholds in an ADR; load in the quality stage.
---

# SonarQube quality gate

The authoritative scan runs in CI on the pull request; you cannot see that result. If
the operator configured a check named sonar, run it with run_checks after writing the
project file: it is the same scanner, and it fails on a red gate. Otherwise make the
configuration right, keep the code small and tested, and record the thresholds.

## sonar-project.properties (repository root)
sonar.projectKey=<org>_<repo>            (from docs/constraints.md or the repository name)
sonar.organization=<org>                 (SonarCloud only; omit for a self-hosted server)
sonar.sources=.
sonar.tests=.
sonar.test.inclusions=**/tests/**,**/test_*.py,**/*_test.py,**/*.test.js,**/*.spec.ts
sonar.exclusions=**/__pycache__/**,**/node_modules/**,**/.venv/**,docs/**,**/.scannerwork/**
sonar.sourceEncoding=UTF-8
Python: sonar.python.version=3.12 and sonar.python.coverage.reportPaths=coverage.xml
Node:   sonar.javascript.lcov.reportPaths=coverage/lcov.info
Java:   sonar.java.binaries=target/classes and sonar.coverage.jacoco.xmlReportPaths=...
Tests may live under tests/ or next to the code (coding-conventions allows both); the
inclusions above classify both layouts as tests. The CI test step must produce the
coverage report (pytest --cov=. --cov-report=xml, or jest --coverage); change that step,
never the operator's local tests check.

## The CI job
A quality job after the tests downloads the coverage artifact, checks out with
fetch-depth 0 (new-code detection needs history), runs
SonarSource/sonarqube-scan-action@v4 with SONAR_TOKEN and SONAR_HOST_URL from secrets,
and passes -Dsonar.qualitygate.wait=true so the job fails when the gate is red. The
pull request then shows the gate as a check; the operator makes it required.

## What the default gate measures on new code
Coverage at least 80 percent, duplicated lines at most 3 percent, maintainability,
reliability and security ratings A, no new blocker or critical issue, security hotspots
reviewed. Write these thresholds, or the project's own, into an ADR titled
"Quality gate thresholds" so reviewers know what red means.

## Writing code that passes without seeing the scanner
- Functions under about 30 lines, files under about 150, no duplicated blocks: extract
  a helper instead of copying.
- Every new module has a test file; cover error paths, not only the happy path.
- No hard-coded secrets or credentials, no disabled security checks, no bare except.
- Remove dead code and commented-out code; the scanner counts them.

## Never
- Put a token in sonar-project.properties or in the workflow; only ${{ secrets.NAME }}.
- Lower a threshold to pass; propose the change in the ADR for a person to decide.
