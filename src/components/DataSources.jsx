const SOURCES = [
  {
    name: 'EIA-930', sub: 'AZPS · CISO · ERCO',
    dataset: 'BA Demand · Net Gen · Interchange',
    dims: [{ cls: 'dim-badge--c', label: 'Sub-C' }],
    cadence: '15 min', freshness: '3 hours', statusCls: 'status-live', statusLabel: 'Live', live: true,
  },
  {
    name: 'EIA NG Spot', sub: 'Henry Hub · Waha',
    dataset: 'Daily Natural Gas Spot Prices',
    dims: [{ cls: 'dim-badge--b', label: 'Sub-B' }, { cls: 'dim-badge--c', label: 'Sub-C' }],
    cadence: '1 hr', freshness: '48 – 72 hrs', statusCls: 'status-live', statusLabel: 'Live', live: true,
  },
  {
    name: 'CAISO OASIS LMP', sub: 'Palo Verde · SP15 · NP15',
    dataset: '5-min Real-Time LMP',
    dims: [{ cls: 'dim-badge--c', label: 'Sub-C' }],
    cadence: '5 min', freshness: '1 hour', statusCls: 'status-live', statusLabel: 'Live', live: true,
  },
  {
    name: 'NOAA NWS Forecast', sub: 'Phoenix PSR/158,56',
    dataset: '72-hr Gridpoint Forecast',
    dims: [{ cls: 'dim-badge--c', label: 'Sub-C' }],
    cadence: '30 min', freshness: '2 hours', statusCls: 'status-live', statusLabel: 'Live', live: true,
  },
  {
    name: 'NOAA NWS Obs', sub: 'KPHX Station',
    dataset: 'Station Observations',
    dims: [{ cls: 'dim-badge--c', label: 'Sub-C' }],
    cadence: '10 min', freshness: '2 hours', statusCls: 'status-live', statusLabel: 'Live', live: true,
  },
  {
    name: 'BLM Surface Mgmt', sub: 'AZ · NM · TX',
    dataset: 'Land Ownership Polygons',
    dims: [{ cls: 'dim-badge--a', label: 'Sub-A' }],
    cadence: 'Daily', freshness: '168 hrs', statusCls: 'status-static', statusLabel: '◆ Static', live: false,
  },
  {
    name: 'FCC BDC Fiber', sub: 'FTTP · AZ · NM · TX',
    dataset: 'Fiber Infrastructure Availability',
    dims: [{ cls: 'dim-badge--a', label: 'Sub-A' }],
    cadence: 'Daily', freshness: '168 hrs', statusCls: 'status-static', statusLabel: '◆ Static', live: false,
  },
  {
    name: 'USGS NHD', sub: 'Waterbodies',
    dataset: 'Hydrography Polygons',
    dims: [{ cls: 'dim-badge--a', label: 'Sub-A' }],
    cadence: 'Daily', freshness: '168 hrs', statusCls: 'status-static', statusLabel: '◆ Static', live: false,
  },
  {
    name: 'FEMA NFHL', sub: 'Flood Hazard Zones',
    dataset: 'Floodplain Polygons',
    dims: [{ cls: 'dim-badge--a', label: 'Sub-A' }],
    cadence: 'Daily', freshness: '168 hrs', statusCls: 'status-static', statusLabel: '◆ Static', live: false,
  },
  {
    name: 'ERCOT MIS', sub: 'DAM · RTM · Fuel Mix',
    dataset: 'Settlement Point LMPs',
    dims: [{ cls: 'dim-badge--c', label: 'Sub-C' }],
    cadence: '15 min', freshness: '1 hour', statusCls: 'status-pending', statusLabel: '⏳ Pending Token', live: false,
  },
]

