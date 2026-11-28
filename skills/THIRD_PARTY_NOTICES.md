# Skill source attribution and modifications

This pack contains compact, instruction-only adaptations made on 2026-11-28.
The exact source revision and file path for each of the 33 adapted skills is in
[provenance.json](provenance.json). The original eight delivery/report skills are
not part of this upstream import. Inclusion implies no upstream endorsement.

## Changes applying to every adapted skill

Bodies were condensed below 4,500 bytes, descriptions made single-line, and folder
names matched to the loader. Instructions were rewritten for this harness's actual
tools, approvals, workspace confinement and shared budgets. No upstream scripts,
installers, hooks, plugins, fonts, images, examples, datasets or provider adapters
were copied. The pack is procedural guidance, not newly installed execution tools.
Missing dependencies and denied execution must be reported rather than bypassed.

These are modified versions, not complete or unchanged upstream skill packages.
A skill authorizes no account access, purchase, cloud write, deployment, commit,
push or publication. Stored source/license links are attribution, not instructions
to fetch or execute anything automatically.

## Apache-2.0 sources

- [Anthropic skills](https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba):
  docx, xlsx, pdf, pptx, frontend-design, webapp-testing and mcp-builder.
  Full per-skill Apache license: [anthropic-APACHE-2.0.txt](licenses/anthropic-APACHE-2.0.txt).
  Removed preinstalled/auto-install assumptions and unsafe shell examples/helpers.
  Office guidance preserves input artifacts and separates structural checks,
  recalculation and visual verification. PPTX is a condensed workflow, not the
  upstream 28 KB guide. Browser waits use concrete readiness, not mandatory
  networkidle. SDK APIs follow installed versions, not a forced migration.
  Upstream third-party notices concern tools/fonts not copied in this pack.
