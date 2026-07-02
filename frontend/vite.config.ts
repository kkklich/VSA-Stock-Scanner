import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Allow the preview harness to assign a port via the PORT env variable.
    port: process.env.PORT ? parseInt(process.env.PORT) : 5173,
    // In development, proxy /api calls to the Python backend so the frontend
    // can call e.g. /api/stocks/ranking without dealing with CORS or hardcoded ports.
    proxy: {
      '/api': {
        target: 'http://localhost:5111',
        changeOrigin: true,
      },
    },
  },
})
