function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}

const FEATURES = [
  '9 live data sources',
  'DuckDB catalog included',
  'Row-level provenance',
  '15-min freshness SLA',
]

export default function CTA() {
  return (
    <section id="cta">
      <div className="cta-glow" />
      <div className="section-inner">
        <span className="section-eyebrow section-eyebrow--orange reveal" style={{ display: 'block', textAlign: 'center', marginBottom: '16px' }}>
          Get Started
        </span>
        <h2 className="section-title section-title--light reveal" style={{ textAlign: 'center' }}>
          Ready to Site Your<br/>
          <em style={{ fontStyle: 'normal', background: 'linear-gradient(135deg,var(--orange-light),#FFB347)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Data Center?
          </em>
        </h2>
        <p className="section-sub section-sub--light reveal" style={{ textAlign: 'center', marginTop: '16px' }}>
          Request access to the COLLIDE siting platform. Pipeline runs continuously —
          your data is fresh before you log in.
        </p>
        <div className="cta-form reveal">
          <input className="cta-input" type="email" placeholder="your@email.com" />
          <a href="#" className="btn-primary">Request Access →</a>
        </div>
        <div className="cta-features reveal" style={{ marginTop: '36px' }}>
          {FEATURES.map((f) => (
            <div className="cta-feat" key={f}>
              <CheckIcon />{f}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
