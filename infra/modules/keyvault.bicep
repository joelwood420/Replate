// Key Vault holding every secret the Function App reads (Global Rule 4: no secrets in
// code or Bicep params).
//
// Secrets arrive two ways:
//
//   SUPPLIED AT DEPLOY TIME as @secure() parameters, then persisted here:
//     sql-admin-password     - also used directly by sql.bicep
//     google-places-api-key  - externally obtained from Google Cloud console
//
//   COMPUTED AT DEPLOY TIME from other resources in this template:
//     content-safety-key     - from the Content Safety account's listKeys()
//     foundry-api-key        - only when useFoundryApiKey is true; prefer managed identity
//
// The secure params are passed on the command line (see infra/README.md), never written
// into main.bicepparam. Each secret is guarded with `if (!empty(...))`, so once seeded you
// can omit it on later deploys and the stored value is left untouched.
//
// A Key Vault reference to a secret that does not exist fails at APP RUNTIME, not deploy
// time - the app setting resolves to empty and shared/config.py raises KeyError inside a
// Durable activity. Confirm all four resolve before calling the deploy done.
//
// Cost note (Global Rule 1): Key Vault standard has NO free tier. Billed per 10k
// operations, negligible at this scale. No fixed hourly cost.

@description('Azure region for the vault.')
param location string

@description('Globally unique Key Vault name (3-24 chars).')
param keyVaultName string

@description('Azure SQL administrator password. Supplied at deploy time; persisted here for the Function App to read.')
@secure()
param sqlAdminPassword string = ''

@description('Google Places API key. Supplied at deploy time; persisted here for the Function App to read.')
@secure()
param googlePlacesApiKey string = ''

@description('Content Safety key, computed by content-safety.bicep.')
@secure()
param contentSafetyKey string = ''

@description('Foundry API key. Only set when authenticating to Foundry with a key rather than managed identity.')
@secure()
param foundryApiKey string = ''

@description('Store a Foundry API key. Leave false to use managed identity (preferred - zero secrets).')
param useFoundryApiKey bool = false

param tags object = {}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    // RBAC rather than access policies - role assignments live in rbac.bicep.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    // Deliberately NOT enabling purge protection: it is irreversible and makes
    // tear-down-and-redeploy during Phase 3 iteration painful.
    enabledForDeployment: false
    enabledForTemplateDeployment: false
    enabledForDiskEncryption: false
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource sqlPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = if (!empty(sqlAdminPassword)) {
  parent: keyVault
  name: 'sql-admin-password'
  properties: {
    value: sqlAdminPassword
    contentType: 'text/plain'
  }
}

resource googlePlacesSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = if (!empty(googlePlacesApiKey)) {
  parent: keyVault
  name: 'google-places-api-key'
  properties: {
    value: googlePlacesApiKey
    contentType: 'text/plain'
  }
}

resource contentSafetySecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = if (!empty(contentSafetyKey)) {
  parent: keyVault
  name: 'content-safety-key'
  properties: {
    value: contentSafetyKey
    contentType: 'text/plain'
  }
}

resource foundrySecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = if (useFoundryApiKey && !empty(foundryApiKey)) {
  parent: keyVault
  name: 'foundry-api-key'
  properties: {
    value: foundryApiKey
    contentType: 'text/plain'
  }
}

output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri

// Secret NAMES, exported so function-app.bicep builds its Key Vault references from one
// source of truth rather than repeating string literals. These are identifiers, not
// values - the secrets themselves never leave the vault.
#disable-next-line outputs-should-not-contain-secrets
output sqlPasswordSecretName string = 'sql-admin-password'
output googlePlacesSecretName string = 'google-places-api-key'
output contentSafetySecretName string = 'content-safety-key'
output foundryApiKeySecretName string = 'foundry-api-key'
