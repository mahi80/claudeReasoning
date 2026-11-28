---
name: aws-cdk
description: Design and code AWS CDK stacks with safe stateful-resource retention, stable logical IDs and reviewable deployment changes.
source: https://github.com/aws/agent-toolkit-for-aws/tree/c51cbfe1a2e2c9f93a40dab35c7082caf3f0f021/skills/core-skills/aws-cdk
license: Apache-2.0, adapted; see skills/THIRD_PARTY_NOTICES.md
---

# AWS CDK development

Read the application's CDK language/version, constructs and deployment conventions.
Keep existing dependency constraints and cdk.json configuration. Write code first;
AWS access, downloads, shell execution and deployment need operator approval.

## Design and code
- Define account/region assumptions explicitly. Do not guess the active AWS account
  or use ambient credentials as authorization.
- Prefer established constructs and least-privilege IAM. Separate public entry
  points from private services; protect sensitive data in storage and transit.
- Use explicit retention/deletion settings appropriate to resource value. Stateful
  databases and buckets should not receive blanket DESTROY or autoDeleteObjects.
  Explain any requested deletion policy and seek approval for destructive behavior.
- Keep construct paths and logical IDs stable. Renaming, moving or changing keys
  can replace resources even when names look similar; inspect replacement effects.
- Keep secrets outside source/context/output. Do not log tokens or include them in
  synthesized templates. Reference approved secret stores rather than embedding
  actual values.

## Verification stages
1. Run approved offline construct assertions and synthesis when dependencies are
   available. Synthesis may execute arbitrary application code, asset builds or
   context lookups; confirm those are local before treating it as offline.
2. Inspect generated templates and security/cost changes. Check replacements,
   retained resources and data-loss exposure before any cloud comparison.
3. Cloud diff/lookup requires separate account access approval. Bootstrap, import,
   deploy and destroy are distinct operations, not automatic next steps.

Do not delete cdk.out or reset context as a generic workaround; diagnose the cause
and preserve unfamiliar artifacts. No automatic credential configuration, AWS MCP
installation or cloud writes. Report tested code separately from untested deployment.
