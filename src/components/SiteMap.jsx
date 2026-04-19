import { useRef, useState, useEffect, useCallback, useMemo } from 'react'
import {
  MapContainer, TileLayer, CircleMarker, Popup, Rectangle, useMap,
} from 'react-leaflet'
import L from 'leaflet'
import { useSites } from '../hooks/useApi'
import { useHeatmap } from '../hooks/useHeatmap'
import MapContextMenu from './MapContextMenu'
import MapStatusIndicator from './MapStatusIndicator'
import OptimizeConfigDialog from './OptimizeConfigDialog'

function scoreToColor(v) {
  if (v >= 0.72) return '#3A8A65'
  if (v >= 0.58) return '#E85D04'
  return '#0D9488'
}

function scoreToLabel(v) {
  if (v >= 0.72) return 'HIGH'
  if (v >= 0.58) return 'MED'
  return 'LOWER'
}

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

function AreaSelectInteraction({ active, onRubberChange, onCommit }) {
  const map = useMap()
  useEffect(() => {
    if (!active) { onRubberChange(null); return }
    const el = map.getContainer()
    el.style.cursor = 'crosshair'
    map.doubleClickZoom.disable()
    let start = null, drawing = false

    const down = e => { map.dragging.disable(); start = e.latlng; drawing = true; onRubberChange(L.latLngBounds(start, start)) }
    const move = e => { if (!drawing || !start) return; onRubberChange(L.latLngBounds(start, e.latlng)) }
    const up = e => {
      if (!drawing || !start) return
      drawing = false; map.dragging.enable()
      const b = L.latLngBounds(start, e.latlng); start = null; onRubberChange(null)
      const sw = b.getSouthWest(), ne = b.getNorthEast()
      if (Math.abs(ne.lat - sw.lat) < MIN_RECT_DEG || Math.abs(ne.lng - sw.lng) < MIN_RECT_DEG) return
      onCommit(b)
    }
    const docUp = () => { if (!drawing) return; drawing = false; start = null; map.dragging.enable(); onRubberChange(null) }

    map.on('mousedown', down); map.on('mousemove', move); map.on('mouseup', up)
    document.addEventListener('mouseup', docUp)
    return () => {
      el.style.cursor = ''; map.doubleClickZoom.enable(); map.dragging.enable()
      map.off('mousedown', down); map.off('mousemove', move); map.off('mouseup', up)
      document.removeEventListener('mouseup', docUp); onRubberChange(null)
    }
  }, [active, map, onRubberChange, onCommit])
  return null
}

function MapContextHandler({ onContextMenu }) {
  const map = useMap()
  useEffect(() => {
    const handler = e => {
      L.DomEvent.preventDefault(e)
      onContextMenu(
        e.originalEvent.clientX,
        e.originalEvent.clientY,
        { type: 'space', lat: e.latlng.lat, lon: e.latlng.lng }
      )
    }
    map.on('contextmenu', handler)
    return () => map.off('contextmenu', handler)
  }, [map, onContextMenu])
  return null
}

function sitesInBounds(sites, bounds) {
  if (!bounds) return []
  return sites.filter(s => bounds.contains(L.latLng(s.lat, s.lng)))
}

