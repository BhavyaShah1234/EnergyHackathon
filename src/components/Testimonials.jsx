const CARDS = [
  {
    quote: '"Silver tables are tidy enough to feed OpenDSS or TFT directly. Join keys are documented in the registry. I went from data to a trained forecast model in under two hours."',
    initials: 'ML',
    avatarCls: 'proof-avatar--b',
    name: 'ML / Scenario Modeler',
    role: 'Time-series forecasting · TFT · OpenDSS',
    delay: undefined,
  },
  {
    quote: null,
    quoteJsx: (
      <>
        "Parse <span className="mono" style={{ fontSize: '13px' }}>geometry_geojson</span> with{' '}
        <span className="mono" style={{ fontSize: '13px' }}>shapely.geometry.shape()</span>.
        No geopandas dependency at ingest time. The BLM + FEMA overlay cut our manual parcel review from days to minutes."
      </>
    ),
    initials: 'GS',
    avatarCls: 'proof-avatar--c',
    name: 'Geospatial Analyst',
    role: 'BLM · FEMA NFHL · NHD overlays',
    delay: '.1s',
  },
  {
    quote: null,
    quoteJsx: (
      <>
        "Query <span className="mono" style={{ fontSize: '13px' }}>catalog.duckdb</span> — it's the single source of truth.
        All failed runs in the last 24h, row-level lineage, freshness status.
        Our dashboard practically builds itself."
      </>
    ),
    initials: 'DA',
    avatarCls: 'proof-avatar--a',
    name: 'Dashboard Engineer',
    role: 'DuckDB · Parquet · Lineage queries',
    delay: '.2s',
  },
]

export default function Testimonials() {
  return (
    <section id="proof" style={{ padding: '100px 24px' }}>
      <div className="section-inner">
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--muted reveal">Built for Practitioners</span>
          <h2 className="section-title section-title--dark reveal">Designed for Every<br/>Downstream Team.</h2>
          <div className="divider divider--orange" style={{ marginTop: '16px' }} />
        </div>
        <div className="proof-grid">
          {CARDS.map((card) => (
            <div
              className="proof-card reveal"
              key={card.name}
              style={card.delay ? { transitionDelay: card.delay } : undefined}
            >
              <p className="proof-quote">{card.quoteJsx ?? card.quote}</p>
              <div className="proof-author">
                <div className={`proof-avatar ${card.avatarCls}`}>{card.initials}</div>
                <div>
                  <div className="proof-name">{card.name}</div>
                  <div className="proof-role">{card.role}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
