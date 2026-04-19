import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function closeFences(text) {
  const count = (text.match(/```/g) || []).length
  return count % 2 !== 0 ? text + '\n```' : text
}

const S = {
  p:          { margin: '0 0 0.6em 0', lineHeight: 'inherit', color: 'inherit' },
  h1:         { fontSize: '15px', fontWeight: 600, color: '#E8DFD0', borderBottom: '1px solid #2a2520', paddingBottom: '4px', margin: '0.9em 0 0.45em' },
  h2:         { fontSize: '14px', fontWeight: 600, color: '#E8DFD0', borderBottom: '1px solid #2a2520', paddingBottom: '3px', margin: '0.8em 0 0.4em' },
  h3:         { fontSize: '13px', fontWeight: 600, color: '#E8DFD0', margin: '0.7em 0 0.35em' },
  ul:         { margin: '0 0 0.6em 0', paddingLeft: '1.4em', color: 'inherit' },
  ol:         { margin: '0 0 0.6em 0', paddingLeft: '1.4em', color: 'inherit' },
  li:         { marginBottom: '0.2em', lineHeight: 'inherit' },
  codeInline: { fontFamily: "'IBM Plex Mono', monospace", fontSize: '0.88em', background: 'rgba(255,255,255,0.08)', padding: '1px 5px', borderRadius: '3px', whiteSpace: 'nowrap' },
  pre:        { background: '#0d0c0a', border: '1px solid #2a2520', borderRadius: '6px', padding: '10px 12px', overflowX: 'auto', margin: '0 0 0.6em 0' },
  codeBlock:  { fontFamily: "'IBM Plex Mono', monospace", fontSize: '11px', color: '#C8C0B4', background: 'none', whiteSpace: 'pre' },
  table:      { width: '100%', borderCollapse: 'collapse', margin: '0 0 0.6em 0', fontSize: 'inherit' },
  th:         { textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid #2a2520', color: '#E8DFD0', fontWeight: 600 },
  td:         { padding: '4px 8px', borderBottom: '1px solid #1e1c1a', color: 'inherit' },
  a:          { color: '#4AA88A', textDecoration: 'none' },
  blockquote: { borderLeft: '3px solid #2a2520', margin: '0 0 0.6em 0', paddingLeft: '12px', fontStyle: 'italic', color: '#9a9088' },
}

export default function MarkdownRenderer({ children, className, streaming = false }) {
  if (!children) return null
  const text = streaming ? closeFences(children) : children

  return (
    <div className={`md-content${className ? ` ${className}` : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p:          ({ children }) => <p style={S.p}>{children}</p>,
          h1:         ({ children }) => <h1 style={S.h1}>{children}</h1>,
          h2:         ({ children }) => <h2 style={S.h2}>{children}</h2>,
          h3:         ({ children }) => <h3 style={S.h3}>{children}</h3>,
          ul:         ({ children }) => <ul style={S.ul}>{children}</ul>,
          ol:         ({ children }) => <ol style={S.ol}>{children}</ol>,
          li:         ({ children }) => <li style={S.li}>{children}</li>,
          pre:        ({ children }) => <pre style={S.pre}>{children}</pre>,
          code:       ({ className, children }) => {
            const isBlock = Boolean(className) || String(children).includes('\n')
            return isBlock
              ? <code className={className} style={S.codeBlock}>{children}</code>
              : <code style={S.codeInline}>{children}</code>
          },
          table:      ({ children }) => <table style={S.table}>{children}</table>,
          th:         ({ children }) => <th style={S.th}>{children}</th>,
          td:         ({ children }) => <td style={S.td}>{children}</td>,
          a:          ({ href, children }) => <a href={href} style={S.a} target="_blank" rel="noopener noreferrer">{children}</a>,
          blockquote: ({ children }) => <blockquote style={S.blockquote}>{children}</blockquote>,
          strong:     ({ children }) => <strong style={{ fontWeight: 600, color: 'inherit' }}>{children}</strong>,
          em:         ({ children }) => <em style={{ fontStyle: 'italic', color: 'inherit' }}>{children}</em>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
