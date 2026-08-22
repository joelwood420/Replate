import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    // Pinned: without strictPort, Vite silently walks to 5174/5175 when 5173 is taken
    // by another project's dev server, and you end up looking at the wrong app.
    port: 5173,
    strictPort: true,
  },
  test: {
    // jsdom gives component/hook tests a DOM without a browser. Setup registers
    // jest-dom matchers and Testing Library cleanup (see src/test/setup.ts).
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    // CSS Modules are not processed; `styles.foo` resolves to undefined in tests,
    // which is harmless because assertions target text/roles, not class names.
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
