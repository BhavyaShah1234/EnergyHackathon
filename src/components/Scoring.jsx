function LandIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
      <polyline points="9 22 9 12 15 12 15 22"/>
    </svg>
  )
}

function GasIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="var(--orange)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
    </svg>
  )
}

function PowerIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="var(--teal)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  )
}

export default function Scoring() {
  return (
    <section id="scoring">
      <div className="section-inner">
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--muted reveal">Site Scoring</span>
          <h2 className="section-title section-title--dark reveal">Three Dimensions.<br/>One Score.</h2>
          <p className="section-sub section-sub--dark reveal">
            Every candidate site is evaluated across land viability, gas supply reliability,
            and BTM power economics — composited into a single deployability score.
          </p>
        </div>

        <div className="scoring-grid">
          <div className="score-card score-card--a reveal">
            <div className="score-icon score-icon--a"><LandIcon /></div>
            <div className="score-badge score-badge--a">Sub-A · Land &amp; Lease</div>
            <h3 className="score-title">Land &amp; Lease<br/>Viability</h3>
            <p className="score-desc">
              Parcel-level suitability across federal, state, and private land.
              Fiber proximity, floodplain exposure, and surface management agency classification.
            </p>
            <ul className="score-metrics">
              <li>BLM &amp; Texas GLO parcel size / zoning</li>
              <li>FCC BDC fiber proximity (FTTP)</li>
              <li>FEMA NFHL floodplain overlay</li>
              <li>USGS NHD water body proximity</li>
              <li>Surface management agency code</li>
            </ul>
            <div className="score-meter">
              <div className="score-meter-label"><span>Confidence</span><span>92%</span></div>
              <div className="score-bar"><div className="score-fill score-fill--a" data-width="92" /></div>
            </div>
          </div>

          <div className="score-card score-card--b reveal" style={{ transitionDelay: '.1s' }}>
            <div className="score-icon score-icon--b"><GasIcon /></div>
            <div className="score-badge score-badge--b">Sub-B · Gas Supply</div>
            <h3 className="score-title">Gas Supply<br/>Reliability</h3>
            <p className="score-desc">
              PHMSA pipeline failure probability, historic curtailment exposure,
              and redundancy at candidate interconnects. Waha Hub price dynamics.
            </p>
            <ul className="score-metrics">
              <li>PHMSA incident &amp; failure rate by pipe segment</li>
              <li>Waha Hub spot vs. Henry Hub spread</li>
              <li>Pipeline redundancy &amp; alternate paths</li>
              <li>Curtailment history (EIA-176 / EIA-757)</li>
              <li>Compressor station proximity</li>
            </ul>
            <div className="score-meter">
              <div className="score-meter-label"><span>Confidence</span><span>78%</span></div>
              <div className="score-bar"><div className="score-fill score-fill--b" data-width="78" /></div>
            </div>
          </div>

          <div className="score-card score-card--c reveal" style={{ transitionDelay: '.2s' }}>
            <div className="score-icon score-icon--c"><PowerIcon /></div>
            <div className="score-badge score-badge--c">Sub-C · Power Economics</div>
            <h3 className="score-title">BTM Power<br/>Economics</h3>
            <p className="score-desc">
              Real-time and forecast LMP at ERCOT settlement points and CAISO/WAPA nodes.
              Gas-to-power spread, heat rate arbitrage, 6–72h forward curves.
            </p>
            <ul className="score-metrics">
              <li>CAISO 5-min LMP: Palo Verde, SP15, NP15</li>
              <li>ERCOT settlement point prices (pending)</li>
              <li>Gas-to-power spread (Waha / Henry Hub)</li>
              <li>NOAA 72-hr load forecasting inputs</li>
              <li>EIA-930 15-min BA demand &amp; net gen</li>
            </ul>
            <div className="score-meter">
              <div className="score-meter-label"><span>Confidence</span><span>85%</span></div>
              <div className="score-bar"><div className="score-fill score-fill--c" data-width="85" /></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
