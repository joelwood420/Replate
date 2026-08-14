# Replate infrastructure (Phase 3)

**Empty for now.** The AWS SAM template that will live here is Phase 3 work, and Phase 3
hasn't started — the current phase is **Phase 0**, porting the backend and frontend from
Azure to AWS. See `CLAUDE.md`.

## What used to be here

A complete Bicep tree for the Azure production environment — Function App, Azure SQL, storage
account, Key Vault, AI Foundry, Content Safety, Static Web App, monitoring and RBAC. It was
written but **never deployed**, which is a large part of why moving to AWS was cheap. It is
recoverable in full from git history:

```
git show 07354af:infra/main.bicep
git show 07354af -- infra/          # everything at once
```

The project moved from Azure to AWS on 2026-08-14 because that is where the owner's study is
focused. `docs/decisions.md` records that decision and the four that came with it — DynamoDB,
Bedrock, the SERP API, and SAM over CDK.

## What will be here

One `template.yaml` (AWS SAM — a CloudFormation transform, so the deployed artifact is an
ordinary CloudFormation stack), plus the Step Functions definitions as standalone
`.asl.json` files referenced via `DefinitionUri`.

Planned resources, with their free-tier posture, are tabulated in
[`../docs/architecture.md`](../docs/architecture.md). Prod only — there is deliberately no
staging parameter set yet (CLAUDE.md Global Rule 2), though the template should be
parameterized so adding one later is a new parameter file, not a rewrite.

Deployment will be manual (`sam build && sam deploy --guided`) through Phase 3; GitHub Actions
with OIDC federated credentials to an IAM role is Phase 4.
