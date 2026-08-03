# Replate infrastructure (Phase 3)

Bicep for the **production** environment. Prod only — there is deliberately no staging
parameter file yet (CLAUDE.md Global Rule 2), though every module is parameterized so
adding one later is a new `.bicepparam` plus a new resource group, not a rewrite.

> **Nothing here has been deployed.** These templates have been written but not yet applied
> to a subscription. Work through the verification section below before trusting them.

## What gets created

| Module | Resource | Free tier? |
|---|---|---|
| `monitoring.bicep` | Log Analytics workspace + Application Insights | Ingestion grant, then per-GB (capped at 1 GB/day) |
| `storage.bicep` | Storage account: `uploads` container, `jobs` queue, deployment package container | **No** |
| `keyvault.bicep` | Key Vault (RBAC mode) + the four app secrets | **No** (per-operation, negligible) |
| `sql.bicep` | Azure SQL server + free-offer database | Yes — 100k vCore-s + 32 GB/month |
| `sql-schema.bicep` | Deployment script applying `backend/db/schema.sql` | **No** (transient ACI, seconds) |
| `ai-foundry.bicep` | Foundry account + project + Claude Haiku 4.5 + `text-embedding-3-small` | **No** — pay per token |
| `content-safety.bicep` | Content Safety account (F0) | Yes — 5,000 images/month |
| `static-web-app.bicep` | Static Web App (Free) | Yes — 100 GB bandwidth/month |
| `function-app.bicep` | Flex Consumption plan + Function App | Yes — 250k exec + 100k GB-s/month |
| `rbac.bicep` | Role assignments for the Function App's managed identity | n/a |

**Nothing here carries a fixed hourly cost**, provided you leave `alwaysReady` unset on the
Function App, keep `freeLimitExhaustionBehavior: 'AutoPause'` on SQL, use `GlobalStandard`
(not provisioned throughput) Foundry deployments, and stay on the Static Web App Free tier.

SignalR / Web PubSub is deliberately **not** provisioned — the frontend polls
`GET /api/jobs/{id}` instead. See `docs/decisions.md`.

---

## Prerequisites

```bash
# Azure CLI with the Bicep extension
az --version && az bicep version

# Static Web Apps CLI, for deploying the frontend build
npm install -g @azure/static-web-apps-cli
```

### Check subscription eligibility for Claude — do this first

Claude on Foundry bills through Azure Marketplace in Claude Consumption Units. **Free-trial,
student, and credit-only subscriptions get 0 RPM / 0 ITPM and cannot use Claude at all**, and
Marketplace charges are generally not covered by Azure credits.

```bash
az cognitiveservices model list -l eastus2 \
  --query "[?contains(model.name, 'claude')].{name:model.name, version:model.version}" -o table
```

If `claude-haiku-4-5` is not listed, stop here — the model choice needs revisiting before
any of this deploys.

---

## Manual steps Bicep cannot do

### 1. Resource group

```bash
az group create --name rg-replate-prod --location eastus2
```

### 2. Entra External ID tenant and app registrations

**None of this is automatable for this project**, and the reasons are worth knowing:

- The **tenant** does have an ARM type
  (`Microsoft.AzureActiveDirectory/ciamDirectories`), but the underlying API requires a
  *delegated user token* — it fails under a service principal or managed identity, so it
  could never run in the Phase 4 GitHub Actions OIDC workflow.
- The **app registrations** are Microsoft Graph objects. The Graph Bicep extension is GA,
  but it creates objects in the tenant the deployment authenticates against — your
  subscription's home tenant — while these must live in the *separate* External ID tenant.
  One `az deployment group create` cannot straddle two tenants.

So, in the Azure portal:

1. Create an **Entra External ID** tenant (Microsoft Entra ID → External Identities).
2. Register a **SPA** application. Platform: Single-page application.
   Leave the redirect URI blank for now — you need the Static Web App hostname, which does
   not exist until after the first deploy (see the two-pass note below).