export default function SiteMap({
  comparePins = [], onCompareAdd, onCompareRemove, onCompareClear, onCompareRun, compareStatus,
  optimize, optimal, optStatus, config, updateConfig, resetConfig,
  onAddContextChip, globalBusy, mapBusyLabel,
}) {
  const { sites, dataSource, refetchSites } = useSites()
  const [selectMode, setSelectMode] = useState(false)
  const [rubberBounds, setRubberBounds] = useState(null)
  const [committedBounds, setCommittedBounds] = useState(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [contextMenu, setContextMenu] = useState(null)
  const { features, activeLayer, loading: heatLoading, loadLayer } = useHeatmap()

  const openContextMenu = useCallback((x, y, target) => {
    setContextMenu({ open: true, x, y, target })
  }, [])

  const closeContextMenu = useCallback(() => setContextMenu(null), [])

  const handleSiteContextMenu = useCallback((e, site) => {
    L.DomEvent.stop(e)
    openContextMenu(e.originalEvent.clientX, e.originalEvent.clientY, { type: 'site', site })
  }, [openContextMenu])

  const onRubberChange = useCallback(b => setRubberBounds(b), [])

  const onCommit = useCallback(bounds => {
    setCommittedBounds(bounds)
    setSelectMode(false)
    refetchSites()
    if (onAddContextChip) {
      const sw = bounds.getSouthWest(), ne = bounds.getNorthEast()
      onAddContextChip({ type: 'region', payload: { sw: { lat: sw.lat, lon: sw.lng }, ne: { lat: ne.lat, lon: ne.lng } } })
    }
  }, [refetchSites, onAddContextChip])

  useEffect(() => {
    if (!selectMode) return
    const onKey = e => { if (e.key === 'Escape') { setSelectMode(false); setRubberBounds(null) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectMode])

  useEffect(() => {
    const handler = () => {
      if (!committedBounds || !optimize || !config) return
      const sw = committedBounds.getSouthWest(), ne = committedBounds.getNorthEast()
      optimize({ sw: { lat: sw.lat, lon: sw.lng }, ne: { lat: ne.lat, lon: ne.lng } }, config)
    }
    window.addEventListener('collide:run-optimize', handler)
    return () => window.removeEventListener('collide:run-optimize', handler)
  }, [committedBounds, optimize, config])

  const selectedSites = useMemo(() => sitesInBounds(sites, committedBounds), [sites, committedBounds])

  const clearSelection = () => { setCommittedBounds(null); setRubberBounds(null); setSelectMode(false) }

  const handleSetRegionCenter = useCallback((lat, lng) => {
    if (!committedBounds) return
    const sw = committedBounds.getSouthWest(), ne = committedBounds.getNorthEast()
    const halfLat = (ne.lat - sw.lat) / 2, halfLng = (ne.lng - sw.lng) / 2
    setCommittedBounds(L.latLngBounds([lat - halfLat, lng - halfLng], [lat + halfLat, lng + halfLng]))
  }, [committedBounds])

  const handleEvaluate = useCallback((lat, lon) => {
    window.dispatchEvent(new CustomEvent('collide:evaluate', { detail: { lat, lon } }))
  }, [])

  return (
    <section id="sitemap" style={{ padding: 0 }}>
      <div className="sitemap-header">
        <div className="sitemap-header-inner">
          <span className="section-eyebrow section-eyebrow--green">Site Map</span>
          <h2 className="section-title section-title--light" style={{ fontSize: 'clamp(28px,3vw,42px)', marginTop: 8 }}>
            {sites.length} Candidate Sites · TX · NM · AZ
          </h2>
          <p className="sitemap-sub">
            Right-click markers or map for options. Draw a rectangle to analyze an area.&nbsp;
            <span style={{ color: dataSource === 'live' ? '#22C55E' : '#7A6E5E' }}>
              {dataSource === 'live' ? '● Live scores' : '○ Cached scores'}
            </span>
          </p>
          <div className="sitemap-toolbar">
            <button type="button" className={`sitemap-tool-btn${selectMode ? ' sitemap-tool-btn--active' : ''}`}
              onClick={() => setSelectMode(v => !v)}>
              {selectMode ? 'Cancel selection' : 'Select area'}
            </button>
            {committedBounds && (
              <button type="button" className="sitemap-tool-btn sitemap-tool-btn--ghost" onClick={clearSelection}>
                Clear area
              </button>
            )}
            <button
              type="button"
              className={`sitemap-tool-btn${optStatus === 'running' ? ' sitemap-tool-btn--active' : ''}`}
              disabled={globalBusy}
              onClick={() => {
                if (!committedBounds) return alert('Draw a region first')
                const sw = committedBounds.getSouthWest(), ne = committedBounds.getNorthEast()
                optimize({ sw: { lat: sw.lat, lon: sw.lng }, ne: { lat: ne.lat, lon: ne.lng } }, config)
              }}
            >
              {optStatus === 'running' ? 'Searching…' : 'Find Best Site'}
            </button>
            <button type="button" className="sitemap-tool-btn sitemap-tool-btn--ghost"
              onClick={() => setConfigOpen(true)}>
              Config
            </button>
          </div>
          {selectMode && (
            <p className="sitemap-select-hint">Click and drag on the map to draw a region. Press Esc to cancel.</p>
          )}
        </div>
        <div className="sitemap-legend">
          <div className="sitemap-legend-item"><span className="sitemap-dot" style={{ background: '#3A8A65' }} /> Score ≥ 72 — High</div>
          <div className="sitemap-legend-item"><span className="sitemap-dot" style={{ background: '#E85D04' }} /> Score 58–71 — Medium</div>
          <div className="sitemap-legend-item"><span className="sitemap-dot" style={{ background: '#0D9488' }} /> Score &lt; 58 — Lower</div>
        </div>
      </div>

      <div style={{ position: 'relative' }}>
        <MapContainer center={[32.4, -103.5]} zoom={6} style={{ height: '560px', width: '100%' }} scrollWheelZoom={false}>
          <FitBounds sites={sites} />
          <MapContextHandler onContextMenu={openContextMenu} />
          <AreaSelectInteraction active={selectMode} onRubberChange={onRubberChange} onCommit={onCommit} />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {rubberBounds && <Rectangle bounds={rubberBounds} pathOptions={{ color: '#22C55E', weight: 2, fillColor: '#22C55E', fillOpacity: 0.15 }} />}
          {committedBounds && <Rectangle bounds={committedBounds} pathOptions={{ color: '#3A8A65', weight: 2, dashArray: '8 6', fillColor: '#3A8A65', fillOpacity: 0.08 }} />}
          {optimal && (
            <CircleMarker
              center={[optimal.lat, optimal.lon]}
              radius={18}
              pathOptions={{ color: '#22C55E', fillColor: '#22C55E', fillOpacity: 0.9, weight: 3 }}
              eventHandlers={{ click: () => handleEvaluate(optimal.lat, optimal.lon) }}
            >
              <Popup>
                <div className="popup-inner">
                  <div className="popup-name">Optimal Site</div>
                  <div className="popup-loc">{optimal.lat.toFixed(4)}°N, {Math.abs(optimal.lon).toFixed(4)}°W</div>
                  <div className="popup-score-row">
                    <span className="popup-score-badge" style={{ background: scoreToColor(optimal.composite_score) }}>
                      {scoreToLabel(optimal.composite_score)} &nbsp; {Math.round(optimal.composite_score * 100)} / 100
                    </span>
                  </div>
                  <table className="popup-table">
                    <tbody>
                      <tr><td>Land</td><td>{Math.round((optimal.land_score ?? 0) * 100)}</td></tr>
                      <tr><td>Gas</td><td>{Math.round((optimal.gas_score ?? 0) * 100)}</td></tr>
                      <tr><td>Power</td><td>{Math.round((optimal.power_score ?? 0) * 100)}</td></tr>
                    </tbody>
                  </table>
                  <div style={{ fontSize: 10, color: '#888', marginTop: 4 }}>Click for full evaluation →</div>
                </div>
              </Popup>
            </CircleMarker>
          )}
          {sites.map(site => (
            <CircleMarker
              key={site.id}
              center={[site.lat, site.lng]}
              radius={10 + site.scores.composite * 10}
              pathOptions={{ color: scoreToColor(site.scores.composite), fillColor: scoreToColor(site.scores.composite), fillOpacity: 0.85, weight: 2 }}
              eventHandlers={{
                click: () => handleEvaluate(site.lat, site.lng),
                contextmenu: e => handleSiteContextMenu(e, site),
              }}
            >
              <Popup>
                <div className="popup-inner">
                  <div className="popup-name">{site.name}</div>
                  <div className="popup-loc">{site.location} · {site.market}</div>
                  <div className="popup-score-row">
                    <span className="popup-score-badge" style={{ background: scoreToColor(site.scores.composite) }}>
                      {scoreToLabel(site.scores.composite)} &nbsp; {Math.round(site.scores.composite * 100)} / 100
                    </span>
                  </div>
                  <table className="popup-table">
                    <tbody>
                      <tr><td>Land</td><td>{Math.round((site.scores.land ?? site.scores.subA ?? 0) * 100)}</td></tr>
                      <tr><td>Gas</td><td>{Math.round((site.scores.gas ?? site.scores.subB ?? 0) * 100)}</td></tr>
                      <tr><td>Power</td><td>{Math.round((site.scores.power ?? site.scores.subC ?? 0) * 100)}</td></tr>
                      <tr><td>Gas ({site.gasHub})</td><td>${site.gasPrice.toFixed(2)}/MMBtu</td></tr>
                      <tr><td>Est. BTM power</td><td>${Number(site.estPowerCostMwh).toFixed(2)}/MWh</td></tr>
                      {site.lmp != null && <tr><td>LMP ({site.lmpNode})</td><td>${Number(site.lmp).toFixed(2)}/MWh</td></tr>}
                      <tr><td>Parcel</td><td>{site.acres.toLocaleString()} acres</td></tr>
                      <tr><td>Land Cost</td><td>${site.landCostPerAcre}/acre</td></tr>
                      <tr><td>Total land</td><td>${site.totalLandCostM.toFixed(2)}M</td></tr>
                      <tr><td>Fiber</td><td>{site.fiberKm != null ? `${site.fiberKm} km` : '—'}</td></tr>
                      <tr><td>Pipeline</td><td>{site.pipelineKm != null ? `${site.pipelineKm} km` : '—'}</td></tr>
                    </tbody>
                  </table>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          <div className="map-layer-toggles" style={{ position: 'absolute', top: 10, right: 10, zIndex: 1000, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {['composite', 'gas', 'lmp'].map(layer => (
              <button key={layer} className={`layer-toggle-pill${activeLayer === layer ? ' layer-toggle-pill--active' : ''}`} onClick={() => loadLayer(layer)}>
                {heatLoading && activeLayer === layer ? '…' : layer}
              </button>
            ))}
          </div>

          {features.map((feat, i) => (
            <CircleMarker key={`heat-${i}`}
              center={[feat.geometry.coordinates[1], feat.geometry.coordinates[0]]}
              radius={16}
              pathOptions={{ fillColor: feat.properties.score >= 0.75 ? '#22C55E' : feat.properties.score >= 0.5 ? '#F59E0B' : '#EF4444', fillOpacity: 0.35, stroke: false }}
            />
          ))}

          {comparePins.map((pin, i) => (
            <CircleMarker key={`pin-${i}`} center={[pin.lat, pin.lon]} radius={10}
              pathOptions={{ color: '#A78BFA', fillColor: '#A78BFA', fillOpacity: 0.7 }}>
              <Popup>
                <div style={{ fontSize: 12, fontFamily: 'monospace', minWidth: 140 }}>
                  <div style={{ marginBottom: 6 }}>Pin {i + 1}: ({pin.lat.toFixed(3)}, {pin.lon.toFixed(3)})</div>
                  {onCompareRemove && (
                    <button
                      onClick={() => onCompareRemove(i)}
                      style={{ fontSize: 11, padding: '2px 8px', cursor: 'pointer', background: '#7F1D1D', color: '#FCA5A5', border: '1px solid #991B1B', borderRadius: 3 }}
                    >
                      Remove pin
                    </button>
                  )}
                </div>
              </Popup>
            </CircleMarker>
          ))}

        </MapContainer>
        <MapStatusIndicator mapBusy={!!globalBusy} label={mapBusyLabel || 'Processing…'} />
      </div>

      <MapContextMenu
        open={!!contextMenu?.open}
        x={contextMenu?.x ?? 0}
        y={contextMenu?.y ?? 0}
        target={contextMenu?.target ?? null}
        committedBounds={committedBounds}
        onClose={closeContextMenu}
        onEvaluate={(lat, lon) => { handleEvaluate(lat, lon); closeContextMenu() }}
        onAddCompare={(lat, lon) => { if (onCompareAdd) onCompareAdd(lat, lon); closeContextMenu() }}
        onSendToAgent={(chip) => { if (onAddContextChip) onAddContextChip(chip); closeContextMenu() }}
        onSetRegionCenter={(lat, lng) => { handleSetRegionCenter(lat, lng); closeContextMenu() }}
      />

      {comparePins.length >= 2 && (
        <div className="compare-header-bar">
          <span>{comparePins.length} sites selected</span>
          <button className="compare-run-btn" onClick={onCompareRun} disabled={compareStatus === 'loading' || globalBusy}>
            {compareStatus === 'loading' ? 'Comparing…' : 'Compare Sites →'}
          </button>
          <button className="compare-clear-btn" onClick={onCompareClear}>Clear</button>
        </div>
      )}

      {committedBounds && (
        <div className="sitemap-pricing-panel">
          <div className="sitemap-pricing-head">
            <h3 className="sitemap-pricing-title">Pricing in selected area</h3>
            <span className="sitemap-pricing-meta">{selectedSites.length} site{selectedSites.length === 1 ? '' : 's'} · {dataSource === 'live' ? 'Live API' : 'Cached fallback'}</span>
          </div>
          {selectedSites.length === 0 ? (
            <p className="sitemap-pricing-empty">No candidate sites fall inside this rectangle. Try a larger region.</p>
          ) : (
            <div className="sitemap-pricing-table-wrap">
              <table className="sitemap-pricing-table">
                <thead>
                  <tr><th>Site</th><th>Hub / node</th><th>Gas</th><th>Est. power</th><th>LMP</th><th>Land / ac</th><th>Total land</th></tr>
                </thead>
                <tbody>
                  {selectedSites.map(site => (
                    <tr key={site.id}>
                      <td><div className="sitemap-pcell-name">{site.name}</div><div className="sitemap-pcell-loc">{site.location}</div></td>
                      <td className="sitemap-pcell-mono">{site.gasHub}<br /><span className="sitemap-pcell-dim">{site.lmpNode}</span></td>
                      <td className="sitemap-pcell-mono">${site.gasPrice.toFixed(2)}/MMBtu</td>
                      <td className="sitemap-pcell-mono">${Number(site.estPowerCostMwh).toFixed(2)}/MWh</td>
                      <td className="sitemap-pcell-mono">{site.lmp != null ? `$${Number(site.lmp).toFixed(2)}` : '—'}</td>
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

      <OptimizeConfigDialog
        open={configOpen}
        config={config || {}}
        onApply={cfg => { if (updateConfig) updateConfig(cfg); setConfigOpen(false) }}
        onReset={() => { if (resetConfig) resetConfig() }}
        onClose={() => setConfigOpen(false)}
      />
    </section>
  )
}