export default function DataSources() {
  return (
    <section id="data">
      <div className="section-inner">
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--teal reveal">Data Sources</span>
          <h2 className="section-title section-title--light reveal">Built on Authoritative<br/>Public Data.</h2>
          <p className="section-sub section-sub--light reveal">
            No scraped proxies. Every source is an authoritative government or ISO API,
            verified live and validated on every pull.
          </p>
        </div>

        <div className="reveal">
          <table className="data-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Dataset</th>
                <th>Dimension</th>
                <th>Cadence</th>
                <th>Freshness SLA</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {SOURCES.map((s) => (
                <tr key={s.name}>
                  <td>
                    <span className="source-name">{s.name}</span><br/>
                    <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{s.sub}</span>
                  </td>
                  <td>{s.dataset}</td>
                  <td>
                    <div className="source-dim">
                      {s.dims.map(d => <span key={d.label} className={`dim-badge ${d.cls}`}>{d.label}</span>)}
                    </div>
                  </td>
                  <td>{s.cadence}</td>
                  <td className="freshness">{s.freshness}</td>
                  <td className={s.statusCls}>
                    {s.live && <span className="pulse" style={{ marginRight: '6px' }} />}
                    {s.statusLabel}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="data-cards-mobile">
          <div className="data-card-mob reveal">
            <div className="data-card-mob-header">
              <span className="source-name mono" style={{ fontSize: '14px' }}>EIA-930 · CAISO · EIA NG</span>
              <span className="status-live mono" style={{ fontSize: '12px' }}><span className="pulse" /> Live</span>
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <span className="dim-badge dim-badge--c">Sub-C</span>
              <span className="dim-badge dim-badge--b">Sub-B</span>
            </div>
          </div>
          <div className="data-card-mob reveal" style={{ transitionDelay: '.1s' }}>
            <div className="data-card-mob-header">
              <span className="source-name mono" style={{ fontSize: '14px' }}>BLM · FCC · USGS · FEMA</span>
              <span className="status-static mono" style={{ fontSize: '12px' }}>◆ Static</span>
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <span className="dim-badge dim-badge--a">Sub-A</span>
            </div>
          </div>
          <div className="data-card-mob reveal" style={{ transitionDelay: '.2s' }}>
            <div className="data-card-mob-header">
              <span className="source-name mono" style={{ fontSize: '14px' }}>ERCOT MIS</span>
              <span className="status-pending mono" style={{ fontSize: '12px' }}>⏳ Pending</span>
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <span className="dim-badge dim-badge--c">Sub-C</span>
            </div>
          </div>
        </div>

        <div className="code-block reveal" style={{ marginTop: '64px' }}>
          <div className="code-header">
            <div className="code-dot code-dot-1" />
            <div className="code-dot code-dot-2" />
            <div className="code-dot code-dot-3" />
            <span className="code-filename">scripts/explain.py — row provenance trace</span>
          </div>
          <div className="code-body">
            <span className="code-comment"># Trace any silver row back to the raw API response that produced it</span>{'\n'}
            <span className="code-fn">python</span> <span className="code-string">scripts/explain.py</span> \{'\n'}
            {'  '}<span className="code-op">--dataset</span> <span className="code-string">caiso_lmp</span> \{'\n'}
            {'  '}<span className="code-op">--key</span> <span className="code-value">{'\'{"interval_start_utc":"2026-04-18T15:00:00+00:00","node":"PALOVRDE_ASR-APND","lmp_component":"LMP"}\''}</span>{'\n'}
            {'\n'}
            <span className="code-comment"># Output:</span>{'\n'}
            <span className="code-fn">request_id</span>{'  '}<span className="code-string">7f3a1c2e-8b4d-4e9a-bc1f-d2e5f6a7b8c9</span>{'\n'}
            <span className="code-fn">fetched_at</span>{'  '}<span className="code-string">2026-04-18T15:03:47Z</span>{'\n'}
            <span className="code-fn">payload_sha</span> <span className="code-string">sha256:a4f2e1...</span>{'\n'}
            <span className="code-fn">raw_file</span>{'    '}<span className="code-string">data/raw/caiso_lmp/2026-04-18/7f3a1c2e.json.gz</span>{'\n'}
            <span className="code-fn">price</span>{'       '}<span className="code-value">$38.50/MWh</span>{'  '}<span className="code-comment">← LMP component</span>
          </div>
        </div>
      </div>
    </section>
  )
}