- [AWS agent toolkit](https://github.com/aws/agent-toolkit-for-aws/tree/c51cbfe1a2e2c9f93a40dab35c7082caf3f0f021):
  aws-cdk, aws-containers and aws-billing-and-cost-management.
  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
  Full [license](licenses/aws-APACHE-2.0.txt) and verbatim [NOTICE](licenses/aws-NOTICE.txt).
  Removed automatic MCP routing and account configuration; no blanket bucket
  deletion, cdk.out cleanup, opt-ins, purchases or cloud execution.
- [Cloudflare skills](https://github.com/cloudflare/skills/tree/ff191de7d903788eceaf516a514ae7d3b56b924a):
  workers-best-practices. Full [license](licenses/cloudflare-APACHE-2.0.txt).
  Omitted always-valid authentication placeholders and unclosed client examples;
  corrected zero-cost assumptions and removed version/install/deploy mandates.
- [Google Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp/tree/7fec3954ca060b3491f6262b9e9bc15333d7f15e):
  cloud-run. Full [license](licenses/cloud-run-APACHE-2.0.txt).
  Replaced required login/project mutation and deployment with preparation and
  explicit approval boundaries. No GKE skill is included: the reviewed GKE source
  tree contained no SKILL.md files.

## MIT sources

- [Ponytail by DietrichGebert](https://github.com/DietrichGebert/ponytail/tree/ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10):
  ponytail. Copyright (c) 2026 DietrichGebert.
  [License](licenses/ponytail-MIT.txt). Removed slash activation and persistent
  session mode; kept smallest-complete-change guidance and safety floor.
- [Superpowers by Jesse Vincent](https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7):
  systematic-debugging, test-driven-development, verification-before-completion.
  Copyright (c) 2025 Jesse Vincent. [License](licenses/superpowers-MIT.txt).
  Removed secret logging, unreviewed helpers, forced code deletion/reverts and
  mandatory orchestration. Kept evidence, regression tests and bounded diagnosis.
- [Matt Pocock skills](https://github.com/mattpocock/skills/tree/bbadaa631c37af594e5a05c9cefacd9956136b18):
  code-review. Copyright (c) 2026 Matt Pocock.
  [License](licenses/mattpocock-MIT.txt). Retained separate standards/spec axes;
  removed tracker setup/slash commands and mandatory parallel agents.
- [Vercel React guidance](https://github.com/vercel-labs/agent-skills/tree/5a37a6329fbad3666c3207392a6a7c0110e92efb):
  vercel-react-best-practices. The pinned README and skill frontmatter declare MIT;
  no copyright line or root license file was supplied there.
  [MIT permission/disclaimer text](licenses/vercel-react-MIT.txt).
  Retained priority ordering, not all 70 rules; removed required libraries and
  broad hydration/caching shortcuts, and emphasized measured behavior/security.
- [Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines/blob/434b7f91364665f2f733b310ec54809bf8f37937/command.md):
  web-design-guidelines. Copyright (c) 2025 Vercel Labs.
  [License](licenses/vercel-guidelines-MIT.txt). Discovered through the pinned
  Vercel catalog. Condensed rules and removed blanket autocomplete, overflow and
  native-navigation restrictions; this is not the full unchanged guideline set.
- [ECC by Affaan Mustafa](https://github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53):
  api-design, database-migrations, docker-patterns, security-review, python-testing.
  Copyright (c) 2026 Affaan Mustafa. [License](licenses/ecc-MIT.txt).
  Omitted unsafe snippets and plugin/auth relays. Identity derives from server
  authentication; uploads need byte validation; backfills advance past NULL/empty
  sources; tests do not assume rollback isolation or live services. No automatic
  dependency updates, destructive Docker cleanup or database resets.
- [Microsoft Azure skills](https://github.com/microsoft/azure-skills/tree/7847020998043c6231929b364c35393b7cdab270):
  azure-prepare and azure-diagnostics. Copyright (c) 2025 Microsoft Corporation.
  [License](licenses/azure-MIT.txt). Removed azd-only and mandatory document/handoff
  rules; kept evidence-only diagnosis and separated resource creation from guidance.
- [Seth Hobson agents](https://github.com/wshobson/agents/tree/c96b5f6552dba32e4492307493ee613581430715):
  k8s-manifest-generator and distributed-tracing. Copyright (c) 2024 Seth Hobson.
  [License](licenses/wshobson-MIT.txt). No unreviewed assets/deployment examples or
  deprecated exporters were copied. Cluster validation/contact remains explicit.
  A second GitHub Actions skill was not added; the delivery runner already has one.

## MPL-2.0 source

[HashiCorp agent skills](https://github.com/hashicorp/agent-skills/tree/5e30fa5c867ba6777c37e4206babfd08049c396f):
terraform-style-guide and terraform-test. The terraform-test metadata supplies
Copyright IBM Corp. 2026. Full [MPL-2.0 license](licenses/terraform-MPL-2.0.txt).
Both adapted SKILL.md files retain their MPL notice and remain available as editable
source under MPL-2.0; this does not relicense unrelated harness files.

Removed forced latest versions and undocumented test invocation/cleanup flags.
Corrected file-filter semantics, mock support in plan and apply, unknown computed
values and the fact that a real-provider plan can access live resources. No
unreviewed reference files or cloud apply tests were copied.

## CC BY 4.0 content and retained Apache attribution

Source: [Antigravity Awesome Skills (AAS)](https://github.com/sickn33/antigravity-awesome-skills/tree/560a2b034d8ce3eb90445841ab6a53df7132926a).
The source [content-license declaration](licenses/aas-CONTENT.txt) distinguishes
original written content (CC BY 4.0) from code (MIT). The source code license with
Copyright (c) 2026 Antigravity User is retained at [aas-MIT.txt](licenses/aas-MIT.txt);
no upstream helper code was imported.

- **Agent Evaluation** (`agent-evaluation`), attributed upstream to Vibeship Spawner Skills (Apache-2.0)
  and modified by AAS maintainers. Previous modification: 2026-09-05 removed
  unsupported benchmark claims, corrected uncertainty/error reporting, and
  separated architecture sketches from the operating procedure. This pack retains
  that attribution and also applies CC BY 4.0 to the AAS written modifications.
  The [Apache-2.0 text](licenses/anthropic-APACHE-2.0.txt) is included for the retained
  upstream terms. No architecture sketches or executable helper were copied.
- **AI Prompt Regression Testing** (`ai-prompt-regression-testing`), Ranjeet2063
  (source metadata also names Ranjeet2063/agentic-awesome-skills), via AAS. CC BY 4.0.
- **Agent Evaluation Reporting** (`agent-evaluation-reporting`), Whxuan0701, via AAS.
  CC BY 4.0.

These three entries were condensed and adapted on 2026-11-28. Removed provider/tool
mandates, external report destinations and missing related-skill links; kept frozen
contracts, distinct outcomes, all attempts, critical safety gates and uncertainty.
No OpenJudge pairwise helper is included because its reviewed tie/swap handling
was incorrect. No noncommercial-only evaluation skill was imported.

License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
with full [legal text](licenses/CC-BY-4.0.txt). Attribution and prior modification
notices must remain with redistribution. These sources are supplied as-is with
no warranty; the licenses contain the full disclaimers. Do not imply endorsement
or add restrictions that prevent recipients from complying with these terms.
