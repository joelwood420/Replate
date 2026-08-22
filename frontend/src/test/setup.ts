import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Testing Library only auto-registers cleanup when Vitest globals are enabled. We import
// test APIs explicitly (globals stay off), so unmount and reset the DOM between tests here.
afterEach(() => {
  cleanup();
});
