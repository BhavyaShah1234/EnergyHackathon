import { useState, useEffect, useCallback } from 'react'
import { SORTED_SITES, MARKET_SNAPSHOT } from '../data/sites'

// ─── Adapters: snake_case API → camelCase frontend ─────────────────────────

function adaptSite(raw) {
  return {
    id:              raw.id,
    name:            raw.name,
    shortName:       raw.name.split(' ').map(w => w[0]).join('').slice(0, 6),
    location:        raw.location,
    lat:             raw.lat,
    lng:             raw.lng,
    state:           raw.state,
    market:          raw.market,
    acres:           raw.acres,
    landCostPerAcre: raw.land_cost_per_acre,
    fiberKm:         raw.fiber_km,
    waterKm:         raw.water_km,
    pipelineKm:      raw.pipeline_km,
    gasHub:          raw.gas_hub,
    gasPrice:        raw.gas_price,
    lmpNode:         raw.lmp_node,
    lmp:             raw.lmp,
    estPowerCostMwh: raw.est_power_cost_mwh,
    totalLandCostM:  raw.total_land_cost_m,
    scores:          raw.scores,
    rank:            raw.rank,
  }
}

function adaptMarket(raw) {
  const waha  = raw.gas?.waha_hub  ?? 1.84
  const henry = raw.gas?.henry_hub ?? 3.41
  return {
    wahaHub:    { price: waha,  unit: '/MMBtu', change: 0.12,  pct: 7.0 },
    henryHub:   { price: henry, unit: '/MMBtu', change: -0.08, pct: -2.3 },
    spread:     { value: +(henry - waha).toFixed(2), label: 'Waha Discount', advantage: true },
    paloverdeL: { price: raw.lmp?.['PALOVRDE_ASR-APND']?.lmp_mwh ?? 38.50, unit: '/MWh', change: 2.10, pct: 5.8 },
    sp15Lmp:    { price: raw.lmp?.SP15?.lmp_mwh ?? 42.30, unit: '/MWh', change: 1.90, pct: 4.7 },
    azpsDemand: { value: raw.demand?.AZPS?.demand_mw ?? 8420, unit: 'MW', change: 1.2 },
  }
}

// ─── Hooks ─────────────────────────────────────────────────────────────────

/**
 * Returns ranked candidate sites.
 * Immediately serves static mock data, then upgrades to live API data if the
 * backend is reachable. `dataSource` lets the UI show 'LIVE' vs 'CACHED'.
 */
export function useSites() {
  const [sites, setSites] = useState(SORTED_SITES)
  const [dataSource, setDataSource] = useState('cached')

  const loadSites = useCallback(async (signal) => {
    const r = await fetch('/api/sites', { signal })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    if (Array.isArray(data) && data.length > 0) {
      setSites(data.map(adaptSite).sort((a, b) => b.scores.composite - a.scores.composite))
      setDataSource('live')
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadSites(controller.signal).catch(() => { /* backend not running — static data remains */ })
    return () => controller.abort()
  }, [loadSites])

  const refetchSites = useCallback(() => {
    const c = new AbortController()
    return loadSites(c.signal).catch(() => {})
  }, [loadSites])

  return { sites, dataSource, refetchSites }
}

/**
 * Returns the live market snapshot (gas prices, LMPs, BA demand).
 * Same fallback pattern as useSites.
 */
export function useMarket() {
  const [market, setMarket] = useState(MARKET_SNAPSHOT)
  const [dataSource, setDataSource] = useState('cached')

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/market', { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setMarket(adaptMarket(data))
        setDataSource('live')
      })
      .catch(() => { /* backend not running — static data remains */ })

    return () => controller.abort()
  }, [])

  return { market, dataSource }
}
