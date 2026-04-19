import { useRef, useState, useEffect, useCallback, useMemo } from 'react'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Rectangle,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'
import { useSites } from '../hooks/useApi'

function scoreToColor(v) {
  if (v >= 0.82) return '#3A8A65'
  if (v >= 0.76) return '#E85D04'
  return '#0D9488'
}

function scoreToLabel(v) {
  if (v >= 0.82) return 'HIGH'
  if (v >= 0.76) return 'MED'
  return 'LOWER'
}

/** Fit all sites once on first load so pan/zoom are not reset on refetch. */
function FitBounds({ sites }) {
  const map = useMap()
  const didFit = useRef(false)
  useEffect(() => {
    if (sites.length > 0 && !didFit.current) {
      map.fitBounds(sites.map(s => [s.lat, s.lng]), { padding: [60, 60] })
      didFit.current = true
    }
  }, [map, sites])
  return null
}

const MIN_RECT_DEG = 0.06

/**
 * Click-drag rectangle on the map (snip-style). Disables pan while drawing.
 */
function AreaSelectInteraction({ active, onRubberChange, onCommit }) {
  const map = useMap()

  useEffect(() => {
    if (!active) {
      onRubberChange(null)
      return
    }

    const el = map.getContainer()
    el.style.cursor = 'crosshair'
    map.doubleClickZoom.disable()

    let start = null
    let drawing = false

    const down = e => {
      map.dragging.disable()
      start = e.latlng
      drawing = true
      onRubberChange(L.latLngBounds(start, start))
    }

    const move = e => {
      if (!drawing || !start) return
      onRubberChange(L.latLngBounds(start, e.latlng))
    }

    const up = e => {
      if (!drawing || !start) return
      drawing = false
      map.dragging.enable()
      const b = L.latLngBounds(start, e.latlng)
      start = null
      onRubberChange(null)
      const sw = b.getSouthWest()
      const ne = b.getNorthEast()
      if (Math.abs(ne.lat - sw.lat) < MIN_RECT_DEG || Math.abs(ne.lng - sw.lng) < MIN_RECT_DEG) {
        return
      }
      onCommit(b)
    }

    /** If pointer is released outside the map, cancel draw without committing. */
    const docUp = () => {
      if (!drawing) return
      drawing = false
      start = null
      map.dragging.enable()
      onRubberChange(null)
    }

    map.on('mousedown', down)
    map.on('mousemove', move)
    map.on('mouseup', up)
    document.addEventListener('mouseup', docUp)

    return () => {
      el.style.cursor = ''
      map.doubleClickZoom.enable()
      map.dragging.enable()
      map.off('mousedown', down)
      map.off('mousemove', move)
      map.off('mouseup', up)
      document.removeEventListener('mouseup', docUp)
      onRubberChange(null)
    }
  }, [active, map, onRubberChange, onCommit])

  return null
}

function sitesInBounds(sites, bounds) {
  if (!bounds) return []
  return sites.filter(s => bounds.contains(L.latLng(s.lat, s.lng)))
}

