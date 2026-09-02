import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Vitest configuration for the frontend component/unit tests. Kept separate
// from vite.config.ts (which carries the dev-server proxy) so the test run has a
// minimal, jsdom-based environment. The React plugin handles the JSX transform.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    restoreMocks: true,
  },
})
