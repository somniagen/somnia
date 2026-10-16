import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { fileURLToPath } from 'node:url'

const backend = process.env.SOMNIA_BACKEND ?? 'http://127.0.0.1:7865'

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      $lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
      $features: fileURLToPath(new URL('./src/features', import.meta.url)),
    },
  },
  server: {
    host: true,
    proxy: {
      '/api': backend,
      '/outputs': backend,
      '/files': backend,
      '/ws': { target: backend.replace('http', 'ws'), ws: true },
    },
  },
})
