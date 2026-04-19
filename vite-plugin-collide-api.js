/**
 * Dev-only: forwards /api/* to the FastAPI process. Reads `.collide-api-port` on every
 * request (written by `scripts/run_api.py`) so the UI tracks auto-picked ports without
 * restarting Vite. Falls back to COLLIDE_API_PORT from .env then 32587.
 */
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'

const PORT_FILE = '.collide-api-port'

export function collideApiDevProxy(fallbackPort) {
  return {
    name: 'collide-api-dev-proxy',
    enforce: 'pre',
    configureServer(server) {
      const root = server.config.root || process.cwd()
      const portFile = path.join(root, PORT_FILE)

      server.middlewares.use((req, res, next) => {
        const url = req.url || ''
        if (!url.startsWith('/api')) return next()

        let port = fallbackPort
        try {
          const t = fs.readFileSync(portFile, 'utf8').trim()
          if (/^\d+$/.test(t)) port = t
        } catch {
          /* no file yet */
        }

        const incoming = new URL(url, 'http://127.0.0.1')
        const opts = {
          hostname: '127.0.0.1',
          port: Number(port),
          path: incoming.pathname + incoming.search,
          method: req.method,
          headers: { ...req.headers, host: `127.0.0.1:${port}` },
        }

        const proxyReq = http.request(opts, proxyRes => {
          res.writeHead(proxyRes.statusCode || 502, proxyRes.headers)
          proxyRes.pipe(res)
        })
        proxyReq.on('error', () => {
          res.statusCode = 502
          res.setHeader('Content-Type', 'application/json')
          res.end(
            JSON.stringify({
              error: 'api_unreachable',
              message: `No API on 127.0.0.1:${port}. Run npm run dev:api first.`,
            })
          )
        })
        req.pipe(proxyReq)
      })
    },
  }
}
