import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// The dev proxy target comes from VITE_API_URL so the backend origin is set in
// .env only and is never written into the config. Without it there is no proxy.
//
// VITE_ALLOWED_HOSTS is for running the dev server somewhere other than
// localhost. Vite answers a request for a Host it has not been told about with
// 403, and a Codespace is reached through a hostname that does not exist when
// this file is written, so it cannot be hardcoded here. It is a comma-separated
// list of Vite host patterns, e.g. `.app.github.dev`. Unset, the default
// applies - only localhost and bare IP addresses - which is what a local
// checkout wants and is how this file behaved before the setting existed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedHosts = (env.VITE_ALLOWED_HOSTS ?? '')
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean)

  return {
    plugins: [vue()],
    server: {
      ...(env.VITE_API_URL
        ? {
            proxy: {
              '/api': {
                target: env.VITE_API_URL,
                changeOrigin: true,
                rewrite: (path: string) => path.replace(/^\/api/, ''),
              },
            },
          }
        : {}),
      ...(allowedHosts.length ? { allowedHosts } : {}),
    },
  }
})
