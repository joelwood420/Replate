import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

// Flat config (ESLint 9). Replaces the old tsc-only "lint" script with a real lint gate:
// type-aware-ish TS rules plus the react-hooks rules that catch stale/missing effect deps,
// which tsc cannot see. Kept close to Vite's react-ts template.
export default tseslint.config(
  {
    ignores: [
      'dist',
      'node_modules',
      'coverage',
      // Compiled config artifacts and the flat config itself are not linted.
      'vite.config.js',
      'vite.config.d.ts',
      'eslint.config.js',
    ],
  },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // Honour the codebase's existing `_name` convention for deliberately unused args.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // Test files run under Vitest: expose its globals so no-undef stays quiet, and relax
    // the react-refresh export rule that only matters for HMR of component modules.
    files: ['src/**/*.{test,spec}.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    languageOptions: {
      globals: {
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
        vi: 'readonly',
      },
    },
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
);
