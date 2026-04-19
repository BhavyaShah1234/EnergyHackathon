export default function StatsBar() {
  return (
    <section id="stats" style={{ padding: 0 }}>
      <div className="stats-inner">
        <div className="stat-item reveal">
          <div className="stat-num stat-num--orange">9</div>
          <div className="stat-label">Live Data Sources</div>
        </div>
        <div className="stat-item reveal" style={{ transitionDelay: '.1s' }}>
          <div className="stat-num stat-num--teal">3</div>
          <div className="stat-label">Scoring Dimensions</div>
        </div>
        <div className="stat-item reveal" style={{ transitionDelay: '.2s' }}>
          <div className="stat-num stat-num--green">15m</div>
          <div className="stat-label">Min Data Freshness</div>
        </div>
        <div className="stat-item reveal" style={{ transitionDelay: '.3s' }}>
          <div className="stat-num stat-num--white">3</div>
          <div className="stat-label">States · AZ · NM · TX</div>
        </div>
      </div>
    </section>
  )
}
