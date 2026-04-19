import { useEffect } from 'react'
import { useAgent } from '../hooks/useAgent'
import MarkdownRenderer from './MarkdownRenderer'

export default function BriefingCard({ regime }) {
  const { tokens, citations, status, ask, reset } = useAgent()

  useEffect(() => {
    ask(
      'Give me a current market briefing: (1) current regime state and what it means for BTM economics, ' +
      '(2) the strongest siting opportunity right now and why, (3) the top risk to watch.',
      { regime }
    )
    return reset
  }, [])  // fire once on mount

  return (
    <div className="briefing-card">
      <div className="briefing-card-header">
        <span className="briefing-card-title">Market Briefing</span>
        <button
          className="briefing-refresh-btn"
          onClick={() => {
            reset()
            ask(
              'Give me a current market briefing: (1) current regime and BTM economics, ' +
              '(2) strongest siting opportunity, (3) top risk.',
              { regime }
            )
          }}
          disabled={status === 'loading' || status === 'streaming'}
        >
          {status === 'loading' || status === 'streaming' ? '…' : '↺'}
        </button>
      </div>

      {status === 'error' && (
        <div className="briefing-error">Analysis unavailable — check ANTHROPIC_API_KEY</div>
      )}

      {status === 'loading' && (
        <div className="briefing-thinking">Analyzing market conditions…</div>
      )}

      {tokens && (
        <div className="briefing-sections">
          <MarkdownRenderer streaming={status === 'streaming'}>{tokens}</MarkdownRenderer>
        </div>
      )}

      {citations.length > 0 && (
        <div className="briefing-citations">
          {citations.slice(0, 4).map((c, i) => (
            <span key={i} className="citation-chip citation-chip--blue">{c}</span>
          ))}
        </div>
      )}
    </div>
  )
}
