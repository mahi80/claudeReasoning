---
name: github-actions
description: Write the GitHub Actions pipeline (test, lint, quality, gated deploy) from a fixed skeleton with pinned action versions; load in the pipeline stage.
---

# GitHub Actions pipeline

You cannot run a workflow or look up action versions. Copy the skeleton, fill in the
commands from the repository, keep the pins the operator maintains below, and let the
actionlint check and the reviewer catch the rest.

## Skeleton: .github/workflows/ci.yml

name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest -q --cov=. --cov-report=xml
      - uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage.xml
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff && ruff check .
  quality:
    needs: [test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/download-artifact@v4
        with:
          name: coverage
      - uses: SonarSource/sonarqube-scan-action@v4
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
        with:
          args: -Dsonar.qualitygate.wait=true
  deploy:
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    needs: [test, lint, quality]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4
      # one deploy step from the table below

Replace main with the base branch named in the task, and the Python steps with the
repository's own commands (Node: actions/setup-node@v4 with node-version "22", then
npm ci, npm test, npm run lint). Keep the file under about 90 lines.

## Deploy step by platform (OIDC, no stored cloud keys)
- AWS: aws-actions/configure-aws-credentials@v4 with role-to-assume from a secret and
  aws-region, then the aws CLI or the deploy action for the service in ADR-0001.
- Azure: azure/login@v2 with client-id, tenant-id and subscription-id from secrets, then az.
- Google Cloud: google-github-actions/auth@v2 with workload_identity_provider and
  service_account from secrets, then gcloud.
- Anything else: one run step calling the platform's CLI with secrets by name, and a
  note in the ADR that a person must configure the deploy identity.

## Rules
- Secrets appear only as ${{ secrets.NAME }}; never a value, never an echo of one.
- The deploy job runs only on push to the base branch and in the production environment,
  which a person protects with required reviewers.
- Pin actions to the major tags above; the operator updates this table, not the agent.
- Write an ADR for the pipeline design: triggers, jobs, gates, deploy identity.
