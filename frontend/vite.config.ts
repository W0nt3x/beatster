import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Unique per build. Baked into the bundle as __BUILD_ID__ and written to
// dist/version.json — the running client polls version.json and reloads when
// the deployed build differs (so users never have to hard-refresh).
const buildId = Date.now().toString(36)

export default defineConfig({
  define: { __BUILD_ID__: JSON.stringify(buildId) },
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'write-version-json',
      apply: 'build',
      closeBundle() {
        writeFileSync(
          resolve(process.cwd(), 'dist', 'version.json'),
          JSON.stringify({ v: buildId }),
        )
      },
    },
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        rewriteWsOrigin: true,
      },
    },
  },
})
