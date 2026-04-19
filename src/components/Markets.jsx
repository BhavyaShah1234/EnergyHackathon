export default function Markets() {
  return (
    <section id="markets">
      <div className="section-inner">
        <div className="section-header">
          <span className="section-eyebrow section-eyebrow--muted reveal">Market Coverage</span>
          <h2 className="section-title section-title--dark reveal">Primary &amp; Secondary<br/>Markets.</h2>
          <p className="section-sub section-sub--dark reveal">
            ERCOT West Texas anchors the Permian opportunity. WECC Arizona and New Mexico
            expand the addressable footprint with CAISO-adjacent power economics.
          </p>
        </div>

        <div className="markets-grid">
          <div className="market-card reveal">
            <div className="market-header">
              <div>
                <div className="market-name">ERCOT</div>
                <div className="market-region mono">West Texas · Permian Basin · Panhandle</div>
              </div>
              <span className="market-badge market-badge--primary">Primary</span>
            </div>
            <div className="market-body">
              <ul className="market-nodes">
                <li>
                  <div className="node-dot node-dot--orange" />
                  Waha Hub (Gas Anchor)
                  <span className="node-price node-price--orange">$1.84/MMBtu</span>
                </li>
                <li>
                  <div className="node-dot node-dot--orange" />
                  West Texas Settlement Point
                  <span className="node-price node-price--orange">Pending</span>
                </li>
                <li>
                  <div className="node-dot node-dot--orange" />
                  Panhandle Hub
                  <span className="node-price node-price--orange">~$1.90/MMBtu</span>
                </li>
              </ul>
              <div className="market-stats-row">
                <div className="market-stat">
                  <div className="market-stat-num market-stat-num--orange">$0.97</div>
                  <div className="market-stat-label">Waha Discount</div>
                </div>
                <div className="market-stat">
                  <div className="market-stat-num market-stat-num--orange">TX</div>
                  <div className="market-stat-label">State Coverage</div>
                </div>
                <div className="market-stat">
                  <div className="market-stat-num market-stat-num--orange">1</div>
                  <div className="market-stat-label">Token Pending</div>
                </div>
              </div>
            </div>
          </div>

          <div className="market-card reveal" style={{ transitionDelay: '.15s' }}>
            <div className="market-header">
              <div>
                <div className="market-name">WECC</div>
                <div className="market-region mono">Arizona · New Mexico · Nevada</div>
              </div>
              <span className="market-badge market-badge--secondary">Secondary</span>
            </div>
            <div className="market-body">
              <ul className="market-nodes">
                <li>
                  <div className="node-dot node-dot--teal" />
                  Palo Verde (CAISO Hub)
                  <span className="node-price node-price--teal">$38.50/MWh</span>
                </li>
                <li>
                  <div className="node-dot node-dot--teal" />
                  SP15 (Southern Cal)
                  <span className="node-price node-price--teal">$42.30/MWh</span>
                </li>
                <li>
                  <div className="node-dot node-dot--teal" />
                  NP15 (Northern Cal)
                  <span className="node-price node-price--teal">$40.10/MWh</span>
                </li>
              </ul>
              <div className="market-stats-row">
                <div className="market-stat">
                  <div className="market-stat-num market-stat-num--teal">5min</div>
                  <div className="market-stat-label">LMP Cadence</div>
                </div>
                <div className="market-stat">
                  <div className="market-stat-num market-stat-num--teal">AZ NM</div>
                  <div className="market-stat-label">State Coverage</div>
                </div>
                <div className="market-stat">
                  <div className="market-stat-num market-stat-num--teal">3</div>
                  <div className="market-stat-label">Live Nodes</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
