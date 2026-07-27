// Azure Functions app (Python) on a Flex Consumption plan, hosting the HTTP triggers, the
// queue trigger and the Durable Functions orchestrator.
//
// WHY FLEX CONSUMPTION (FC1) RATHER THAN CONSUMPTION (Y1): Linux Consumption is legacy for
// new Python apps and drags in the Azure Files content share
// (WEBSITE_CONTENTAZUREFILECONNECTIONSTRING / WEBSITE_CONTENTSHARE), a persistent source of
// deployment breakage. Flex uses a blob container plus managed identity instead.
//
// THE TRADE-OFF, stated plainly per Global Rule 1: Flex's monthly free grant is 250,000
// executions + 100,000 GB-seconds. Consumption's is 1,000,000 + 400,000 - four times more
// generous. At MVP volume both are almost certainly free, but if this app ever gets busy,
// Consumption's grant stretches further. Re-verify both against the current Azure Functions
// pricing page before committing.
//
// NEVER set alwaysReady on Flex: a non-zero value forfeits the free grant entirely.
//
// Flex-specific settings that will hard-fail the deploy or the app if added:
//   linuxFxVersion, FUNCTIONS_EXTENSION_VERSION, FUNCTIONS_WORKER_RUNTIME,
//   WEBSITE_RUN_FROM_PACKAGE, WEBSITE_CONTENTAZUREFILECONNECTIONSTRING, WEBSITE_CONTENTSHARE
// The runtime lives in functionAppConfig.runtime instead. alwaysOn must be false, and
// maximumInstanceCount has a floor of 40.

@description('Azure region for the plan and site.')
param location string

@description('Name of the Flex Consumption plan.')
param planName string

@description('Globally unique Function App name.')
param functionAppName string

@description('Python version for the Functions runtime.')
param pythonVersion string = '3.12'

@description('Maximum scale-out instances. The platform floor is 40.')
@minValue(40)
param maximumInstanceCount int = 40

@description('Memory per instance, in MB.')
@allowed([
  512
  2048
  4096
])
param instanceMemoryMB int = 2048

// --- Storage -----------------------------------------------------------------------
@description('Blob endpoint of the storage account, e.g. https://acct.blob.core.windows.net/')
param storageBlobEndpoint string

@description('Container holding the deployment package. Must already exist.')
param deploymentContainerName string

@description('Full storage connection string for AzureWebJobsStorage. shared/config.py reads this variable directly and shared/blob.py pulls the account key off it to mint SAS tokens, so the identity-based (__blobServiceUri) form will NOT work until blob.py moves to user-delegation SAS.')
@secure()
param storageConnectionString string

@description('Blob container the client uploads to. Wired to BLOB_CONTAINER_UPLOADS.')
param uploadsContainerName string

@description('Queue that starts the orchestrator. Wired to QUEUE_NAME_JOBS.')
param jobsQueueName string

// --- Monitoring --------------------------------------------------------------------
@description('Application Insights connection string.')
@secure()
param appInsightsConnectionString string

// --- SQL ---------------------------------------------------------------------------
@description('Fully qualified SQL server name. Wired to SQL_SERVER.')
param sqlServerFqdn string

@description('Database name. Wired to SQL_DATABASE.')
param sqlDatabaseName string

@description('SQL login. Wired to SQL_UID.')
param sqlAdminLogin string

@description('ODBC driver name. VERIFY this driver actually ships in the Flex Python image before relying on it - pyodbc failing to find a driver surfaces as an opaque ("01000", "...can\'t open lib...") error inside a Durable activity.')
param sqlOdbcDriver string = 'ODBC Driver 18 for SQL Server'

// --- Key Vault ---------------------------------------------------------------------
@description('Key Vault name, used to build @Microsoft.KeyVault references.')
param keyVaultName string

@description('Secret name holding the SQL password.')
param sqlPasswordSecretName string

@description('Secret name holding the Google Places API key.')
param googlePlacesSecretName string

@description('Secret name holding the Content Safety key.')
param contentSafetySecretName string