3. Register an **API** application and expose a scope (e.g. `access_as_user`).
4. Grant the SPA delegated permission to that API scope.
5. Create a **sign-up and sign-in user flow** and associate both apps with it.
6. Record: tenant ID, SPA client ID, API client ID, authority URL
   (`https://<tenant>.ciamlogin.com/<tenantId>/v2.0`), and JWKS URI.

Put those values into `main.bicepparam`. A tenant ID and a public-client SPA client ID are
not secrets — a SPA cannot hold one — so they belong in the parameter file, not Key Vault.

### 3. Secrets

`main.bicepparam` reads these from the environment via `readEnvironmentVariable()`, so their
values stay in your shell and never enter source control (Global Rule 4). `keyvault.bicep`
persists them into Key Vault on first deploy.

```bash
export SQL_ADMIN_PASSWORD='<generate a strong password>'
export GOOGLE_PLACES_API_KEY='<from Google Cloud console>'
```

`SQL_ADMIN_PASSWORD` has no fallback — the deploy fails fast if it is unset rather than
provisioning an empty password. `GOOGLE_PLACES_API_KEY` may be omitted on later deploys;
`keyvault.bicep` leaves an already-stored secret untouched when the parameter is blank.

> Note: `--parameters sqlAdminPassword=...` on the command line does **not** work alongside
> a `.bicepparam` file. A params file must assign every parameter that has no default, so
> the assignment has to live in the file — hence `readEnvironmentVariable()`.

---

## Deploy

```bash
az deployment group create \
  --resource-group rg-replate-prod \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

Preview first — this is read-only and creates nothing:

```bash
az deployment group what-if \
  --resource-group rg-replate-prod \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

Compile-only checks, no subscription needed:

```bash
az bicep build --file infra/main.bicep --outfile "$TEMP/main.json"
az bicep lint  --file infra/main.bicep
```

(On Windows, `--outfile /dev/null` fails with `Unsupported Windows DOS device path` — the
Bicep CLI needs a real path, so write the compiled JSON somewhere disposable.)

> ⚠️ Do **not** commit the output of `az bicep build-params`. It resolves
> `readEnvironmentVariable()` and writes the actual secret values into the generated JSON.
> Use it for validation only, and delete the output.

### The deploy is two-pass, by necessity

The SPA redirect URI needs the Static Web App hostname, which does not exist until the
first deploy completes:

1. Deploy with the Entra parameters blank.
2. `az deployment group show ... --query properties.outputs.staticWebAppUrl.value -o tsv`
3. Register that URL as the SPA redirect URI in the External ID tenant.
4. Fill in the Entra parameters in `main.bicepparam` and redeploy.
5. Build and deploy the frontend (below).

---

## Immediately after the first deploy

### 1. Confirm `VECTOR` works on the free-tier database

The entire `CulinaryEmbeddings` design depends on this. The vector data type is documented
for Azure SQL Database with no service-tier qualifier and a 1998-dimension maximum, so it
should be fine — but confirm before building anything else on it.

```bash
python backend/scripts/apply_schema.py --dry-run   # sanity-check the file first

sqlcmd -S <sqlServerFqdn> -d FoodApp -U replateadmin -P "$SQL_ADMIN_PASSWORD" -Q "
  CREATE TABLE dbo.__vec_probe (v VECTOR(1536) NOT NULL);
  DROP TABLE dbo.__vec_probe;
  PRINT 'VECTOR(1536) supported.';
"
```

If this fails, the embeddings design has to change and everything downstream of it is
wasted work.

*(Brute-force `VECTOR_DISTANCE` — what `activities/query_culinary_embeddings.py` does — is
what matters here. DiskANN vector *indexing* is the tier-restricted feature, and this
project does not use it.)*

### 2. Confirm the ODBC driver exists in the Flex Python image

`shared/config.py` defaults `SQL_ODBC_DRIVER` to `ODBC Driver 18 for SQL Server` and
`requirements.txt` pins `pyodbc`. A missing driver surfaces as an opaque
`('01000', "...can't open lib...")` inside a Durable activity — miserable to diagnose.

```bash
func azure functionapp publish <functionAppName>
# then, from the Kudu / SSH console:
python -c "import pyodbc; print(pyodbc.drivers())"
```

