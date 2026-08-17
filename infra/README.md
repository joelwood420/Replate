# Replate infrastructure (AWS SAM)

The whole production stack as one AWS SAM template — which is to say one CloudFormation
stack, since SAM is a template transform. Prod only for now (CLAUDE.md Global Rule 2); the
template is parameterised so a staging environment is a later parameter file, not a rewrite.

```
infra/
  template.yaml          the stack: Lambda, API Gateway, Step Functions, DynamoDB, SQS,
                         S3 + CloudFront, Cognito, IAM, CloudWatch log groups
  samconfig.toml         deploy defaults — region ap-southeast-2, stub-mode overrides
  dependencies/
    requirements.txt     httpx + numpy + python-dotenv → shared Lambda layer (no boto3)
```

The Step Functions definitions are **not** in this template — they live in
`../backend/statemachines/*.asl.json` and are referenced via `DefinitionUri`, with their
`${...FunctionArn}` placeholders resolved by `DefinitionSubstitutions`, so they stay readable
and diffable on their own.

## Phase 3a: the stub deploy

This deploys with every **paid** integration off, so it runs end-to-end at no per-token cost:

| Off in 3a | How | Turned on in 3b |
|---|---|---|
| Anthropic model calls (menu, vision, recipe) | `ANTHROPIC_API_KEY` blank | create the `SecureString` param |
| Rekognition moderation | `ModerationEnabled=false` | `true` |
| Google Places | env key empty; SSM param not yet created | create the `SecureString` param |

Everything else is real: real Cognito sign-in, real API Gateway JWT authorizer, real
DynamoDB/SQS/S3/Step Functions/CloudFront. See `docs/decisions.md` (2026-08-14) for why the
line is drawn at cost rather than realism.

## Prerequisites

- **AWS CLI**, configured with credentials for the target account (`aws configure`).
- **AWS SAM CLI**.
- **Docker**, running. `sam build` uses it (`use_container = true` in `samconfig.toml`)
  because the dependency layer's numpy is a compiled wheel that must be built for the Lambda
  platform — building it straight from Windows/macOS would ship the wrong binary.

## Deploy

```bash
cd infra
sam validate --lint            # syntax + best-practice lint
sam build --use-container      # builds the layer + copies function source
sam deploy --guided            # first time; writes answers back to samconfig.toml
```

`--guided` is only needed the first time; afterwards `sam deploy` reuses `samconfig.toml`.
The stub-mode parameter overrides are already in `samconfig.toml`, so a plain deploy stays
stubbed.

### After the first deploy

1. **Read the stack outputs** (`sam list stack-outputs --stack-name replate`, or the
   CloudFormation console). You'll wire three of them into the frontend and use the rest for
   the smoke test.
2. **Point the frontend at the stack** — in `frontend/.env`:
   ```
   VITE_API_BASE_URL   = <ApiBaseUrl output>
   VITE_COGNITO_ENABLED= true
   VITE_COGNITO_AUTHORITY = <CognitoIssuer output>
   VITE_COGNITO_CLIENT_ID = <UserPoolClientId output>
   ```
3. **Build and publish the React app** to the site bucket:
   ```bash
   cd ../frontend && npm run build
   aws s3 sync dist/ "s3://<SiteBucketName output>/" --delete
   aws cloudfront create-invalidation --distribution-id <CloudFrontDistributionId output> --paths "/*"
   ```
   Until this runs the CloudFront URL serves nothing — the site bucket starts empty.
4. **Create a demo user** (Cognito has no self-serve sign-up UI wired):
   ```bash
   aws cognito-idp admin-create-user --user-pool-id <UserPoolId output> --username you@example.com
   aws cognito-idp admin-set-user-password --user-pool-id <UserPoolId output> --username you@example.com --password '<Passw0rd!>' --permanent
   ```

### Smoke test (stub pipeline)

Open the CloudFront URL → sign in → upload a photo with GPS → poll until the job reaches
`Identified` (a canned match) → press **Reverse engineer** → the job reaches `Completed` with
canned recipe elements. That exercises API Gateway → Lambda → SQS → Step Functions →
DynamoDB → S3 presigned upload end-to-end, with no Anthropic spend.

## Teardown

Most of the stack scales to zero, so there's no standing bill — teardown is for peace of mind
and wiping demo data. One catch: **CloudFormation won't delete a non-empty S3 bucket**, so
empty both first:

```bash
aws s3 rm "s3://<UploadsBucketName output>/" --recursive
aws s3 rm "s3://<SiteBucketName output>/" --recursive
cd infra && sam delete
```

Because every Lambda log group is declared in the stack (rather than left to Lambda's implicit
never-expire group), `sam delete` removes those too — nothing lingers. The one thing it can't
remove is the `SecureString` in Parameter Store (CloudFormation never created it) — delete
`/replate/anthropic-api-key` by hand if you want it gone.

## Deliberate deviations

- **Region `ap-southeast-2` (Sydney)** — closest to the owner for demo latency (see
  `docs/decisions.md`). Model calls go to the Anthropic API over the internet, so the region
  only places the free-tier infra, not the models.
- **API Gateway HTTP API, not Function URLs** — keeps the free Cognito JWT authorizer. Note
  its free tier is the **12-month** kind, not always-free (CLAUDE.md Global Rule 1); the exit
  if per-request cost ever bites is Function URLs with in-handler JWT validation.
- **S3 buckets:** SSE-S3 (AES256) encryption is on; Object Lock, cross-region replication,
  access logging and versioning are intentionally **off** — cfn-guard flags them, but they add
  real cost or conflict with the uploads lifecycle-expiry rule, and none earn their keep for a
  free-tier demo. Public access is fully blocked and the site bucket is reachable only through
  CloudFront's Origin Access Control.
- **DynamoDB is PROVISIONED 25/25** — the always-free grant. On-demand bills from the first
  request, so it is never used here.

## Not done by the template (manual, mostly 3b)

- Create the **`SecureString`** params for 3b — CloudFormation can't create SecureStrings:
  ```bash
  aws ssm put-parameter --name /replate/anthropic-api-key     --type SecureString --value '<key>'
  aws ssm put-parameter --name /replate/google-places-api-key --type SecureString --value '<key>'
  ```
  The execution roles already grant `ssm:GetParameter` on `/replate/*`; the 3b code change is
  reading them at runtime instead of from the (empty) env vars.
- **CI/CD** — deployment stays manual this phase; GitHub Actions with OIDC federated
  credentials is Phase 4.
