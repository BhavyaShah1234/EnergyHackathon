import { useState, useCallback } from 'react'

export function useOptimize() {
  const [progress, setProgress] = useState([])
  const [optimal, setOptimal] = useState(null)
  const [status, setStatus] = useState('idle')

  const optimize = useCallback((bounds, config = {}) => {
    const {
      weights = [0.30, 0.35, 0.35],
      maxSites = 5,
      gasPriceMax = null,
      powerCostMax = null,
      acresMin = 0,
      marketFilter = [],
      minComposite = 0.0,
    } = config

    setProgress([]); setOptimal(null); setStatus('running')
    fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bounds,
        weights,
        max_sites: maxSites,
        gas_price_max: gasPriceMax,
        power_cost_max: powerCostMax,
        acres_min: acresMin,
        market_filter: marketFilter,
        min_composite: minComposite,
      }),
    }).then(res => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = '', event = null
      const read = () => reader.read().then(({ done, value }) => {
        if (done) { setStatus('done'); return }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.startsWith('event: ')) event = line.slice(7).trim()
          if (line.startsWith('data: ') && event) {
            const d = JSON.parse(line.slice(6).trim())
            if (event === 'progress') setProgress(p => [...p, d])
            if (event === 'optimal')  setOptimal(prev => (!prev || d.composite_score > prev.composite_score) ? d : prev)
            event = null
          }
        }
        read()
      })
      read()
    }).catch(() => setStatus('error'))
  }, [])

  const reset = useCallback(() => {
    setProgress([]); setOptimal(null); setStatus('idle')
  }, [])

  return { progress, optimal, status, optimize, reset }
}
