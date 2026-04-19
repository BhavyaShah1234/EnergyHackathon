import { useState, useCallback } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { GAS_PRICE_HISTORY } from '../data/sites'
import { useSites, useMarket } from '../hooks/useApi'

// ─── Sub-components ────────────────────────────────────────────────────────

function DataSourceBadge({ source }) {
  const live = source === 'live'
  return (
    <div
      className={`db-live-prices-badge${live ? ' db-live-prices-badge--streaming' : ''}`}
      role="status"
      aria-label={live ? 'Prices from live API' : 'Demo price snapshot'}
    >
      <span className="db-live-prices-badge__globe" aria-hidden>🌍</span>
      <span className="db-live-prices-badge__label">LIVE PRICES</span>
      {live && <span className="db-live-prices-badge__dot" />}
    </div>
  )
}

function ScoreBar({ value, color }) {
  return (
    <div className="db-score-bar-track">
      <div className="db-score-bar-fill" style={{ width: `${value * 100}%`, background: color }} />
    </div>
  )
}

function ScoreBadge({ value }) {
  const pct = Math.round(value * 100)
  const cls = value >= 0.80 ? 'db-badge--green' : value >= 0.70 ? 'db-badge--yellow' : 'db-badge--red'
  return <span className={`db-badge ${cls}`}>{pct}</span>
}

function KpiCard({ label, value, unit, change, pct, accent }) {
  const up = change >= 0
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color: `var(--${accent})` }}>
        {value}<span className="kpi-unit">{unit}</span>
      </div>
      {change !== undefined && (
        <div className={`kpi-change ${up ? 'kpi-change--up' : 'kpi-change--down'}`}>
          {up ? '▲' : '▼'} {Math.abs(pct).toFixed(1)}% today
        </div>
      )}
    </div>
  )
}

const TOOLTIP_STYLE = {
  background: '#141210',
  border: '1px solid #2A2318',
  fontFamily: 'IBM Plex Mono',
  fontSize: 11,
  borderRadius: 8,
}

const AXIS_TICK = { fill: '#7A6E5E', fontSize: 10, fontFamily: 'IBM Plex Mono' }

function scoreColor(v) {
  if (v >= 0.82) return '#3A8A65'
  if (v >= 0.76) return '#E85D04'
  return '#0D9488'
}

// ─── Pipeline Trigger ──────────────────────────────────────────────────────

