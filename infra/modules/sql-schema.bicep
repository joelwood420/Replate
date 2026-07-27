// Applies backend/db/schema.sql to the Azure SQL database.
//
// CLAUDE.md Phase 3 step 3 requires this to happen via a deployment script step or an
// idempotent migration tool - explicitly NOT through the Azure Portal - so that local and
// prod schemas never drift.
//
// The schema is pulled in with loadTextContent(), so there is no copy of schema.sql inside
// infra/ and backend/db/schema.sql stays the single source of truth. The file is a few KB,
// far inside the 4 MB template limit.
//
// Uses the go-sqlcmd static binary rather than PowerShell's SqlServer module or pyodbc:
// one self-contained download, no ODBC driver to install, no PSGallery dependency at
// deploy time. go-sqlcmd understands the GO batch separators in schema.sql.
//
// schema.sql MUST be idempotent (every CREATE TABLE is guarded by an
// IF OBJECT_ID(...) IS NULL check) because forceUpdateTag defaults to a fresh timestamp,
// which makes this script re-run on every deployment.
//
// Cost note (Global Rule 1): deploymentScripts provisions a transient Azure Container
// Instance and storage account behind the scenes. No free tier, but it is billed in
// seconds and cleaned up on success. No fixed hourly cost.

@description('Azure region for the deployment script resources.')
param location string

@description('Name for the user-assigned managed identity the script runs as.')
param identityName string

@description('Name for the deployment script resource.')
param deploymentScriptName string

@description('Fully qualified domain name of the SQL server.')
param sqlServerFqdn string

@description('Database to apply the schema to.')
param sqlDatabaseName string

@description('SQL administrator login.')
param sqlAdminLogin string

@description('SQL administrator password.')
@secure()
param sqlAdminPassword string

@description('Changing this forces the script to re-run. Defaults to a fresh timestamp so the schema is reconciled on every deploy.')
param forceUpdateTag string = utcNow()

param tags object = {}

// The script authenticates to SQL with the admin login, so this identity needs no Azure
// data-plane roles. It exists because deploymentScripts requires an identity to run as.
resource scriptIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

resource applySchema 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: deploymentScriptName
  location: location
  tags: tags
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${scriptIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.70.0'
    retentionInterval: 'PT1H'
    cleanupPreference: 'OnSuccess'
    timeout: 'PT30M'
    forceUpdateTag: forceUpdateTag
    environmentVariables: [
      {
        name: 'SQL_SERVER_FQDN'
        value: sqlServerFqdn
      }
      {
        name: 'SQL_DB'
        value: sqlDatabaseName
      }
      {
        name: 'SQL_UID'
        value: sqlAdminLogin
      }
      {
        name: 'SQL_PWD'
        secureValue: sqlAdminPassword
      }
      {
        name: 'SCHEMA_SQL'
        value: loadTextContent('../../backend/db/schema.sql')
      }
    ]
    scriptContent: '''
      set -euo pipefail

      echo "Downloading go-sqlcmd..."
      curl -sSL -o sqlcmd.tar.bz2 \
        https://github.com/microsoft/go-sqlcmd/releases/latest/download/sqlcmd-linux-amd64.tar.bz2
      tar -xjf sqlcmd.tar.bz2
      chmod +x sqlcmd

      printf '%s' "$SCHEMA_SQL" > schema.sql
      echo "Schema is $(wc -c < schema.sql) bytes."

      # A serverless database that has auto-paused takes roughly a minute to resume, and
      # the first connection attempt fails fast rather than waiting. Retry through it.
      attempt=1
      max_attempts=10
      until ./sqlcmd -S "$SQL_SERVER_FQDN" -d "$SQL_DB" -U "$SQL_UID" -P "$SQL_PWD" \
              -Q "SELECT 1" -b -l 60 > /dev/null 2>&1; do
        if [ "$attempt" -ge "$max_attempts" ]; then
          echo "Database did not become reachable after $max_attempts attempts." >&2
          exit 1
        fi
        echo "Database not reachable yet (attempt $attempt/$max_attempts); waiting 30s..."
        attempt=$((attempt + 1))
        sleep 30
      done

      echo "Applying schema..."
      ./sqlcmd -S "$SQL_SERVER_FQDN" -d "$SQL_DB" -U "$SQL_UID" -P "$SQL_PWD" \
        -i schema.sql -b -l 60

      echo "Verifying expected tables exist..."
      ./sqlcmd -S "$SQL_SERVER_FQDN" -d "$SQL_DB" -U "$SQL_UID" -P "$SQL_PWD" -b -l 60 -Q "
        SET NOCOUNT ON;
        DECLARE @missing NVARCHAR(MAX) = (
          SELECT STRING_AGG(t.name, ', ')
          FROM (VALUES ('Users'),('Restaurants'),('MenuItems'),('Jobs'),
                       ('JobRestaurantCandidates'),('JobResults'),('DishElements'),
                       ('ElementIngredients'),('ElementSteps'),('CulinaryEmbeddings')) AS t(name)
          WHERE OBJECT_ID(N'dbo.' + t.name, N'U') IS NULL
        );
        IF @missing IS NOT NULL
        BEGIN
          RAISERROR('Missing tables after schema apply: %s', 16, 1, @missing);
        END
        ELSE
          PRINT 'All 10 tables present.';
      "

      echo "Schema applied successfully."
    '''
  }
}

output scriptIdentityId string = scriptIdentity.id
output scriptIdentityPrincipalId string = scriptIdentity.properties.principalId
