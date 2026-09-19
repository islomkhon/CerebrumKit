import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// The dev proxy target comes from VITE_API_URL so the backend origin is set in
// .env only and is never written into the config. Without it there is no proxy.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    server: env.VITE_API_URL
      ? {
          proxy: {
            '/api': {
              target: env.VITE_API_URL,
              changeOrigin: true,
              rewrite: (path) => path.replace(/^\/api/, ''),
            },
          },
        }
      : {},
  }
})