function PipelineTrigger() {
  const [status, setStatus] = useState('idle')  // idle | running | done | error
  const [lastRun, setLastRun] = useState(null)

  const trigger = useCallback(() => {
    setStatus('running')
    fetch('/api/pipeline/run', { method: 'POST' })
      .then(r => r.json())
      .then(() => {
        setStatus('done')
        setLastRun(new Date().toLocaleTimeString())
        setTimeout(() => setStatus('idle'), 3000)
      })
      .catch(() => {
        setStatus('error')
        setTimeout(() => setStatus('idle'), 4000)
      })
  }, [])

  return (
    <div className="pipeline-trigger">
      <button
        className={`pipeline-btn pipeline-btn--${status}`}
        onClick={trigger}
        disabled={status === 'running'}
      >
        {status === 'running' ? '⟳ Refreshing…' : '↺ Refresh Data'}
      </button>
      {lastRun && status !== 'error' && (
        <span className="pipeline-last-run">Updated {lastRun}</span>
      )}
      {status === 'error' && (
        <span className="pipeline-error">Pipeline failed — using cached data</span>
      )}
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────

export default function Dashboard() {
  const { sites, dataSource: sitesSource } = useSites()
  const { market: snap, dataSource: marketSource } = useMarket()

  const isLive    = sitesSource === 'live' || marketSource === 'live'
  const topSite   = sites[0]

  const chartSites = sites.map(s => ({
    name:      s.shortName,
    score:     Math.round(s.scores.composite * 100),
    composite: s.scores.composite,
  }))

  const avgGasPrice    = (sites.reduce((acc, s) => acc + s.gasPrice, 0) / sites.length).toFixed(2)
  const avgPowerCost   = (sites.reduce((acc, s) => acc + s.estPowerCostMwh, 0) / sites.length).toFixed(1)
  const avgAcres       = Math.round(sites.reduce((acc, s) => acc + s.acres, 0) / sites.length)
  const avgLandCost    = Math.round(sites.reduce((acc, s) => acc + s.landCostPerAcre, 0) / sites.length)
  const ercotCount     = sites.filter(s => s.market === 'ERCOT').length

  return (
    <section id="dashboard">
      <div className="section-inner">

        <PipelineTrigger />

        {/* Header */}
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--teal reveal">Intelligence Dashboard</span>
          <h2 className="section-title section-title--light reveal">
            Live Market Data &amp;<br />Site Rankings.
          </h2>
          <p className="section-sub section-sub--light reveal">
            Natural gas pricing, CAISO LMPs, and composite site scores updated continuously
            across all candidate parcels in TX, NM, and AZ.
          </p>
          <div className="db-header-meta reveal">
            <DataSourceBadge source={isLive ? 'live' : 'cached'} />
            <span className="db-header-note">
              {isLive
                ? 'Streaming from live EIA + CAISO feeds'
                : 'Demo snapshot on this page · run npm run dev:api in another terminal for API-backed live feeds'}
            </span>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="kpi-row reveal">
          <KpiCard
            label="Waha Hub"
            value={snap.wahaHub.price.toFixed(2)}
            unit="/MMBtu"
            change={snap.wahaHub.change}
            pct={snap.wahaHub.pct}
            accent="orange-light"
          />
          <KpiCard
            label="Henry Hub"
            value={snap.henryHub.price.toFixed(2)}
            unit="/MMBtu"
            change={snap.henryHub.change}
            pct={snap.henryHub.pct}
            accent="teal-light"
          />
          <div className="kpi-card kpi-card--spread">
            <div className="kpi-label">Waha Discount vs Henry</div>
            <div className="kpi-value" style={{ color: '#22C55E' }}>
              ${snap.spread.value}<span className="kpi-unit">/MMBtu saved</span>
            </div>
            <div className="kpi-change kpi-change--up">▲ private generation advantage</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Top Site Score</div>
            <div className="kpi-value" style={{ color: '#3A8A65' }}>
              {topSite ? Math.round(topSite.scores.composite * 100) : '—'}
              <span className="kpi-unit">/ 100</span>
            </div>
            <div className="kpi-change kpi-change--up">
              {topSite ? `▲ ${topSite.name} · ${topSite.location}` : '—'}
            </div>
          </div>
        </div>

        {/* Charts */}
        <div className="db-charts-row reveal">
          <div className="db-chart-panel">
            <div className="db-chart-header">
              <span className="db-chart-title">Gas Price Trend · 30 Days</span>
              <div className="db-chart-legend">
                <span className="db-legend-dot" style={{ background: 'var(--orange-light)' }} />Waha Hub
                <span className="db-legend-dot" style={{ background: 'var(--teal-light)', marginLeft: 16 }} />Henry Hub
              </div>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={GAS_PRICE_HISTORY} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradWaha" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#E85D04" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#E85D04" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradHenry" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#14B8A6" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#14B8A6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A2318" />
                <XAxis dataKey="date" tick={AXIS_TICK} interval={6} />
                <YAxis tick={AXIS_TICK} tickFormatter={v => `$${v}`} domain={[1.4, 3.7]} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(v, name) => [`$${v}/MMBtu`, name === 'waha' ? 'Waha Hub' : 'Henry Hub']}
                  labelStyle={{ color: '#F4EFE4', marginBottom: 4 }}
                />
                <Area type="monotone" dataKey="henry" stroke="#14B8A6" fill="url(#gradHenry)" strokeWidth={2}   dot={false} />
                <Area type="monotone" dataKey="waha"  stroke="#E85D04" fill="url(#gradWaha)"  strokeWidth={2.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="db-chart-panel">
            <div className="db-chart-header">
              <span className="db-chart-title">Composite Site Scores</span>
              <span className="db-chart-sub">100 = perfect deployability</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartSites} layout="vertical" margin={{ top: 4, right: 32, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A2318" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={AXIS_TICK} />
                <YAxis dataKey="name" type="category" tick={AXIS_TICK} width={52} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={v => [`${v} / 100`, 'Composite Score']}
                  labelStyle={{ color: '#F4EFE4' }}
                />
                <ReferenceLine x={80} stroke="#3A8A65" strokeDasharray="4 3" strokeOpacity={0.6} />
                <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                  {chartSites.map(s => (
                    <Cell key={s.name} fill={scoreColor(s.composite)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Site Ranking Table */}
        <div className="db-table-wrap reveal">
          <div className="db-table-header">
            <span className="db-chart-title">Candidate Site Rankings</span>
            <div className="db-table-legend">
              <span className="db-legend-dot" style={{ background: '#3A8A65' }} /> Sub-A Land
              <span className="db-legend-dot" style={{ background: '#E85D04', marginLeft: 16 }} /> Sub-B Gas
              <span className="db-legend-dot" style={{ background: '#14B8A6', marginLeft: 16 }} /> Sub-C Power
            </div>
          </div>
          <table className="db-table">
            <thead>
              <tr>
                <th>#</th><th>Site</th><th>State</th><th>Composite</th>
                <th>Sub-A Land</th><th>Sub-B Gas</th><th>Sub-C Power</th>
                <th>Gas /MMBtu</th><th>Est. /MWh</th><th>Acres</th><th>Land $M</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((site, i) => (
                <tr key={site.id}>
                  <td className="db-rank">{i + 1}</td>
                  <td>
                    <div className="db-site-name">{site.name}</div>
                    <div className="db-site-loc">{site.location}</div>
                  </td>
                  <td>
                    <span className={`db-state-badge db-state-badge--${site.state.toLowerCase()}`}>
                      {site.state}
                    </span>
                  </td>
                  <td>
                    <div className="db-composite-cell">
                      <ScoreBadge value={site.scores.composite} />
                      <ScoreBar value={site.scores.composite} color={scoreColor(site.scores.composite)} />
                    </div>
                  </td>
                  <td>
                    <div className="db-sub-cell">
                      <span className="db-sub-num">{Math.round(site.scores.subA * 100)}</span>
                      <ScoreBar value={site.scores.subA} color="#3A8A65" />
                    </div>
                  </td>
                  <td>
                    <div className="db-sub-cell">
                      <span className="db-sub-num">{Math.round(site.scores.subB * 100)}</span>
                      <ScoreBar value={site.scores.subB} color="#E85D04" />
                    </div>
                  </td>
                  <td>
                    <div className="db-sub-cell">
                      <span className="db-sub-num">{Math.round(site.scores.subC * 100)}</span>
                      <ScoreBar value={site.scores.subC} color="#14B8A6" />
                    </div>
                  </td>
                  <td className="db-mono">${site.gasPrice.toFixed(2)}</td>
                  <td className="db-mono db-highlight">${site.estPowerCostMwh.toFixed(2)}</td>
                  <td className="db-mono">{site.acres.toLocaleString()}</td>
                  <td className="db-mono">${site.totalLandCostM.toFixed(2)}M</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Land & Market Efficiency Strip */}
        <div className="db-efficiency-row reveal">
          <div className="db-eff-card">
            <div className="db-eff-num" style={{ color: 'var(--orange-light)' }}>${avgGasPrice}</div>
            <div className="db-eff-label">Avg Gas Price · All Sites</div>
          </div>
          <div className="db-eff-card">
            <div className="db-eff-num" style={{ color: 'var(--teal-light)' }}>${avgPowerCost}</div>
            <div className="db-eff-label">Avg Est. Power Cost · $/MWh</div>
          </div>
          <div className="db-eff-card">
            <div className="db-eff-num" style={{ color: 'var(--green-light)' }}>
              {avgAcres.toLocaleString()}
            </div>
            <div className="db-eff-label">Avg Parcel Size · Acres</div>
          </div>
          <div className="db-eff-card">
            <div className="db-eff-num" style={{ color: 'var(--text-dark)' }}>${avgLandCost}</div>
            <div className="db-eff-label">Avg Land Cost · $/Acre</div>
          </div>
          <div className="db-eff-card">
            <div className="db-eff-num" style={{ color: 'var(--orange-light)' }}>
              ${snap.spread.value}
            </div>
            <div className="db-eff-label">Waha Discount vs Grid</div>
          </div>
          <div className="db-eff-card">
            <div className="db-eff-num" style={{ color: '#22C55E' }}>
              {ercotCount}/{sites.length}
            </div>
            <div className="db-eff-label">Sites on ERCOT · Waha Gas</div>
          </div>
        </div>

      </div>
    </section>
  )
}
