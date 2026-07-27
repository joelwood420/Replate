// Replate - Phase 3 production infrastructure.
//
// Deployed with:
//   az deployment group create --resource-group <rg> \
//     --template-file infra/main.bicep --parameters infra/main.bicepparam \
//     --parameters sqlAdminPassword=<...> googlePlacesApiKey=<...>
//
// See infra/README.md for the manual prerequisites (resource group, Entra External ID
// tenant and app registrations) and the two-pass sequence needed to wire the SPA redirect
// URI.
//
// PROD ONLY (Global Rule 2). Every module takes explicit name/location/tags parameters and
// there are no environment conditionals anywhere, so adding staging later is one new
// .bicepparam plus one new resource group - but the staging plumbing itself is not built.
//
// The resource group is created by hand, not by this template.

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------------
// Naming and general
// ---------------------------------------------------------------------------------

@description('Short prefix for all resource names.')
@minLength(2)
@maxLength(10)
param namePrefix string = 'replate'

@description('Environment discriminator. Prod only for now - see Global Rule 2.')
param environmentName string = 'prod'

@description('Default region for resources without their own region constraint.')
param location string = resourceGroup().location

@description('Tags applied to every resource.')
param tags object = {
  application: 'replate'
  environment: environmentName
  managedBy: 'bicep'
}

// Three region parameters, deliberately independent. Claude on Foundry is only available
// in certain regions; the Azure SQL free offer permanently locks its region per
// subscription; Content Safety F0 has its own supported-region list. Collapsing these into
// one parameter will eventually make one of the three undeployable.

@description('Region for the Foundry account. Claude models are region-restricted - eastus2 and swedencentral host Haiku.')
param aiLocation string = 'eastus2'

@description('Region for Azure SQL. WARNING: the free offer locks this per subscription once chosen and it cannot be changed.')
param sqlLocation string = location

@description('Region for the Content Safety account. F0 has its own supported-region list.')
param contentSafetyLocation string = location

@description('Region for the schema deployment script. It runs on Azure Container Instances, which is not offered in every region Azure SQL is - and because the SQL free offer permanently locks its region per subscription, tying this to sqlLocation could box the schema step out entirely.')
param deploymentScriptLocation string = location

// ---------------------------------------------------------------------------------
// Secrets, supplied at deploy time (never written into main.bicepparam)
// ---------------------------------------------------------------------------------

@description('Azure SQL administrator password. Persisted to Key Vault for the app to read.')
@secure()
param sqlAdminPassword string

@description('Google Places API key. Persisted to Key Vault for the app to read.')
@secure()
param googlePlacesApiKey string = ''

// ---------------------------------------------------------------------------------
// SQL
// ---------------------------------------------------------------------------------

@description('Azure SQL administrator login.')
param sqlAdminLogin string = 'replateadmin'

@description('Database name. Wired to the SQL_DATABASE app setting.')
param sqlDatabaseName string = 'FoodApp'

@description('Object ID of the Entra principal to set as SQL Entra admin - normally your own user, for tooling access. Leave empty to skip.')
param entraAdminObjectId string = ''

@description('Display name of the Entra SQL admin principal.')
param entraAdminLogin string = ''

@description('Apply backend/db/schema.sql as part of the deployment. Set false to skip and use backend/scripts/apply_schema.py instead.')
param applySchema bool = true

// ---------------------------------------------------------------------------------
// Foundry / Marketplace offer acceptance
// ---------------------------------------------------------------------------------

@description('Organization name, used to accept the Anthropic Azure Marketplace offer.')
param claudeOrganizationName string

@description('Two-letter country code, used to accept the Anthropic Azure Marketplace offer.')
@minLength(2)
@maxLength(2)
param claudeCountryCode string

@description('Industry, used to accept the Anthropic Azure Marketplace offer. Lowercase.')
param claudeIndustry string = 'technology'

@description('Claude model to deploy for both the vision guess and menu extraction.')
param claudeModelName string = 'claude-haiku-4-5'

@description('"1" = Hosted on Anthropic (required for the web_search server tool), "2" = Hosted on Azure.')
@allowed([
  '1'
  '2'
])
param claudeModelVersion string = '1'

@description('Store a Foundry API key in Key Vault and wire it to ANTHROPIC_API_KEY. Required while shared/menu_extraction.py still uses Anthropic(api_key=...).')
param useFoundryApiKey bool = true

// ---------------------------------------------------------------------------------
// Entra External ID - created manually, values flow in as parameters
// ---------------------------------------------------------------------------------

@description('Entra External ID tenant ID.')
param entraTenantId string = ''

@description('SPA app registration client ID. Not a secret - public clients cannot hold one.')
param entraSpaClientId string = ''

