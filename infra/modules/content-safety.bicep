// Azure AI Content Safety, for moderating uploaded photos before they enter the pipeline
// (CLAUDE.md Phase 3 step 6).
//
// WHY THIS IS A SEPARATE ACCOUNT FROM ai-foundry.bicep: an AIServices account does expose
// the content-safety endpoints, but AIServices is only offered at sku S0 - there is no F0.
// A dedicated kind:'ContentSafety' account can use F0, which is free and, importantly,
// REJECTS requests rather than billing once the monthly allowance is used. Under Global
// Rule 1 that is the right shape: overage is impossible by construction.
//
// Data-plane call:
//   POST {endpoint}/contentsafety/image:analyze?api-version=2024-09-01
// Feed it the read SAS URL that shared/blob.py already mints rather than piping image
// bytes back through the Function App.
//
// Cost note (Global Rule 1): F0 is free - 5,000 image analyses + 5,000 text records per
// month. On exhaustion requests are rejected; there is no overage rate. No fixed hourly
// cost. Note Azure typically permits only one F0 account per kind per subscription.

@description('Azure region. Content Safety F0 has its own supported-region list, separate from the Foundry and SQL regions.')
param location string

@description('Globally unique Content Safety account name. Also becomes the customSubDomainName, so it must be DNS-safe.')
param contentSafetyName string

@description('SKU. F0 is the free tier; S0 bills per transaction. Keep F0 unless the 5,000/month allowance is genuinely exceeded.')
@allowed([
  'F0'
  'S0'
])
param sku string = 'F0'

@description('Set true to require Entra auth and disable API keys entirely.')
param disableLocalAuth bool = false

param tags object = {}

resource contentSafety 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: contentSafetyName
  location: location
  tags: tags
  kind: 'ContentSafety'
  sku: {
    name: sku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: contentSafetyName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: disableLocalAuth
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

output contentSafetyId string = contentSafety.id
output contentSafetyName string = contentSafety.name
output contentSafetyEndpoint string = contentSafety.properties.endpoint

// Consumed by main.bicep and written into Key Vault. Never surfaced as a main.bicep output.
@secure()
output contentSafetyKey string = contentSafety.listKeys().key1
