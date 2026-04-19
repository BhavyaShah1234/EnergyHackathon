const ITEMS = [
  { label: 'AZPS Demand',      value: '8,420 MW',       change: '▲ 1.2%',   dir: 'up' },
  { label: 'Waha Hub',         value: '$1.84/MMBtu',    change: '▲ $0.12',  dir: 'up' },
  { label: 'Henry Hub',        value: '$3.41/MMBtu',    change: '▼ $0.08',  dir: 'down' },
  { label: 'Palo Verde LMP',   value: '$38.50/MWh',     change: '▲ $2.10',  dir: 'up' },
  { label: 'SP15 LMP',         value: '$42.30/MWh',     change: '▲ $1.90',  dir: 'up' },
  { label: 'NP15 LMP',         value: '$40.10/MWh',     change: '▼ $0.50',  dir: 'down' },
  { label: 'KPHX Temp',        value: '98°F · Clear',   change: null,       dir: null },
  { label: 'Phoenix Forecast', value: '102°F high · Sunny', change: null,   dir: null },
  { label: 'CISO Net Gen',     value: '32,100 MW',      change: '▲ 0.8%',   dir: 'up' },
  { label: 'ERCO Demand',      value: '51,200 MW',      change: '▲ 3.1%',   dir: 'up' },
]

export default function LiveTicker() {
  const doubled = [...ITEMS, ...ITEMS]
  return (
    <div id="ticker">
      <div className="ticker-inner">
        <div className="ticker-label">● LIVE</div>
        <div className="ticker-track">
          <div className="ticker-items">
            {doubled.map((item, i) => (
              <div className="ticker-item" key={i}>
                <span>{item.label}</span> {item.value}
                {item.change && <span className={item.dir}>{item.change}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
