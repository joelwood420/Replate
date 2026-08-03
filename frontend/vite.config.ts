import { defineConfig } from 'vite';
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
});
