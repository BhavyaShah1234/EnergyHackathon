import MarkdownRenderer from './MarkdownRenderer'

function ScoreBar({ label, value, color }) {
  return (
    <div className="score-bar-row">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="score-bar-val">{Math.round(value * 100)}</span>
    </div>
  )
}

function Gauge({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = pct >= 75 ? '#22C55E' : pct >= 50 ? '#F59E0B' : '#EF4444'
  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 120 70" width="160">
        <path d="M10,65 A55,55 0 0,1 110,65" fill="none" stroke="#2a2a2a" strokeWidth="12" />
        <path
          d="M10,65 A55,55 0 0,1 110,65"
          fill="none" stroke={color} strokeWidth="12"
          strokeDasharray={`${(pct / 100) * 172} 172`}
        />
        <text x="60" y="62" textAnchor="middle" fill={color} fontSize="22" fontWeight="bold">{pct}</text>
      </svg>
      <div className="gauge-label">Composite Score</div>
    </div>
  )
}

function RegimeProbBars({ proba }) {
  if (!proba || proba.length < 3) return null
  const items = [
    { label: 'Normal',          value: proba[0], color: '#22C55E' },
    { label: 'Stress/Scarcity', value: proba[1], color: '#EF4444' },
    { label: 'Wind Curtailment', value: proba[2], color: '#F59E0B' },
  ]
  return (
    <div className="regime-prob-section">
      <div className="regime-prob-title">Regime Confidence</div>
      {items.map(({ label, value, color }) => (
        <div key={label} className="regime-prob-row">
          <span className="regime-prob-label">{label}</span>
          <div className="regime-prob-track">
            <div className="regime-prob-fill" style={{ width: `${value * 100}%`, background: color }} />
          </div>
          <span className="regime-prob-pct">{Math.round(value * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

export default function SummaryTab({ scorecard: sc, narrative, status, error }) {
  if (!sc) {
    if (status === 'error') {
      return <div className="scorecard-loading">Evaluation failed: {error || 'Unknown error'}</div>
    }
    if (status === 'done') {
      return <div className="scorecard-loading">No scorecard returned for this coordinate.</div>
    }
    return <div className="scorecard-loading">Evaluating coordinate…</div>
  }

  const cost = sc.cost
  return (
    <div className="summary-tab">
      <Gauge value={sc.composite_score} />

      <div className="score-bars">
        <ScoreBar label="Land"  value={sc.land_score}  color="#3A8A65" />
        <ScoreBar label="Gas"   value={sc.gas_score}   color="#E85D04" />
        <ScoreBar label="Power" value={sc.power_score} color="#0D9488" />
      </div>

      <div className="regime-badge" data-regime={sc.regime}>
        {sc.regime === 'stress_scarcity'  && '🔴 Stress / Scarcity'}
        {sc.regime === 'wind_curtailment' && '🟡 Wind Curtailment'}
        {sc.regime === 'normal'           && '🟢 Normal'}
      </div>

      <RegimeProbBars proba={sc.regime_proba} />

      {cost && (
        <div className="npv-row">
          <div className="npv-cell">
            <div className="npv-val">${cost.npv_p10_m.toFixed(0)}M</div>
            <div className="npv-lbl">P10 NPV</div>
          </div>
          <div className="npv-cell">
            <div className="npv-val npv-val--mid">${cost.npv_p50_m.toFixed(0)}M</div>
            <div className="npv-lbl">P50 NPV</div>
          </div>
          <div className="npv-cell">
            <div className="npv-val">${cost.npv_p90_m.toFixed(0)}M</div>
            <div className="npv-lbl">P90 NPV</div>
          </div>
        </div>
      )}

      <div className="narrative-box">
        {narrative
          ? <MarkdownRenderer streaming={status === 'streaming'}>{narrative}</MarkdownRenderer>
          : (status === 'streaming' ? '…' : '')}
      </div>
    </div>
  )
}
