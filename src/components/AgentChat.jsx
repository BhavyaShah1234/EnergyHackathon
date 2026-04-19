import { useState, useRef, useEffect } from 'react'
import { useAgent } from '../hooks/useAgent'
import MarkdownRenderer from './MarkdownRenderer'

function CitationChip({ text }) {
  const isCoord = /^-?\d+\.\d+,-?\d+\.\d+/.test(text)
  const isNode = /^(HB_|PALO|SP15|NP15)/.test(text)
  const cls = isCoord ? 'citation-chip--green' : isNode ? 'citation-chip--orange' : 'citation-chip--blue'
  return <span className={`citation-chip ${cls}`}>{text}</span>
}

function Message({ role, text, citations }) {
  return (
    <div className={`chat-message chat-message--${role}`}>
      <div className="chat-bubble">
        {role === 'assistant'
          ? <MarkdownRenderer>{text}</MarkdownRenderer>
          : text}
      </div>
      {citations && citations.length > 0 && (
        <div className="chat-citations">
          {citations.map((c, i) => <CitationChip key={i} text={c} />)}
        </div>
      )}
    </div>
  )
}

export default function AgentChat({ context }) {
  const [input, setInput] = useState('')
  const [history, setHistory] = useState([])
  const { tokens, citations, status, ask, reset } = useAgent()
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [tokens, history])

  const submit = () => {
    if (!input.trim() || status === 'loading' || status === 'streaming') return
    const q = input.trim()
    setHistory(h => [...h, { role: 'user', text: q }])
    setInput('')
    reset()
    ask(q, context)
  }

  const onKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }

  useEffect(() => {
    if (status === 'done' && tokens) {
      setHistory(h => [...h, { role: 'assistant', text: tokens, citations }])
      reset()
    }
  }, [status])

  return (
    <div className="agent-chat">
      <div className="chat-messages">
        {history.map((msg, i) => (
          <Message key={i} role={msg.role} text={msg.text} citations={msg.citations} />
        ))}
        {(status === 'loading' || status === 'streaming') && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-bubble">
              {status === 'loading'
                ? <span className="chat-thinking">Thinking…</span>
                : <MarkdownRenderer streaming>{tokens}</MarkdownRenderer>}
            </div>
            {citations.length > 0 && (
              <div className="chat-citations">
                {citations.map((c, i) => <CitationChip key={i} text={c} />)}
              </div>
            )}
          </div>
        )}
        {status === 'error' && (
          <div className="chat-message chat-message--error">
            <div className="chat-bubble">Error: check ANTHROPIC_API_KEY and backend logs.</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask about sites, timing, stress scenarios, or economics…"
          rows={2}
        />
        <button
          className="chat-send-btn"
          onClick={submit}
          disabled={!input.trim() || status === 'loading' || status === 'streaming'}
        >
          →
        </button>
      </div>
    </div>
  )
}
