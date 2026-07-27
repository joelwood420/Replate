// Log Analytics workspace + Application Insights.
//
// Not in CLAUDE.md's Phase 3 resource list, but backend/host.json already configures
// Application Insights sampling, so the Function App expects a connection string.
//
// Cost note (Global Rule 1): Log Analytics has a free ingestion grant per billing
// account, then bills per GB. Ingestion is the sleeper cost in this architecture - a
// retry storm in the Durable orchestrator can quietly ingest gigabytes. dailyQuotaGb
// caps that; ingestion stops for the rest of the UTC day rather than billing on.

@description('Azure region for the workspace and Application Insights component.')
param location string

@description('Name of the Log Analytics workspace.')
param workspaceName string

@description('Name of the Application Insights component.')
param appInsightsName string

@description('Daily ingestion cap in GB. Ingestion stops for the rest of the day once hit.')
param dailyQuotaGb int = 1

@description('How long to retain logs, in days.')
param retentionInDays int = 30

param tags object = {}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    workspaceCapping: {
      dailyQuotaGb: dailyQuotaGb
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    // Forces Entra-authenticated telemetry ingestion. Requires the Function App's
    // managed identity to hold Monitoring Metrics Publisher (granted in rbac.bicep)
    // and the APPLICATIONINSIGHTS_AUTHENTICATION_STRING app setting.
    DisableLocalAuth: true
    IngestionMode: 'LogAnalytics'
  }
}

output workspaceId string = workspace.id
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
