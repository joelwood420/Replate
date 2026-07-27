// Azure SQL logical server + free-offer database.
//
// The database holds every table in backend/db/schema.sql, including CulinaryEmbeddings
// with its native VECTOR(1536) column. activities/query_culinary_embeddings.py runs a
// brute-force VECTOR_DISTANCE scan against it - no DiskANN index, which is the
// tier-restricted / preview feature.
//
// VERIFY BEFORE BUILDING ANYTHING ELSE ON THIS: the vector data type is documented for
// "Azure SQL Database" with no service-tier qualifier and a 1998-dimension maximum, so the
// free offer should support it - but the entire embeddings design depends on it. Run this
// against the provisioned database before going further:
//
//   CREATE TABLE dbo.__vec_probe (v VECTOR(1536) NOT NULL);
//   DROP TABLE dbo.__vec_probe;
//
// Cost note (Global Rule 1): the free offer gives 100,000 vCore-seconds + 32 GB data +
// 32 GB backup per month, for up to 10 free databases per subscription. No fixed hourly
// cost. Two consequences worth stating plainly:
//
//   * freeLimitExhaustionBehavior 'AutoPause' (required by CLAUDE.md) means a runaway loop
//     takes the app OFFLINE until the next calendar month rather than billing you. That is
//     the intended trade, but it is an availability risk, not a pure win.
//   * Switching to 'BillForUsage' later is ONE-WAY - you cannot go back to AutoPause.
//
// Also note the free offer LOCKS ITS REGION per subscription: once a region is chosen for a
// free database it applies to all free databases in that subscription and cannot be
// changed. Hence sqlLocation is a separate parameter from the other regions.

@description('Azure region for the SQL server. NOTE: the free-offer region is locked per subscription once chosen.')
param location string

@description('Globally unique logical server name.')
param sqlServerName string

@description('Database name. Must match the SQL_DATABASE app setting.')
param sqlDatabaseName string

@description('SQL administrator login. Must match the SQL_UID app setting.')
param sqlAdminLogin string

@description('SQL administrator password. Supplied at deploy time, also persisted to Key Vault.')
@secure()
param sqlAdminPassword string

@description('Object ID of the Entra principal to set as SQL Entra admin - normally you, for tooling access.')
param entraAdminObjectId string = ''

@description('Display name of the Entra SQL admin principal.')
param entraAdminLogin string = ''

@description('Minutes of inactivity before the serverless database auto-pauses. Too short burns the free grant on cold-start resumes; too long burns it idling.')
param autoPauseDelayMinutes int = 60

param tags object = {}

var configureEntraAdmin = !empty(entraAdminObjectId) && !empty(entraAdminLogin)

resource sqlServer 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    version: '12.0'
    administrators: configureEntraAdmin ? {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: entraAdminLogin
      sid: entraAdminObjectId
      tenantId: subscription().tenantId
      // MUST stay false: shared/config.py connects with SQL auth (SQL_UID / SQL_PWD).
      // Flipping this to true locks the Function App out of the database.
      azureADOnlyAuthentication: false
    } : null
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  tags: tags
  sku: {
    // General Purpose serverless. The free offer caps at 4 vCores.
    name: 'GP_S_Gen5_2'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 2
  }
  properties: {
    // These two properties require apiVersion 2023-08-01 or later - older versions
    // silently lack them and you get a normal billed database.
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    autoPauseDelay: autoPauseDelayMinutes
    minCapacity: json('0.5')
    maxSizeBytes: 34359738368 // 32 GB
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    // AutoPause forces local-redundant backup anyway; stating it avoids a diff on redeploy.
    requestedBackupStorageRedundancy: 'Local'
    zoneRedundant: false
  }
}

// Lets Azure services - the Function App, and the deployment script container that applies
// schema.sql - reach the server. The 0.0.0.0 sentinel is the documented "allow Azure
// services" rule, not a literal address range.
resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-08-01' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

output sqlServerId string = sqlServer.id
output sqlServerName string = sqlServer.name
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = sqlDatabase.name
output firewallRuleId string = allowAzureServices.id
