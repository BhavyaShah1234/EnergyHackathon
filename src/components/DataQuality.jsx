const ITEMS = [
  {
    iconCls: 'quality-icon--green',
    iconColor: 'var(--green-light)',
    title: 'No Corrupted Rows',
    desc: <>Every row passes its Pandera schema. Violations quarantined with a <span className="mono">_reason</span> column — never silently dropped.</>,
    svg: <><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></>,
    delay: undefined,
  },
  {
    iconCls: 'quality-icon--teal',
    iconColor: 'var(--teal-light)',
    title: 'Idempotent Writes',
    desc: 'Natural-key dedup per dataset. Re-running the same time window is always a no-op — safe for backfill and catch-up.',
    svg: <><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.31"/></>,
    delay: '.05s',
  },
  {
    iconCls: 'quality-icon--orange',
    iconColor: 'var(--orange-light)',
    title: 'Full Provenance Trail',
    desc: <><span className="mono">_source</span>, <span className="mono">_request_id</span>, <span className="mono">_fetched_at_utc</span>, <span className="mono">_payload_sha256</span> on every row in every dataset.</>,
    svg: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>,
    delay: '.1s',
  },
  {
    iconCls: 'quality-icon--green',
    iconColor: 'var(--green-light)',
    title: 'Tamper-Evident Silver',
    desc: <> SHA256 manifest of every silver Parquet. <span className="mono">scripts/verify_integrity.py</span> detects any drift outside the pipeline.</>,
    svg: <><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></>,
    delay: '.15s',
  },
  {
    iconCls: 'quality-icon--teal',
    iconColor: 'var(--teal-light)',
    title: 'Freshness SLA Enforced',
    desc: <>Per-source SLA from 1 hour (CAISO) to 168 hours (geospatial). Failures recorded in DuckDB <span className="mono">run_ledger</span> and per-run JSON reports.</>,
    svg: <><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>,
    delay: '.2s',
  },
  {
    iconCls: 'quality-icon--orange',
    iconColor: 'var(--orange-light)',
    title: 'UTC Everywhere',
    desc: <>All timestamps normalized to <span className="mono">datetime64[ns, UTC]</span> at ingest time. No timezone ambiguity for point-in-time training.</>,
    svg: <><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></>,
    delay: '.25s',
  },
]

export default function DataQuality() {
  return (
    <section id="quality">
      <div className="section-inner">
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--orange reveal">Data Quality</span>
          <h2 className="section-title section-title--light reveal">Guaranteed Quality<br/>at Every Row.</h2>
          <p className="section-sub section-sub--light reveal">
            Eight hardened guarantees from raw API response to silver parquet.
            Your model trains on clean data or it doesn't train at all.
          </p>
        </div>

        <div className="quality-grid">
          {ITEMS.map((item) => (
            <div
              className="quality-item reveal"
              key={item.title}
              style={item.delay ? { transitionDelay: item.delay } : undefined}
            >
              <div className={`quality-icon ${item.iconCls}`}>
                <svg viewBox="0 0 24 24" fill="none" stroke={item.iconColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {item.svg}
                </svg>
              </div>
              <div className="quality-title">{item.title}</div>
              <p className="quality-desc">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