If `ODBC Driver 18 for SQL Server` is absent, options are: set `SQL_ODBC_DRIVER` to
`ODBC Driver 17 for SQL Server`, swap `pyodbc` for `pymssql` / `mssql-python`, or move to a
custom container image.

### 3. Confirm the `web_search` server tool works on Foundry

`shared/menu_extraction.py` calls Claude with the `web_search_20260209` server tool, per the
2026-07-23 decision in `docs/decisions.md`. Foundry's published capability table lists only
client-executed tools, and the web-search documentation says Foundry requires a **"Hosted on
Anthropic"** deployment — which is what `claudeModelVersion = '1'` selects.

Make one real call before building further on it. If web search is not available, the
menu-fetch strategy needs revisiting (SERP API, or a fetch-then-extract split) and a new
`docs/decisions.md` entry.

### 4. Confirm every Key Vault reference resolved

A Key Vault reference to a missing secret fails at **app runtime, not deploy time** — the
setting resolves to empty and `shared/config.py` raises `KeyError` inside a Durable
activity.

```bash
az webapp config appsettings list --name <functionAppName> \
  --resource-group rg-replate-prod -o table
```

Then check the portal's **Key Vault references** blade under the Function App's
Configuration — every entry should show `Resolved`, not `Failed`. Allow ~5 minutes after
deployment for role propagation.

---

## Deploy the applications

### Backend

```bash
cd backend
func azure functionapp publish <functionAppName>
curl https://<functionAppUrl>/api/ping     # expect "pong"
```

### Frontend

**The `VITE_*` variables are build-time.** `npm run build` bakes them into `frontend/dist`;
they cannot be set on the Static Web App afterwards. This is the most likely way to ship a
frontend still pointing at `http://localhost:7071/api`.

```bash
cd frontend
cat > .env.production <<EOF
VITE_API_BASE_URL=<functionAppUrl>/api
VITE_ENTRAID_ENABLED=true
VITE_ENTRA_CLIENT_ID=<entraSpaClientId>
VITE_ENTRA_AUTHORITY_URL=<entraAuthorityUrl>
EOF

npm run build
swa deploy ./dist --deployment-token "$(az staticwebapp secrets list \
  --name <staticWebAppName> --query properties.apiKey -o tsv)" --env production
```

All the values above come from the deployment outputs:

```bash
az deployment group show --resource-group rg-replate-prod --name main \
  --query properties.outputs -o json
```

---

## Known limitations and follow-ups

- **`allowSharedKeyAccess` is `true`.** `shared/blob.py` mints SAS tokens with the account
  key, and `shared/config.py` reads a plain `AzureWebJobsStorage` connection string.
  Moving `blob.py` to user-delegation SAS (`get_user_delegation_key()`) would let this be
  set to `false`; `rbac.bicep` already has a `grantBlobDelegator` switch ready for it.
- **`ENTRAID_ENABLED` defaults to `false`.** `shared/auth.py` raises `NotImplementedError`
  when it is true, because real JWT validation is Phase 3 Part B work.
- **`useFoundryApiKey` defaults to `true`.** `shared/menu_extraction.py` still constructs
  `Anthropic(api_key=...)`. Switching it to `AnthropicFoundry` with a managed-identity token
  provider allows `useFoundryApiKey = false` and `disableLocalAuth = true` — zero secrets.
  The `Cognitive Services User` role assignment is already in place for it.
- **One storage account, not two.** CLAUDE.md Phase 3 step 1 mentions a separate account for
  Durable Functions state; this uses one. Durable namespaces its own blobs, queues and
  tables by task hub name (`ReplateHub`), so there is no collision, and storage has no free
  tier either way. See the header comment in `storage.bicep`.
- **The SQL free offer locks its region per subscription.** Once a free database is created
  in a region, all free databases in that subscription must use it. Choose deliberately.
- **`AutoPause` is an availability trade, not a pure win.** Exhausting the free limit takes
  the database offline until the next calendar month rather than billing. Add an Azure
  Monitor alert (alert rules are free) on the *Free amount remaining* metric below
  10,000 vCore-seconds. Switching to `BillForUsage` later is **one-way**.
