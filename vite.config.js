import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { collideApiDevProxy } from './vite-plugin-collide-api.js'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const fallbackApiPort = env.COLLIDE_API_PORT || '32587'

  return {
    plugins: [collideApiDevProxy(fallbackApiPort), react()],
    optimizeDeps: {
      include: ['leaflet', 'react-leaflet'],
    },
    server: {
      // /api is handled by collideApiDevProxy (dynamic port from .collide-api-port)
    },
    build: {
      chunkSizeWarningLimit: 600,
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom'],
            'vendor-charts': ['recharts'],
            'vendor-map': ['leaflet', 'react-leaflet'],
          },
        },
      },
    },
  }
})
