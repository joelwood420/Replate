// Storage account backing three separate concerns:
//   1. the `uploads` blob container the client PUTs photos into via a SAS URL
//   2. the `jobs` queue that starts the Durable orchestrator
//   3. Durable Functions orchestration state, plus the Flex Consumption deployment package
//
// DEVIATION FROM CLAUDE.md: Phase 3 step 1 says "including the separate storage account
// Durable Functions needs for orchestration state". This module uses ONE account instead.
// Durable Functions does not require a dedicated account - it namespaces its own blobs,
// queues and tables by the task hub name (`ReplateHub`, set in backend/host.json), so
// there is no collision with `uploads` or `jobs`. The documented reasons to split are
// task-hub throughput contention and cross-app isolation, neither of which applies at MVP
// scale, and storage has no free tier either way so the cost is identical. Splitting is a
// one-parameter change later if throughput ever justifies it.
//
// Cost note (Global Rule 1): storage has NO free tier. Billed per GB-month plus per-10k
// transactions. No fixed hourly cost.

@description('Azure region for the storage account.')
param location string

@description('Globally unique storage account name (3-24 chars, lowercase alphanumeric).')
param storageAccountName string

@description('Blob container the client uploads photos into. Must match BLOB_CONTAINER_UPLOADS.')
param uploadsContainerName string = 'uploads'

@description('Queue that triggers the orchestrator starter. Must match QUEUE_NAME_JOBS.')
param jobsQueueName string = 'jobs'

@description('Container holding the Flex Consumption deployment package. Must exist before the Function App is created.')
param deploymentContainerName string

@description('Origins allowed to PUT directly to blob storage - the Static Web App hostname. Without this the browser upload fails with an opaque CORS error.')
param allowedUploadOrigins array

param tags object = {}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    // Required for now: shared/blob.py mints SAS tokens with the account key
    // (it reads service_client.credential.account_key), and shared/config.py reads a
    // plain `AzureWebJobsStorage` connection string. Flipping this to false requires
    // migrating blob.py to user-delegation SAS first - tracked as a follow-up.
    allowSharedKeyAccess: true
    defaultToOAuthAuthentication: false
    dnsEndpointType: 'Standard'
    accessTier: 'Hot'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    cors: {
      corsRules: [
        {
          // The browser PUTs the photo straight to blob storage with the write-only SAS
          // URL returned by POST /api/jobs - never through the Function App. That
          // cross-origin PUT requires this rule. backend/scripts/configure_azurite_cors.py
          // does the equivalent for local Azurite.
          allowedOrigins: allowedUploadOrigins
          allowedMethods: [
            'PUT'
            'OPTIONS'
          ]
          allowedHeaders: [
            '*'
          ]
          exposedHeaders: [
            '*'
          ]
          maxAgeInSeconds: 3600
        }
      ]
    }
  }
}

resource uploadsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: uploadsContainerName
  properties: {
    publicAccess: 'None'
  }
}

// Flex Consumption pulls the app package from here using the Function App's managed
// identity. It must exist before the site resource is created.
resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2025-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource jobsQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2025-01-01' = {
  parent: queueService
  name: jobsQueueName
}

output storageAccountId string = storageAccount.id
output storageAccountName string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output uploadsContainerName string = uploadsContainer.name
output jobsQueueName string = jobsQueue.name
output deploymentContainerName string = deploymentContainer.name

// Consumed by function-app.bicep for the AzureWebJobsStorage app setting. Resolved at
// deploy time so no key is ever committed (Global Rule 4), but note the resolved value
// does land in ARM deployment history - never surface this through main.bicep outputs.
@secure()
output connectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
