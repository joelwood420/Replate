// Production parameters for Replate.
//
// PROD ONLY (Global Rule 2) - this is deliberately the only parameter file. Adding staging
// later means a second .bicepparam and a second resource group, not edits here.
//
// NO SECRETS IN THIS FILE (Global Rule 4). The two @secure() parameters are read from the
// environment at deploy time via readEnvironmentVariable(), so their values live in your
// shell (or your CI secret store), never in source control:
//
//   export SQL_ADMIN_PASSWORD='<strong password>'
//   export GOOGLE_PLACES_API_KEY='<from Google Cloud console>'
//
//   az deployment group create \
//     --resource-group rg-replate-prod \
//     --template-file infra/main.bicep \
//     --parameters infra/main.bicepparam
//
// SQL_ADMIN_PASSWORD has no fallback - the deploy fails fast if it is unset rather than
// silently provisioning an empty password. GOOGLE_PLACES_API_KEY defaults to empty, since
// after the first deploy the secret is already in Key Vault and keyvault.bicep leaves a
// stored secret untouched when the parameter is blank.
//
// (Passing these with `--parameters name=value` on the command line does NOT work here:
// a .bicepparam file must assign every parameter that has no default, so the assignment
// has to live in this file.)

using './main.bicep'

param sqlAdminPassword = readEnvironmentVariable('SQL_ADMIN_PASSWORD')
param googlePlacesApiKey = readEnvironmentVariable('GOOGLE_PLACES_API_KEY', '')

param namePrefix = 'replate'
param environmentName = 'prod'

// Regions are independent on purpose - see the comments in main.bicep.
//   location            - general resources
//   aiLocation          - must be a region that hosts Claude Haiku on Foundry
//   sqlLocation         - LOCKED per subscription by the free offer once first used
//   contentSafetyLocation - F0 has its own supported-region list
param location = 'eastus2'
param aiLocation = 'eastus2'
param sqlLocation = 'eastus2'
param contentSafetyLocation = 'eastus2'

// --- SQL ---------------------------------------------------------------------------
param sqlAdminLogin = 'replateadmin'
param sqlDatabaseName = 'FoodApp'
param applySchema = true

// Set these to your own Entra user so you can connect with Azure Data Studio / the VS Code
// mssql extension without the SQL admin password. Find your object ID with:
//   az ad signed-in-user show --query id -o tsv
param entraAdminObjectId = ''
param entraAdminLogin = ''

// --- Foundry -----------------------------------------------------------------------
// These three accept the Anthropic offer on Azure Marketplace on your behalf, which is why
// no separate portal click-through is needed. Industry must be lowercase.
param claudeOrganizationName = 'Replate'
param claudeCountryCode = 'GB'
param claudeIndustry = 'technology'

param claudeModelName = 'claude-haiku-4-5'
// '1' = Hosted on Anthropic. Required for the web_search server tool that
// shared/menu_extraction.py depends on. '2' = Hosted on Azure.
param claudeModelVersion = '1'

// True while shared/menu_extraction.py still constructs Anthropic(api_key=...).
// Flip to false in Phase 3 Part B once it uses AnthropicFoundry with a managed-identity
// token provider - the Cognitive Services User role assignment is already in place.
param useFoundryApiKey = true

// --- Entra External ID -------------------------------------------------------------
// The tenant and both app registrations are created MANUALLY (Bicep cannot do either -
// see infra/README.md). Fill these in after the manual step, then redeploy.
//
// entraIdEnabled stays false until Phase 3 Part B implements real JWT validation:
// shared/auth.py raises NotImplementedError when it is true.
param entraTenantId = ''
param entraSpaClientId = ''
param entraApiClientId = ''
param entraAuthorityUrl = ''
param entraJwksUri = ''
param entraIdEnabled = false
