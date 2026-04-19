export default function Navbar({ onAnalystToggle, analystOpen }) {
  return (
    <nav>
      <a href="#" className="nav-logo">
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="var(--orange-light)" stroke="var(--orange-light)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        COLLIDE
      </a>
      <ul className="nav-links">
        <li><a href="#scoring">Scoring</a></li>
        <li><a href="#workflow">Workflow</a></li>
        <li><a href="#quality">Quality</a></li>
      </ul>
      <button
        className={`analyst-toggle-btn${analystOpen ? ' analyst-toggle-btn--active' : ''}`}
        onClick={onAnalystToggle}
        title="AI Analyst"
      >
        ⚡ AI Analyst
      </button>
    </nav>
  )
}
