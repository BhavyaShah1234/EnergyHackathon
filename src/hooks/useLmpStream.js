import { useState, useEffect } from 'react'

const FALLBACK = { HB_WEST: 42.0, HB_NORTH: 40.0, HB_SOUTH: 43.0 }

export function useLmpStream() {
  const [lmp, setLmp] = useState(FALLBACK)

  useEffect(() => {
    const enableWsInProd = import.meta.env.VITE_ENABLE_LMP_WS === 'true'
    const shouldUseWs = !import.meta.env.PROD || enableWsInProd
    if (!shouldUseWs) return

    let ws
    const connect = () => {
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${protocol}://${location.host}/api/lmp/stream`

      try {
        ws = new WebSocket(url)
      } catch {
        // Browser may block socket setup in some environments; keep fallback values.
        return
      }

      ws.onmessage = e => setLmp(JSON.parse(e.data))
      ws.onerror   = () => ws?.close()
      ws.onclose   = () => setTimeout(connect, 5000)
    }
    connect()
    return () => ws?.close()
  }, [])

  return lmp
}
