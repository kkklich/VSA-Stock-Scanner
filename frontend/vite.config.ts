import { defineConfig } from 'vite'
import type { ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Backend target for the dev proxy. Use 127.0.0.1 (not "localhost"): on Windows
// Node resolves "localhost" to IPv6 ::1 first, but Uvicorn binds IPv4 by
// default, which produces "ECONNREFUSED" proxy errors. Override with
// VITE_API_PROXY when the backend runs elsewhere.
const API_TARGET = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:5111'

const apiProxy: ProxyOptions = {
  target: API_TARGET,
  changeOrigin: true,
  // Fail fast instead of leaving requests pending: `timeout` covers the
  // incoming client socket, `proxyTimeout` covers a slow/hung backend.
  timeout: 60_000,
  proxyTimeout: 60_000,
  configure(proxy) {
    // When the backend is down, return a clean 503 (JSON) instead of letting
    // the request hang and dumping an unhandled AggregateError to the console.
    proxy.on('error', (err, _req, res) => {
      const socket = res as unknown as {
        writableEnded?: boolean
        headersSent?: boolean
        writeHead?: (code: number, headers: Record<string, string>) => void
        end?: (chunk: string) => void
      }
      // Only the ServerResponse branch can send a body (not raw sockets).
      if (
        typeof socket.writeHead === 'function' &&
        typeof socket.end === 'function' &&
        !socket.headersSent &&
        !socket.writableEnded
      ) {
        socket.writeHead(503, { 'Content-Type': 'application/json' })
        socket.end(
          JSON.stringify({
            detail:
              'Backend API is not reachable. Start it with run-backend-python.bat (port 5111).',
          }),
        )
      }
      // Keep a single concise line in the dev console instead of a stack trace.
      console.warn(`[api proxy] backend unreachable at ${API_TARGET}: ${err.message}`)
    })
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Allow the preview harness to assign a port via the PORT env variable.
    port: process.env.PORT ? parseInt(process.env.PORT) : 5173,
    // In development, proxy /api calls to the Python backend so the frontend
    // can call e.g. /api/stocks/ranking without dealing with CORS or hardcoded ports.
    proxy: {
      '/api': apiProxy,
    },
  },
})
