export default function Hero() {
  return (
    <section id="hero">
      <div className="hero-grid" />
      <div className="hero-glow" />

      <div className="hero-cards">
        <div className="hero-card hero-card--1">
          <div className="hcard-label">Waha Hub Spot</div>
          <div className="hcard-value hcard-value--orange">
            $1.84 <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>/MMBtu</span>
          </div>
          <div className="hcard-sub">↑ 0.12 today</div>
        </div>
        <div className="hero-card hero-card--2">
          <div className="hcard-label">AZPS Net Gen</div>
          <div className="hcard-value hcard-value--teal">8,420 MW</div>
          <div className="hcard-sub">15-min cadence · live</div>
        </div>
        <div className="hero-card hero-card--3">
          <div className="hcard-label">Palo Verde LMP</div>
          <div className="hcard-value hcard-value--green">
            $38.50 <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>/MWh</span>
          </div>
          <div className="hcard-sub">5-min · CAISO RTM</div>
        </div>
        <div className="hero-card hero-card--4">
          <div className="hcard-label">Phoenix Temp</div>
          <div className="hcard-value" style={{ color: 'var(--text-dark)' }}>98°F</div>
          <div className="hcard-sub">KPHX · 10-min obs</div>
        </div>
      </div>

      <div className="hero-inner">
        <div className="hero-eyebrow">AI-Powered BTM Siting Platform</div>
        <h1 className="hero-headline">
          Site the Next<br /><em>Data Center.</em>
        </h1>
        <p className="hero-sub">
          AI-driven land, gas supply, and power economics analysis across ERCOT and WECC.
          From Permian Basin parcels to CAISO LMPs — scored in seconds.
        </p>
        <div className="hero-actions">
          <a href="#scoring" className="btn-primary">Explore the Platform</a>
          <a href="#data" className="btn-secondary">View Live Data →</a>
        </div>
      </div>
    </section>
  )
}
