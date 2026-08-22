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
3. **Build and publish the React app** to the site bucket. Publish in **two passes** so the
   cache headers are right — this matters: a single header-less `s3 sync` leaves `index.html`
   with no `Cache-Control`, and browsers then serve a stale app shell (old JS) on the next
   deploy without revalidating. The hashed `assets/*` files are content-addressed so they're
   safe to cache forever; `index.html` must always be revalidated.
   ```bash
   cd ../frontend && npm run build

   # 1. Hashed assets first — immutable, and --delete prunes superseded files.
   aws s3 sync dist/ "s3://<SiteBucketName output>/" --delete \
     --exclude "index.html" \
     --cache-control "public, max-age=31536000, immutable"

   # 2. index.html last — never silently cached, so a deploy is picked up immediately.
   aws s3 cp dist/index.html "s3://<SiteBucketName output>/index.html" \
     --cache-control "no-cache" \
     --content-type "text/html; charset=utf-8"

   aws cloudfront create-invalidation --distribution-id <CloudFrontDistributionId output> --paths "/*"
   ```
   Until this runs the CloudFront URL serves nothing — the site bucket starts empty.

   > **Note:** the CloudFront invalidation only clears the *edge* cache. It does not touch a
   > browser that already cached a header-less `index.html` (or registered a service worker)
   > from an earlier deploy — that profile needs a manual **Clear site data**. The two-pass
   > headers above are what prevent this happening to returning users going forward.
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

## CI/CD (Phase 4)

Deployment is automated with GitHub Actions, prod only. The manual `sam` commands above still
work and are the fallback; day to day, merging to `main` deploys. Auth is OIDC to an IAM role,
so there are no AWS keys in GitHub. See `docs/decisions.md` (2026-08-22).

- `.github/workflows/deploy-infra.yml` runs `sam build` + `sam deploy` on any push to `main`
  under `infra/**` or `backend/**` (or on manual dispatch). Functions and infra are one stack,
  so this single workflow deploys the backend too.
- `.github/workflows/deploy-frontend.yml` builds the React app and publishes it (the same
  two-pass sync + CloudFront invalidation as above) on any push to `main` under `frontend/**`.
  It reads `ApiBaseUrl`, `UserPoolId` and `UserPoolClientId` from the stack outputs at build
  time, so the site never drifts from the deployed API and user pool.
- `.github/workflows/ci.yml` runs on every pull request: `sam validate --lint`; the frontend
  job (`npm ci` → ESLint → Vitest → build); the backend unit suite (`pytest`); and the backend
  integration suite (LocalStack via `docker compose`, then `pytest -m integration`). These are
  the checks to mark **required** for merge to `main` (see the Phase 5 section below).
- `.github/workflows/e2e.yml` runs the Playwright journey against the deployed prod site
  **manually only** (`workflow_dispatch` — Actions tab -> "E2E (manual)" -> Run workflow). A
  full happy-path run drives the real pipeline and costs noticeably more than a normal recipe
  generation, so it is not wired to any automatic trigger. Prerequisites are in the Phase 5
  section below.
- `.github/workflows/teardown.yml` is manual only and deletes the stack (type the stack name to
  confirm).

### One-time bootstrap

The deploy role cannot live in this stack (it is what deploys this stack), so it has its own
small template. Deploy it once:

```bash
aws cloudformation deploy \
  --template-file infra/github-oidc.yaml \
  --stack-name replate-github-oidc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-southeast-2
```

Then, in the GitHub repo settings (Settings -> Secrets and variables -> Actions -> Variables),
add three Actions **variables**:

| Variable | Value |
|---|---|
| `AWS_REGION` | `ap-southeast-2` |
| `SAM_STACK_NAME` | `replate` |
| `AWS_DEPLOY_ROLE_ARN` | the `DeployRoleArn` output of the bootstrap stack |

No Actions **secrets** are needed: OIDC replaces access keys, and the Anthropic key stays in
SSM Parameter Store. If the account already has a GitHub OIDC provider, pass its ARN as the
`ExistingOIDCProviderArn` parameter so the bootstrap reuses it instead of failing on a
duplicate.

## Testing in CI/CD (Phase 5)

Unit tests run on every PR (the `ci.yml` jobs above). The Playwright e2e journey runs
**manually** against prod via `e2e.yml` (`workflow_dispatch`) — a full run drives the real,
paid pipeline, so it is triggered by hand, not on deploy. Two one-time setup steps make e2e
able to run:

1. **A demo Cognito user.** e2e signs in through the in-app `/signin` form, so it needs a
   permanent-password account with no email-code step. Create one with the welcome email
   suppressed and the address pre-verified (a fake domain is fine — nothing is emailed):
   ```bash
   POOL=<UserPoolId output>
   aws cognito-idp admin-create-user --user-pool-id "$POOL" \
     --username e2e-demo@replate.test --message-action SUPPRESS \
     --user-attributes Name=email,Value=e2e-demo@replate.test Name=email_verified,Value=true
   aws cognito-idp admin-set-user-password --user-pool-id "$POOL" \
     --username e2e-demo@replate.test --password '<Passw0rd!>' --permanent
   ```
   The password must satisfy the pool policy: **>= 8 chars, upper + lower + digit** (symbols
   optional). The e2e cleanup step resolves this user's `sub` from the email and deletes only
   that user's job items after each run.
2. **Two GitHub Actions secrets** (Settings -> Secrets and variables -> Actions -> Secrets),
   which the workflow injects as the demo credentials:

   | Secret | Value |
   |---|---|
   | `E2E_USER_EMAIL` | `e2e-demo@replate.test` |
   | `E2E_USER_PASSWORD` | the permanent password set above |

   The e2e job reuses the existing OIDC deploy role and the three Actions *variables* from the
   Phase 4 bootstrap — the deploy role already grants the DynamoDB + Cognito access the cleanup
   step needs, so no extra AWS config is required.

**Make the PR checks required.** So a red suite blocks merge, mark these `ci.yml` job names as
required status checks on `main` (Settings -> Branches -> add a branch protection rule for
`main` -> "Require status checks to pass"):

- `Frontend lint, test, build`
- `Backend unit tests`
- `Backend integration tests (LocalStack)`
- `Lint SAM template` (optional but cheap)

E2E is intentionally **not** a required check — it is manual-only. Each happy-path e2e run
spends real Anthropic tokens + web_search and consumes the demo user's rate-limit quota, which
is why it is triggered by hand and the suite is kept lean (one happy path plus two no-cost
failure paths).

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
- **CI/CD** is done (Phase 4): see the "CI/CD (Phase 4)" section above. The one-time step is
  deploying `github-oidc.yaml` and setting the three Actions variables.
- **Phase 5 testing** adds two manual, one-time steps: create the e2e demo Cognito user and set
  the `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` Actions secrets, then mark the PR test jobs as
  required status checks on `main`. See "Testing in CI/CD (Phase 5)" above.