export default function SiteMap() {
  const { sites, dataSource, refetchSites } = useSites()
  const [selectMode, setSelectMode] = useState(false)
  const [rubberBounds, setRubberBounds] = useState(null)
  const [committedBounds, setCommittedBounds] = useState(null)

  const onRubberChange = useCallback(b => {
    setRubberBounds(b)
  }, [])

  const onCommit = useCallback(
    bounds => {
      setCommittedBounds(bounds)
      setSelectMode(false)
      refetchSites()
    },
    [refetchSites]
  )

  useEffect(() => {
    if (!selectMode) return
    const onKey = e => {
      if (e.key === 'Escape') {
        setSelectMode(false)
        setRubberBounds(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectMode])

  const selectedSites = useMemo(
    () => sitesInBounds(sites, committedBounds),
    [sites, committedBounds]
  )

  const clearSelection = () => {
    setCommittedBounds(null)
    setRubberBounds(null)
    setSelectMode(false)
  }

  return (
    <section id="sitemap" style={{ padding: 0 }}>
      <div className="sitemap-header">
        <div className="sitemap-header-inner">
          <span className="section-eyebrow section-eyebrow--green">Site Map</span>
          <h2
            className="section-title section-title--light"
            style={{ fontSize: 'clamp(28px,3vw,42px)', marginTop: 8 }}
          >
            {sites.length} Candidate Sites · TX · NM · AZ
          </h2>
          <p className="sitemap-sub">
            Click markers for detail, or draw a rectangle to compare live pricing in that area.&nbsp;
            <span style={{ color: dataSource === 'live' ? '#22C55E' : '#7A6E5E' }}>
              {dataSource === 'live' ? '● Live scores' : '○ Cached scores'}
            </span>
          </p>
          <div className="sitemap-toolbar">
            <button
              type="button"
              className={`sitemap-tool-btn${selectMode ? ' sitemap-tool-btn--active' : ''}`}
              onClick={() => setSelectMode(v => !v)}
            >
              {selectMode ? 'Cancel selection' : 'Select area'}
            </button>
            {committedBounds && (
              <button type="button" className="sitemap-tool-btn sitemap-tool-btn--ghost" onClick={clearSelection}>
                Clear area
              </button>
            )}
          </div>
          {selectMode && (
            <p className="sitemap-select-hint">Click and drag on the map to draw a region. Press Esc to cancel.</p>
          )}
        </div>
        <div className="sitemap-legend">
          <div className="sitemap-legend-item">
            <span className="sitemap-dot" style={{ background: '#3A8A65' }} /> Score ≥ 82 — High
          </div>
          <div className="sitemap-legend-item">
            <span className="sitemap-dot" style={{ background: '#E85D04' }} /> Score 76–81 — Medium
          </div>
          <div className="sitemap-legend-item">
            <span className="sitemap-dot" style={{ background: '#0D9488' }} /> Score &lt; 76 — Lower
          </div>
        </div>
      </div>

      <MapContainer
        center={[32.4, -103.5]}
        zoom={6}
        style={{ height: '560px', width: '100%' }}
        scrollWheelZoom={false}
      >
        <FitBounds sites={sites} />
        <AreaSelectInteraction active={selectMode} onRubberChange={onRubberChange} onCommit={onCommit} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {rubberBounds && (
          <Rectangle
            bounds={rubberBounds}
            pathOptions={{ color: '#22C55E', weight: 2, fillColor: '#22C55E', fillOpacity: 0.15 }}
          />
        )}
        {committedBounds && (
          <Rectangle
            bounds={committedBounds}
            pathOptions={{
              color: '#3A8A65',
              weight: 2,
              dashArray: '8 6',
              fillColor: '#3A8A65',
              fillOpacity: 0.08,
            }}
          />
        )}
        {sites.map(site => (
          <CircleMarker
            key={site.id}
            center={[site.lat, site.lng]}
            radius={10 + site.scores.composite * 10}
            pathOptions={{
              color: scoreToColor(site.scores.composite),
              fillColor: scoreToColor(site.scores.composite),
              fillOpacity: 0.85,
              weight: 2,
            }}
          >
            <Popup>
              <div className="popup-inner">
                <div className="popup-name">{site.name}</div>
                <div className="popup-loc">
                  {site.location} · {site.market}
                </div>
                <div className="popup-score-row">
                  <span
                    className="popup-score-badge"
                    style={{ background: scoreToColor(site.scores.composite) }}
                  >
                    {scoreToLabel(site.scores.composite)} &nbsp; {Math.round(site.scores.composite * 100)} / 100
                  </span>
                </div>
                <table className="popup-table">
                  <tbody>
                    <tr>
                      <td>Sub-A Land</td>
                      <td>{Math.round(site.scores.subA * 100)}</td>
                    </tr>
                    <tr>
                      <td>Sub-B Gas</td>
                      <td>{Math.round(site.scores.subB * 100)}</td>
                    </tr>
                    <tr>
                      <td>Sub-C Power</td>
                      <td>{Math.round(site.scores.subC * 100)}</td>
                    </tr>
                    <tr>
                      <td>Gas ({site.gasHub})</td>
                      <td>${site.gasPrice.toFixed(2)}/MMBtu</td>
                    </tr>
                    <tr>
                      <td>Est. BTM power</td>
                      <td>${Number(site.estPowerCostMwh).toFixed(2)}/MWh</td>
                    </tr>
                    {site.lmp != null && (
                      <tr>
                        <td>LMP ({site.lmpNode})</td>
                        <td>${Number(site.lmp).toFixed(2)}/MWh</td>
                      </tr>
                    )}
                    <tr>
                      <td>Parcel</td>
                      <td>{site.acres.toLocaleString()} acres</td>
                    </tr>
                    <tr>
                      <td>Land Cost</td>
                      <td>${site.landCostPerAcre}/acre</td>
                    </tr>
                    <tr>
                      <td>Total land</td>
                      <td>${site.totalLandCostM.toFixed(2)}M</td>
                    </tr>
                    <tr>
                      <td>Fiber</td>
                      <td>{site.fiberKm != null ? `${site.fiberKm} km` : '—'}</td>
                    </tr>
                    <tr>
                      <td>Pipeline</td>
                      <td>{site.pipelineKm != null ? `${site.pipelineKm} km` : '—'}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      {committedBounds && (
        <div className="sitemap-pricing-panel">
          <div className="sitemap-pricing-head">
            <h3 className="sitemap-pricing-title">Pricing in selected area</h3>
            <span className="sitemap-pricing-meta">
              {selectedSites.length} site{selectedSites.length === 1 ? '' : 's'} ·{' '}
              {dataSource === 'live' ? 'Live API' : 'Cached fallback'}
            </span>
          </div>
          {selectedSites.length === 0 ? (
            <p className="sitemap-pricing-empty">No candidate sites fall inside this rectangle. Try a larger region.</p>
          ) : (
            <div className="sitemap-pricing-table-wrap">
              <table className="sitemap-pricing-table">
                <thead>
                  <tr>
                    <th>Site</th>
                    <th>Hub / node</th>
                    <th>Gas</th>
                    <th>Est. power</th>
                    <th>LMP</th>
                    <th>Land / ac</th>
                    <th>Total land</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedSites.map(site => (
                    <tr key={site.id}>
                      <td>
                        <div className="sitemap-pcell-name">{site.name}</div>
                        <div className="sitemap-pcell-loc">{site.location}</div>
                      </td>
                      <td className="sitemap-pcell-mono">
                        {site.gasHub}
                        <br />
                        <span className="sitemap-pcell-dim">{site.lmpNode}</span>
                      </td>
                      <td className="sitemap-pcell-mono">${site.gasPrice.toFixed(2)}/MMBtu</td>
                      <td className="sitemap-pcell-mono">${Number(site.estPowerCostMwh).toFixed(2)}/MWh</td>
                      <td className="sitemap-pcell-mono">
                        {site.lmp != null ? `$${Number(site.lmp).toFixed(2)}` : '—'}
                      </td>
                      <td className="sitemap-pcell-mono">${site.landCostPerAcre.toLocaleString()}</td>
                      <td className="sitemap-pcell-mono">${site.totalLandCostM.toFixed(2)}M</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
