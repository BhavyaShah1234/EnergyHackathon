const STEPS = [
  {
    num: '01 — Ingest',
    title: 'Live API Pull',
    desc: '9 source APIs fetched on their native cadence — 5-min LMPs to weekly geospatial snapshots. Raw responses persisted with SHA256.',
    accent: 'step-accent--1',
  },
  {
    num: '02 — Validate',
    title: 'Schema + DQ Check',
    desc: 'Every row passes a Pandera schema. Violations are quarantined, never dropped silently. Freshness SLA per source enforced at ingest time.',
    accent: 'step-accent--2',
  },
  {
    num: '03 — Silver Lake',
    title: 'Partitioned Parquet',
    desc: 'Validated, deduped, feature-ready rows land in a partitioned Parquet lake. Natural-key dedup makes re-runs a no-op. DuckDB catalog auto-registered.',
    accent: 'step-accent--3',
  },
  {
    num: '04 — Score',
    title: 'Composite Site Score',
    desc: 'Sub-A + Sub-B + Sub-C composited into a single deployability score. Each dimension traceable to the raw API response that produced it.',
    accent: 'step-accent--4',
  },
]

export default function Workflow() {
  return (
    <section id="workflow">
      <div className="section-inner">
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--orange reveal">How It Works</span>
          <h2 className="section-title section-title--light reveal">From Raw API to<br/>Deployable Score.</h2>
          <p className="section-sub section-sub--light reveal">
            A hardened ingest pipeline validates every row before it touches your model.
            Provenance-tracked, tamper-evident, UTC-normalized.
          </p>
        </div>
        <div className="workflow-steps reveal">
          {STEPS.map((step) => (
            <div className="workflow-step" key={step.num}>
              <span className="step-num">{step.num}</span>
              <div className="step-title">{step.title}</div>
              <p className="step-desc">{step.desc}</p>
              <div className={`step-accent ${step.accent}`} />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