@description('Secret name holding the Foundry API key.')
param foundryApiKeySecretName string

// --- AI ----------------------------------------------------------------------------
@description('Foundry Anthropic base URL, e.g. https://acct.services.ai.azure.com/anthropic')
param claudeBaseUrl string

@description('Claude DEPLOYMENT name (not a model id). Wired to both MENU_FETCH_MODEL and VISION_MODEL_DEPLOYMENT.')
param claudeDeploymentName string

@description('Azure OpenAI endpoint on the Foundry account, for the embeddings call.')
param azureOpenAiEndpoint string

@description('Embedding deployment name.')
param embeddingDeploymentName string

@description('Content Safety endpoint.')
param contentSafetyEndpoint string

@description('Set true while shared/menu_extraction.py still constructs Anthropic(api_key=...). Flip to false in Phase 3 Part B once it uses AnthropicFoundry with a managed-identity token provider.')
param useFoundryApiKey bool = true

// --- Auth --------------------------------------------------------------------------
@description('Entra External ID tenant ID. Obtained manually - Bicep cannot create the tenant.')
param entraTenantId string = ''

@description('API app registration client ID - the audience the backend validates tokens against. NOT the SPA client ID, which the frontend consumes as VITE_ENTRA_CLIENT_ID.')
param entraApiClientId string = ''

@description('Authority URL, e.g. https://<tenant>.ciamlogin.com/<tenantId>/v2.0')
param entraAuthorityUrl string = ''

@description('JWKS URI for token signature validation.')
param entraJwksUri string = ''

@description('Turns on real Entra JWT validation. shared/auth.py raises NotImplementedError when this is true until Phase 3 Part B implements validation, so it defaults false.')
param entraIdEnabled bool = false

// --- Tunables (all have safe defaults in shared/config.py) --------------------------
param sasTokenExpiryMinutes int = 15
param menuCacheTtlHours int = 24
param menuMatchConfidenceThreshold string = '0.6'
param vectorSearchTopK int = 5
param placesTimeoutSeconds string = '8'
param menuFetchTimeoutSeconds string = '60'
param menuFetchMaxRetries int = 2

@description('Origins allowed to call the Function App - the Static Web App URL. The SWA Free tier has no linked backends, so the SPA calls this host cross-origin.')
param allowedCorsOrigins array

param tags object = {}

// Key Vault references. The VaultName form is version-independent, unlike SecretUri=,
// which would pin a specific secret version at template-compile time.
var sqlPasswordRef = '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${sqlPasswordSecretName})'
var googlePlacesRef = '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${googlePlacesSecretName})'
var contentSafetyRef = '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${contentSafetySecretName})'
var foundryApiKeyRef = '@Microsoft.KeyVault(VaultName=${keyVaultName};SecretName=${foundryApiKeySecretName})'

resource plan 'Microsoft.Web/serverfarms@2025-03-01' = {
  name: planName
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2025-03-01' = {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storageBlobEndpoint}${deploymentContainerName}'
          authentication: {
            // Requires Storage Blob Data Owner on the account for this app's identity -
            // granted in rbac.bicep. Without it the app cannot fetch its own package.
            type: 'SystemAssignedIdentity'
          }
        }
      }
      runtime: {
        name: 'python'
        version: pythonVersion
      }
      scaleAndConcurrency: {
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: instanceMemoryMB
        // alwaysReady is deliberately absent - setting it forfeits the free grant.
      }
    }
    siteConfig: {
      // Must be false on Flex Consumption.
      alwaysOn: false
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      http20Enabled: true
      cors: {
        allowedOrigins: allowedCorsOrigins
        supportCredentials: false
      }
    }
  }
}

