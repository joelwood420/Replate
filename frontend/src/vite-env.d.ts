/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_COGNITO_ENABLED: string;
  readonly VITE_COGNITO_AUTHORITY: string;
  readonly VITE_COGNITO_CLIENT_ID: string;
  readonly VITE_COGNITO_REDIRECT_URI: string;
  readonly VITE_COGNITO_SCOPE: string;
  readonly VITE_STUB_AUTH_HEADER_NAME: string;
  readonly VITE_STUB_DEFAULT_USER_OID: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
