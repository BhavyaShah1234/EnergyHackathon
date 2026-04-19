const PLATFORM_LINKS = [
  { href: '#scoring', label: 'Scoring Engine' },
  { href: '#workflow', label: 'Pipeline' },
  { href: '#data', label: 'Data Sources' },
  { href: '#markets', label: 'Markets' },
]

const DATA_LINKS = [
  { label: 'EIA-930 BA' },
  { label: 'CAISO OASIS' },
  { label: 'NOAA NWS' },
  { label: 'BLM · FEMA · FCC' },
]

const DEV_LINKS = [
  { label: 'GitHub Repo' },
  { label: 'Schema Reference' },
  { label: 'DuckDB Catalog' },
  { label: 'API Docs' },
]

const BADGES = ['ERCOT', 'WECC', 'EIA', 'CAISO', 'NOAA']

export default function Footer() {
  return (
    <footer>
      <div className="footer-inner">
        <div className="footer-top">
          <div className="footer-brand">
            <a href="#" className="nav-logo" style={{ fontSize: '18px' }}>
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: '18px', height: '18px' }}>
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="var(--orange-light)" stroke="var(--orange-light)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              COLLIDE
            </a>
            <p>AI-powered BTM siting for natural gas data centers across ERCOT and WECC.</p>
          </div>

          <div>
            <div className="footer-col-title">Platform</div>
            <ul className="footer-links">
              {PLATFORM_LINKS.map(l => (
                <li key={l.label}><a href={l.href}>{l.label}</a></li>
              ))}
            </ul>
          </div>

          <div>
            <div className="footer-col-title">Data</div>
            <ul className="footer-links">
              {DATA_LINKS.map(l => (
                <li key={l.label}><a href="#">{l.label}</a></li>
              ))}
            </ul>
          </div>

          <div>
            <div className="footer-col-title">Developers</div>
            <ul className="footer-links">
              {DEV_LINKS.map(l => (
                <li key={l.label}><a href="#">{l.label}</a></li>
              ))}
            </ul>
          </div>
        </div>

        <div className="footer-bottom">
          <div className="footer-copy">
            © 2026 COLLIDE · Collide AI-for-Energy Hackathon · All data from authoritative public APIs
          </div>
          <div className="footer-badges">
            {BADGES.map(b => <span key={b} className="footer-badge">{b}</span>)}
          </div>
        </div>
      </div>
    </footer>
  )
}
