// Microsoft Foundry (Azure AI Foundry) account hosting both models the pipeline needs:
//
//   * Claude Haiku 4.5  - the vision guess (activities/vision_guess.py) and the menu
//                         extraction call (shared/menu_extraction.py)
//   * text-embedding-3-small - culinary technique vectors for CulinaryEmbeddings
//
// One AIServices account serves both: Anthropic-format and OpenAI-format deployments
// coexist under the same account, endpoint and identity. Content Safety is deliberately
// NOT here - see content-safety.bicep for why.
//
// TWO THINGS TO VERIFY BEFORE BUILDING PHASE 3 ON THIS:
//
//   1. The web_search server tool. shared/menu_extraction.py calls Claude with
//      `web_search_20260209`, per the 2026-07-23 decision in docs/decisions.md. Foundry's
//      published capability table lists only client-executed tools, and the web-search
//      documentation states Foundry requires a "Hosted on Anthropic" deployment - which is
//      what modelVersion '1' selects below ('2' is Hosted on Azure). Confirm with a real
//      call before assuming menu extraction works. If it does not, the menu-fetch strategy
//      needs revisiting and a new docs/decisions.md entry.
//
//   2. Subscription eligibility. Claude on Foundry bills through Azure Marketplace in
//      Claude Consumption Units. Free-trial, student and credit-only subscriptions get
//      0 RPM / 0 ITPM and cannot use Claude at all, and Marketplace charges are generally
//      not covered by Azure credits. Check with:
//        az cognitiveservices model list -l <region> --query "[?name=='claude-haiku-4-5']"
//
// Cost note (Global Rule 1): the account itself is free; models are pay-per-use with no
// free tier. GlobalStandard is consumption-based with NO fixed hourly cost - do not switch
// to provisioned throughput, which does carry one.

@description('Azure region. Claude models on Foundry are region-restricted - eastus2 and swedencentral host Haiku. Separate from the other region parameters on purpose.')
param location string

@description('Globally unique Foundry account name. Also becomes the customSubDomainName, so it must be DNS-safe.')
param foundryAccountName string

@description('Name of the Foundry project under the account.')
param foundryProjectName string

@description('Deployment name for the Claude model. This is what the app sends as the `model` parameter - NOT the model id. Wired to MENU_FETCH_MODEL and VISION_MODEL_DEPLOYMENT.')
param claudeDeploymentName string = 'claude-haiku-4-5'

@description('Claude model id to deploy.')
param claudeModelName string = 'claude-haiku-4-5'

@description('"1" = Hosted on Anthropic (required for the web_search server tool), "2" = Hosted on Azure.')
@allowed([
  '1'
  '2'
])
param claudeModelVersion string = '1'

@description('Claude deployment capacity, in thousands of tokens per minute.')
param claudeCapacity int = 25

@description('Deployment name for the embedding model. Wired to EMBEDDING_DEPLOYMENT_NAME.')
param embeddingDeploymentName string = 'text-embedding-3-small'

@description('Embedding model id. 1536 dimensions, matching CulinaryEmbeddings.Embedding VECTOR(1536).')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding deployment capacity, in thousands of tokens per minute.')
param embeddingCapacity int = 30

// The three modelProviderData fields below are used by the Cognitive Services resource
// provider to accept the Azure Marketplace offer for Anthropic Claude on your behalf,
// which is why no separate portal click-through is needed.
@description('Organization name, for the Anthropic Marketplace offer acceptance.')
param claudeOrganizationName string

@description('Two-letter country code, for the Anthropic Marketplace offer acceptance.')
@minLength(2)
@maxLength(2)
param claudeCountryCode string

@description('Industry, for the Anthropic Marketplace offer acceptance. Must be lowercase.')
@allowed([
  'technology'
  'finance'
  'healthcare'
  'education'
  'retail'
  'manufacturing'
  'government'
  'media'
  'other'
])
param claudeIndustry string = 'technology'

@description('Set true to require Entra auth and disable API keys entirely. Prefer true once managed-identity auth is verified working.')
param disableLocalAuth bool = false

param tags object = {}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: foundryAccountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    // AIServices only offers S0. There is no free tier for this account kind - which is
    // exactly why Content Safety lives in its own F0 account.
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    // Required for the https://<name>.services.ai.azure.com endpoint the SDKs expect.
    customSubDomainName: foundryAccountName
    // Required, or project creation fails with "Project can only be created under
    // AIServices Kind account".
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: disableLocalAuth
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-10-01-preview' = {
  parent: foundry
  name: foundryProjectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource claudeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = {
  parent: foundry
  name: claudeDeploymentName
  sku: {
    // Consumption-based. Provisioned throughput would introduce a fixed hourly cost -
    // see Global Rule 1.
    name: 'GlobalStandard'
    capacity: claudeCapacity
  }
  properties: {
    model: {
      format: 'Anthropic'
      name: claudeModelName
      version: claudeModelVersion
    }
    // modelProviderData is required for Anthropic models but is NOT part of the published
    // ARM/Bicep type schema, so Bicep flags it as an unexpected property. It is passed
    // through to the resource provider correctly. The suppression below is expected, not
    // a workaround for a mistake.
    #disable-next-line BCP037
    modelProviderData: {
      organizationName: claudeOrganizationName
      countryCode: claudeCountryCode
      industry: claudeIndustry
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
  dependsOn: [
    foundryProject
  ]
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = {
  parent: foundry
  name: embeddingDeploymentName
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: '1'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
  // Foundry serializes model deployments server-side and returns 409 on concurrent
  // creates. This dependsOn is load-bearing, not cosmetic.
  dependsOn: [
    claudeDeployment
  ]
}

output foundryAccountId string = foundry.id
output foundryAccountName string = foundry.name
output foundryPrincipalId string = foundry.identity.principalId

// The Anthropic SDK's AnthropicFoundry client takes this as its base URL.
output claudeBaseUrl string = 'https://${foundry.name}.services.ai.azure.com/anthropic'
// Azure OpenAI SDK endpoint for the embeddings call.
output azureOpenAiEndpoint string = 'https://${foundry.name}.services.ai.azure.com'

// Deployment NAMES, not model ids. shared/config.py currently defaults MENU_FETCH_MODEL to
// 'claude-sonnet-5', a first-party Anthropic model id - on Foundry the `model` parameter
// must be the deployment name or the call 404s.
output claudeDeploymentName string = claudeDeployment.name
output embeddingDeploymentName string = embeddingDeployment.name

// Consumed by main.bicep and written into Key Vault when key auth is in use. Never
// surfaced as a main.bicep output.
@secure()
output foundryApiKey string = foundry.listKeys().key1
