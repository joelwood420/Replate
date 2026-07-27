// Azure Static Web App hosting the built React SPA (frontend/dist).
//
// NOT repo-linked. repositoryUrl / branch / repositoryToken are deliberately omitted:
// wiring GitHub is Phase 4 work, and putting a GitHub PAT in a Bicep parameter would
// violate Global Rule 4. Deploy the build with `swa deploy` using the deployment token,
// or add the official SWA GitHub Action in Phase 4.
//
// IMPORTANT - the VITE_* variables are BUILD-TIME, not app settings. `npm run build` bakes
// VITE_API_BASE_URL, VITE_ENTRAID_ENABLED, VITE_ENTRA_CLIENT_ID and
// VITE_ENTRA_AUTHORITY_URL into frontend/dist. They cannot be set on the Static Web App
// afterwards. main.bicep outputs the values that feed them; the build step must consume
// those outputs. Forgetting this is the most likely way to ship a frontend still pointing
// at http://localhost:7071/api.
//
// The Free tier has NO linked backends (that needs Standard), so the SPA calls the
// Function App directly on its own hostname. That makes the Function App's CORS rule
// load-bearing rather than optional.
//
// Cost note (Global Rule 1): Free tier - 100 GB bandwidth/month, 250 MB per environment,
// 500 MB total, 2 custom domains, 10 free Static Web Apps per subscription. On exhaustion
// the site stops being served; there is no overage bill. No fixed hourly cost.

@description('Azure region for the Static Web App.')
param location string

@description('Name of the Static Web App.')
param staticWebAppName string

@description('SKU. Free has no linked-backend support, which is fine here - the SPA calls the Function App directly.')
@allowed([
  'Free'
  'Standard'
])
param sku string = 'Free'

param tags object = {}

resource staticWebApp 'Microsoft.Web/staticSites@2025-03-01' = {
  name: staticWebAppName
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    // Not linked to a source control provider - see the header comment.
    provider: 'None'
    // The Free tier allows 3 preview environments; disabling avoids surprise deployments
    // and keeps the 500 MB total storage allowance for production.
    stagingEnvironmentPolicy: 'Disabled'
    allowConfigFileUpdates: true
    enterpriseGradeCdnStatus: 'Disabled'
  }
}

output staticWebAppId string = staticWebApp.id
output staticWebAppName string = staticWebApp.name
output staticWebAppHostname string = staticWebApp.properties.defaultHostname
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