@description('API app registration client ID - the audience the backend validates against.')
param entraApiClientId string = ''

@description('Authority URL, e.g. https://<tenant>.ciamlogin.com/<tenantId>/v2.0')
param entraAuthorityUrl string = ''

@description('JWKS URI for token signature validation.')
param entraJwksUri string = ''

@description('Enable real Entra JWT validation. shared/auth.py raises NotImplementedError while true until Phase 3 Part B implements it, so this stays false for the infra-only deploy.')
param entraIdEnabled bool = false

// ---------------------------------------------------------------------------------
// Derived names
// ---------------------------------------------------------------------------------

// uniqueString() always returns exactly 13 characters.
var suffix = uniqueString(resourceGroup().id)
var baseName = '${namePrefix}-${environmentName}'

// Storage and Cognitive Services names must be globally unique and DNS-safe: lowercase
// alphanumeric only, and storage is capped at 24 characters.
var compactName = toLower('${namePrefix}${environmentName}')

// Storage accounts and Key Vaults cap at 24 characters. Truncate the PREFIX to fit rather
// than the whole composed string - truncating the end would cut into uniqueString() and
// discard exactly the part providing collision resistance. Both budgets derive from
// compactName because it contains no hyphens, so truncation can never leave a trailing or
// doubled hyphen (Key Vault rejects both).
var storagePrefix = take(compactName, 9) //  9 + len('st') 2 + 13 = 24
var keyVaultPrefix = take(compactName, 7) //  len('kv-') 3 + 7 + len('-') 1 + 13 = 24

var names = {
  logAnalytics: '${baseName}-log'
  appInsights: '${baseName}-appi'
  storage: '${storagePrefix}st${suffix}'
  keyVault: 'kv-${keyVaultPrefix}-${suffix}'
  sqlServer: '${baseName}-sql-${suffix}'
  foundry: '${compactName}ai${suffix}'
  foundryProject: '${baseName}-aiproj'
  contentSafety: '${compactName}cs${suffix}'
  functionPlan: '${baseName}-plan'
  functionApp: '${baseName}-func-${suffix}'
  staticWebApp: '${baseName}-swa'
  schemaIdentity: '${baseName}-schema-id'
  schemaScript: '${baseName}-apply-schema'
}

var deploymentContainerName = 'app-package'

// ---------------------------------------------------------------------------------
// Modules
// ---------------------------------------------------------------------------------

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    workspaceName: names.logAnalytics
    appInsightsName: names.appInsights
    tags: tags
  }
}

// Deployed before storage and the Function App because both need its hostname for CORS.
module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'static-web-app'
  params: {
    location: location
    staticWebAppName: names.staticWebApp
    tags: tags
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: names.storage
    deploymentContainerName: deploymentContainerName
    allowedUploadOrigins: [
      staticWebApp.outputs.staticWebAppUrl
    ]
    tags: tags
  }
}

module contentSafety 'modules/content-safety.bicep' = {
  name: 'content-safety'
  params: {
    location: contentSafetyLocation
    contentSafetyName: names.contentSafety
    tags: tags
  }
}

module foundry 'modules/ai-foundry.bicep' = {
  name: 'ai-foundry'
  params: {
    location: aiLocation
    foundryAccountName: names.foundry
    foundryProjectName: names.foundryProject
    claudeModelName: claudeModelName
    claudeDeploymentName: claudeModelName
    claudeModelVersion: claudeModelVersion
    claudeOrganizationName: claudeOrganizationName
    claudeCountryCode: claudeCountryCode
    claudeIndustry: claudeIndustry
    tags: tags
  }
}

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    keyVaultName: names.keyVault
    sqlAdminPassword: sqlAdminPassword
    googlePlacesApiKey: googlePlacesApiKey
    contentSafetyKey: contentSafety.outputs.contentSafetyKey
    foundryApiKey: foundry.outputs.foundryApiKey
    useFoundryApiKey: useFoundryApiKey
    tags: tags
  }
}

module sql 'modules/sql.bicep' = {
  name: 'sql'
  params: {
    location: sqlLocation
    sqlServerName: names.sqlServer
    sqlDatabaseName: sqlDatabaseName
    sqlAdminLogin: sqlAdminLogin
    sqlAdminPassword: sqlAdminPassword
    entraAdminObjectId: entraAdminObjectId
    entraAdminLogin: entraAdminLogin
    tags: tags
  }
}