// Declared as a separate child resource rather than inline in siteConfig so that a later
// `func azure functionapp publish` does not clobber the settings.
resource appSettings 'Microsoft.Web/sites/config@2025-03-01' = {
  parent: functionApp
  name: 'appsettings'
  properties: union(
    {
      // --- Platform ---
      AzureWebJobsStorage: storageConnectionString
      APPLICATIONINSIGHTS_CONNECTION_STRING: appInsightsConnectionString
      // Required because monitoring.bicep sets DisableLocalAuth on the App Insights
      // component; pairs with Monitoring Metrics Publisher in rbac.bicep.
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'Authorization=AAD'

      // --- Azure SQL (shared/config.py: sql_server / sql_database / sql_uid / sql_pwd) ---
      SQL_SERVER: sqlServerFqdn
      SQL_DATABASE: sqlDatabaseName
      SQL_UID: sqlAdminLogin
      SQL_PWD: sqlPasswordRef
      SQL_ODBC_DRIVER: sqlOdbcDriver

      // --- Storage names ---
      BLOB_CONTAINER_UPLOADS: uploadsContainerName
      QUEUE_NAME_JOBS: jobsQueueName
      SAS_TOKEN_EXPIRY_MINUTES: string(sasTokenExpiryMinutes)

      // --- Pipeline tunables ---
      MENU_CACHE_TTL_HOURS: string(menuCacheTtlHours)
      MENU_MATCH_CONFIDENCE_THRESHOLD: menuMatchConfidenceThreshold
      VECTOR_SEARCH_TOP_K: string(vectorSearchTopK)

      // --- Google Places ---
      GOOGLE_PLACES_API_KEY: googlePlacesRef
      PLACES_TIMEOUT_SECONDS: placesTimeoutSeconds

      // --- Foundry / Claude ---
      // MENU_FETCH_MODEL must be the DEPLOYMENT name, not a model id. shared/config.py
      // defaults it to 'claude-sonnet-5', which would 404 against Foundry.
      CLAUDE_BASE_URL: claudeBaseUrl
      MENU_FETCH_MODEL: claudeDeploymentName
      VISION_MODEL_DEPLOYMENT: claudeDeploymentName
      MENU_FETCH_TIMEOUT_SECONDS: menuFetchTimeoutSeconds
      MENU_FETCH_MAX_RETRIES: string(menuFetchMaxRetries)

      // --- Embeddings ---
      AZURE_OPENAI_ENDPOINT: azureOpenAiEndpoint
      EMBEDDING_DEPLOYMENT_NAME: embeddingDeploymentName

      // --- Content moderation ---
      CONTENT_SAFETY_ENDPOINT: contentSafetyEndpoint
      CONTENT_SAFETY_KEY: contentSafetyRef

      // --- Auth ---
      // STUB_AUTH_HEADER_NAME and STUB_DEFAULT_USER_OID are deliberately NOT set in prod.
      // shared/config.py has safe defaults, and shipping them would expose a live
      // auth-bypass header.
      ENTRAID_ENABLED: string(entraIdEnabled)
      ENTRA_TENANT_ID: entraTenantId
      // Deliberately ENTRA_API_CLIENT_ID, not ENTRA_CLIENT_ID. There are two client IDs in
      // this system and they are not interchangeable: the backend validates a token's
      // audience against the API registration's ID (this one), while the SPA authenticates
      // as the SPA registration and gets its ID via VITE_ENTRA_CLIENT_ID at build time.
      // Naming both "ENTRA_CLIENT_ID" invites wiring the wrong one, and the mistake would
      // stay silent until Phase 3 Part B implements validation.
      ENTRA_API_CLIENT_ID: entraApiClientId
      ENTRA_AUTHORITY_URL: entraAuthorityUrl
      ENTRA_JWKS_URI: entraJwksUri
    },
    // shared/config.py's anthropic_api_key() does os.environ["ANTHROPIC_API_KEY"] and
    // menu_extraction.py passes it to Anthropic(api_key=...). Until that moves to
    // AnthropicFoundry with a managed-identity token provider, the key must be present.
    useFoundryApiKey ? { ANTHROPIC_API_KEY: foundryApiKeyRef } : {}
  )
}

output functionAppId string = functionApp.id
output functionAppName string = functionApp.name
output functionAppHostname string = functionApp.properties.defaultHostName
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output functionAppPrincipalId string = functionApp.identity.principalId
