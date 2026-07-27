// All role assignments in one place.
//
// This module must run LAST - every assignment needs the Function App's system-assigned
// principal ID, which only exists once the site resource has been created.
//
// Allow roughly five minutes for role propagation before the first request. In particular
// the Flex Consumption deployment-package fetch uses the app's managed identity, so a
// publish attempted immediately after deployment can fail with a permissions error that
// resolves itself on retry.

@description('System-assigned principal ID of the Function App.')
param functionAppPrincipalId string

@description('Name of the Key Vault to grant secret read access on.')
param keyVaultName string

@description('Name of the storage account to grant data-plane access on.')
param storageAccountName string

@description('Name of the Application Insights component to grant telemetry publishing on.')
param appInsightsName string

@description('Name of the Foundry account to grant model inference access on.')
param foundryAccountName string

@description('Name of the Content Safety account. Only used when grantContentSafetyAccess is true.')
param contentSafetyName string

@description('Grant Cognitive Services User on Content Safety. Only needed when calling it with managed identity rather than the key from Key Vault.')
param grantContentSafetyAccess bool = false

@description('Grant Storage Blob Delegator, needed only after shared/blob.py moves from account-key SAS to user-delegation SAS.')
param grantBlobDelegator bool = false

// Built-in role definition IDs.
var roles = {
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  storageBlobDelegator: 'db58b8e5-c6ad-4a2a-8342-4190687cbf4a'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' existing = {
  name: keyVaultName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  name: storageAccountName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' existing = {
  name: foundryAccountName
}

resource contentSafety 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' existing = {
  name: contentSafetyName
}

// Resolves the @Microsoft.KeyVault(...) app settings for SQL_PWD, GOOGLE_PLACES_API_KEY,
// CONTENT_SAFETY_KEY and (when key auth is in use) ANTHROPIC_API_KEY.
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, functionAppPrincipalId, roles.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Blob Data Owner is a hard requirement on Flex Consumption: the platform fetches the
// deployment package from the blob container using this identity.
resource blobDataOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, functionAppPrincipalId, roles.storageBlobDataOwner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Queue and Table access are not strictly required while AzureWebJobsStorage is a
// connection string, but they cost nothing and mean switching to identity-based
// connections later needs no new role assignment. Durable Functions uses all three.
resource queueDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, functionAppPrincipalId, roles.storageQueueDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource tableDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, functionAppPrincipalId, roles.storageTableDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageTableDataContributor)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource blobDelegator 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantBlobDelegator) {
  scope: storageAccount
  name: guid(storageAccount.id, functionAppPrincipalId, roles.storageBlobDelegator)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDelegator)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Required because monitoring.bicep sets DisableLocalAuth on the App Insights component,
// so telemetry must be published with an Entra token.
resource metricsPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: appInsights
  name: guid(appInsights.id, functionAppPrincipalId, roles.monitoringMetricsPublisher)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Lets the app call Claude and the embedding model with its managed identity. Granted
// unconditionally so the key-auth path can be switched off later without another deploy.
resource foundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, functionAppPrincipalId, roles.cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource contentSafetyUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantContentSafetyAccess) {
  scope: contentSafety
  name: guid(contentSafety.id, functionAppPrincipalId, roles.cognitiveServicesUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
    principalId: functionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}