// Depends on the firewall rule inside sql.bicep - without it the deployment script's
// container cannot reach the database, intermittently.
module sqlSchema 'modules/sql-schema.bicep' = if (applySchema) {
  name: 'sql-schema'
  params: {
    location: deploymentScriptLocation
    identityName: names.schemaIdentity
    deploymentScriptName: names.schemaScript
    sqlServerFqdn: sql.outputs.sqlServerFqdn
    sqlDatabaseName: sql.outputs.sqlDatabaseName
    sqlAdminLogin: sqlAdminLogin
    sqlAdminPassword: sqlAdminPassword
    tags: tags
  }
}

module functionApp 'modules/function-app.bicep' = {
  name: 'function-app'
  params: {
    location: location
    planName: names.functionPlan
    functionAppName: names.functionApp

    storageBlobEndpoint: storage.outputs.blobEndpoint
    deploymentContainerName: storage.outputs.deploymentContainerName
    storageConnectionString: storage.outputs.connectionString
    uploadsContainerName: storage.outputs.uploadsContainerName
    jobsQueueName: storage.outputs.jobsQueueName

    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString

    sqlServerFqdn: sql.outputs.sqlServerFqdn
    sqlDatabaseName: sql.outputs.sqlDatabaseName
    sqlAdminLogin: sqlAdminLogin

    keyVaultName: keyVault.outputs.keyVaultName
    sqlPasswordSecretName: keyVault.outputs.sqlPasswordSecretName
    googlePlacesSecretName: keyVault.outputs.googlePlacesSecretName
    contentSafetySecretName: keyVault.outputs.contentSafetySecretName
    foundryApiKeySecretName: keyVault.outputs.foundryApiKeySecretName

    claudeBaseUrl: foundry.outputs.claudeBaseUrl
    claudeDeploymentName: foundry.outputs.claudeDeploymentName
    azureOpenAiEndpoint: foundry.outputs.azureOpenAiEndpoint
    embeddingDeploymentName: foundry.outputs.embeddingDeploymentName
    contentSafetyEndpoint: contentSafety.outputs.contentSafetyEndpoint
    useFoundryApiKey: useFoundryApiKey

    entraTenantId: entraTenantId
    entraApiClientId: entraApiClientId
    entraAuthorityUrl: entraAuthorityUrl
    entraJwksUri: entraJwksUri
    entraIdEnabled: entraIdEnabled

    allowedCorsOrigins: [
      staticWebApp.outputs.staticWebAppUrl
    ]

    tags: tags
  }
}

// Last: every assignment needs the Function App's principal ID.
module rbac 'modules/rbac.bicep' = {
  name: 'rbac'
  params: {
    functionAppPrincipalId: functionApp.outputs.functionAppPrincipalId
    keyVaultName: keyVault.outputs.keyVaultName
    storageAccountName: storage.outputs.storageAccountName
    appInsightsName: monitoring.outputs.appInsightsName
    foundryAccountName: foundry.outputs.foundryAccountName
    contentSafetyName: contentSafety.outputs.contentSafetyName
  }
}

// ---------------------------------------------------------------------------------
// Outputs - the contract for the backend publish, the frontend build, and Phase 4.
// Never output a key, connection string or password.
// ---------------------------------------------------------------------------------

@description('Target for: func azure functionapp publish <name>')
output functionAppName string = functionApp.outputs.functionAppName

@description('Base for the frontend VITE_API_BASE_URL - append /api')
output functionAppUrl string = functionApp.outputs.functionAppUrl

@description('Target for: swa deploy')
output staticWebAppName string = staticWebApp.outputs.staticWebAppName

@description('Register this as the SPA redirect URI in the External ID tenant.')
output staticWebAppUrl string = staticWebApp.outputs.staticWebAppUrl

output sqlServerFqdn string = sql.outputs.sqlServerFqdn
output sqlDatabaseName string = sql.outputs.sqlDatabaseName
output keyVaultName string = keyVault.outputs.keyVaultName
output storageAccountName string = storage.outputs.storageAccountName
output foundryAccountName string = foundry.outputs.foundryAccountName

@description('Base URL for the Anthropic SDK AnthropicFoundry client.')
output claudeBaseUrl string = foundry.outputs.claudeBaseUrl

@description('Deployment name to send as the `model` parameter - NOT a model id.')
output claudeDeploymentName string = foundry.outputs.claudeDeploymentName

output azureOpenAiEndpoint string = foundry.outputs.azureOpenAiEndpoint
output embeddingDeploymentName string = foundry.outputs.embeddingDeploymentName
output contentSafetyEndpoint string = contentSafety.outputs.contentSafetyEndpoint

// Echoed back so the frontend build can compose its VITE_* variables from deployment
// outputs rather than a hand-maintained second copy.
output entraTenantId string = entraTenantId
output entraSpaClientId string = entraSpaClientId
output entraAuthorityUrl string = entraAuthorityUrl
output entraIdEnabled bool = entraIdEnabled
