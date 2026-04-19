# Markdown Rendering for AI Responses — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all plain-text AI response rendering with `react-markdown` + `remark-gfm`, and update backend prompts to produce proper markdown.

**Architecture:** A single shared `MarkdownRenderer` component wraps `ReactMarkdown` with dark-theme inline styles and streaming-safe code-fence fixing. All three AI surfaces (`AgentChat`, `BriefingCard`, `SummaryTab`) import it. Backend `_SYNTHESIZE_SYSTEM` and `_NARRATION_SYSTEM` prompts are updated to allow and encourage markdown output.

**Tech Stack:** react-markdown ^9.x, remark-gfm ^4.x, React 18, Vite 6

> **Note:** This project has no test framework configured (no vitest/jest in package.json). Each task includes manual verification steps in place of automated tests.

---

### Task 1: Install dependencies

**Files:**
- Modify: `package.json` (via npm)

- [ ] **Step 1: Install react-markdown and remark-gfm**

```bash
npm install react-markdown remark-gfm
```

- [ ] **Step 2: Verify installation**

```bash
npm list react-markdown remark-gfm
```

Expected output:
```
collide-platform@0.1.0
├── react-markdown@9.x.x
└── remark-gfm@4.x.x
```

- [ ] **Step 3: Verify dev server still starts**

```bash
npm run dev
```

Expected: Vite dev server starts on `http://localhost:5173` with no errors.

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add react-markdown and remark-gfm"
```

---

### Task 2: Create `MarkdownRenderer` component

**Files:**
- Create: `src/components/MarkdownRenderer.jsx`
- Modify: `src/index.css` (one rule for last-child margin reset)

- [ ] **Step 1: Create the component**

Create `src/components/MarkdownRenderer.jsx` with this exact content:

```jsx
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
```

- [ ] **Step 2: Add the last-child margin-reset rule to `src/index.css`**

Append to the end of `src/index.css`:

```css
.md-content > :last-child { margin-bottom: 0; }
```

- [ ] **Step 3: Manually verify the component renders**

Temporarily add this to `src/main.jsx` (or any mounted component) and check in browser:

```jsx
import MarkdownRenderer from './components/MarkdownRenderer'

// Inside any rendered tree:
<MarkdownRenderer>{"## Hello\n\nThis is **bold** and `inline code`.\n\n- item one\n- item two"}</MarkdownRenderer>
```

Expected: headers, bold, inline code chip, bullet list all render styled correctly in the dark theme. Remove after checking.

- [ ] **Step 4: Commit**

```bash
git add src/components/MarkdownRenderer.jsx src/index.css
git commit -m "feat: add MarkdownRenderer with dark-theme styles and streaming fence-fix"
```

---

### Task 3: Update `AgentChat.jsx`

**Files:**
- Modify: `src/components/AgentChat.jsx:1,11-22,59-68`

- [ ] **Step 1: Add import and update `Message` component**

Replace the top of `src/components/AgentChat.jsx` (lines 1–22):

```jsx
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
```

- [ ] **Step 2: Update the streaming assistant bubble (lines 58–69)**

Replace the streaming bubble block:

```jsx
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
```

- [ ] **Step 3: Verify in browser**

Start `npm run dev`, open AgentChat, send a message. Confirm:
- User messages still render as plain text (no markdown processing)
- Assistant responses render markdown (headers, bullets, bold) correctly
- Streaming text updates smoothly without layout jumps
- Citations chips still appear below the bubble

- [ ] **Step 4: Commit**

```bash
git add src/components/AgentChat.jsx
git commit -m "feat: render assistant chat responses with MarkdownRenderer"
```

---

### Task 4: Update `BriefingCard.jsx`

**Files:**
- Modify: `src/components/BriefingCard.jsx:1,16,46-51`

- [ ] **Step 1: Add import, remove manual split, replace section render**

Replace the full `src/components/BriefingCard.jsx`:

```jsx
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
```

- [ ] **Step 2: Verify in browser**

Open the BriefingCard panel. Confirm:
- Content renders with markdown structure (numbered sections, bold, etc.)
- The manual paragraph split is gone (no duplicate section breaks)
- Refresh button still works and triggers a new fetch
- Citations still render below

- [ ] **Step 3: Commit**

```bash
git add src/components/BriefingCard.jsx
git commit -m "feat: render BriefingCard content with MarkdownRenderer, remove manual split"
```

---

### Task 5: Update `SummaryTab.jsx`

**Files:**
- Modify: `src/components/SummaryTab.jsx:1,102-104`

- [ ] **Step 1: Add import**

Add import on line 1 of `src/components/SummaryTab.jsx`:

```jsx
import MarkdownRenderer from './MarkdownRenderer'
```

- [ ] **Step 2: Replace the narrative-box div (lines 102–104)**

Replace:
```jsx
      <div className="narrative-box">
        {narrative || (status === 'streaming' ? '…' : '')}
      </div>
```

With:
```jsx
      <div className="narrative-box">
        {narrative
          ? <MarkdownRenderer streaming={status === 'streaming'}>{narrative}</MarkdownRenderer>
          : (status === 'streaming' ? '…' : '')}
      </div>
```

- [ ] **Step 3: Verify in browser**

Click a map coordinate to trigger evaluation. Confirm:
- Streaming shows `…` placeholder until narrative arrives
- Once narrative streams in, markdown renders (bold numbers, bullet sub-points if present)
- `.narrative-box` spacing is preserved (no extra padding from last `<p>` margin due to `.md-content > :last-child` rule)

- [ ] **Step 4: Commit**

```bash
git add src/components/SummaryTab.jsx
git commit -m "feat: render site narrative with MarkdownRenderer"
```

---

### Task 6: Update `_SYNTHESIZE_SYSTEM` prompt (agent chat + briefing)

**Files:**
- Modify: `backend/agent/graph.py:33-36`

- [ ] **Step 1: Replace `_SYNTHESIZE_SYSTEM`**

In `backend/agent/graph.py`, replace lines 33–36:

```python
_SYNTHESIZE_SYSTEM = """You are a senior BTM data center investment analyst.
You have access to live scoring data, market regime, LMP forecasts, and news.
Write a concise, direct response (3-5 paragraphs max). Include specific numbers.
Cite news headlines by title when you use them. No bullet points. No hedging."""
```

With:

```python
_SYNTHESIZE_SYSTEM = """You are a senior BTM data center investment analyst.
You have access to live scoring data, market regime, LMP forecasts, and news.
Write a concise, direct response. Include specific numbers. Cite news headlines by title when you use them. No hedging.
Format your response in markdown: **bold** key metrics and numbers; use bullet lists for multiple factors or comparisons; use ## headers to separate major sections when the response spans multiple topics; use tables when comparing two or more options side by side."""
```

- [ ] **Step 2: Verify via the agent chat**

Start the backend (`npm run dev:api`) and frontend (`npm run dev`). Send a message like:
- "Compare sites at 31.9,-102.1 and 32.5,-101.2" — expect a table or bullet comparison
- "What happens if gas prices spike 40%?" — expect bold numbers and bullet factors

Confirm markdown structure renders correctly end-to-end.

- [ ] **Step 3: Commit**

```bash
git add backend/agent/graph.py
git commit -m "feat: update synthesize prompt to produce markdown output"
```

---

### Task 7: Update `_NARRATION_SYSTEM` prompt (site narrative)

**Files:**
- Modify: `backend/pipeline/evaluate.py:74-79`

- [ ] **Step 1: Replace `_NARRATION_SYSTEM`**

In `backend/pipeline/evaluate.py`, replace lines 74–79:

```python
_NARRATION_SYSTEM = """You are a senior energy infrastructure analyst advising a data center development team.
Given a BTM site scorecard, write a concise 3-paragraph executive summary:
1. Site overview: what makes it strong or weak across the three dimensions.
2. Key risk: which dimension is the binding constraint and why.
3. Timing recommendation: based on the current market regime and any news.
Use plain English. Be specific about numbers. No bullet points."""
```

With:

```python
_NARRATION_SYSTEM = """You are a senior energy infrastructure analyst advising a data center development team.
Given a BTM site scorecard, write a concise executive summary with exactly three sections:
1. **Site overview**: what makes it strong or weak across land, gas, and power dimensions.
2. **Key risk**: which dimension is the binding constraint and why.
3. **Timing recommendation**: based on the current market regime and any news.
Be specific about numbers. Use markdown: **bold** key metrics and scores, bullet sub-points within a section where helpful. Keep each section to 2-3 sentences."""
```

- [ ] **Step 2: Verify via the site evaluation**

Trigger a site evaluation by clicking a coordinate on the map. Confirm:
- Narrative streams in with markdown structure (bold section labels, bold numbers)
- Three sections are clearly delineated
- `.narrative-box` renders it cleanly without overflow

- [ ] **Step 3: Commit**

```bash
git add backend/pipeline/evaluate.py
git commit -m "feat: update narration prompt to produce markdown output"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All spec requirements covered — shared component (Task 2), all 3 surfaces (Tasks 3–5), both backend prompts (Tasks 6–7), `_INTENT_SYSTEM` untouched, streaming safety in `MarkdownRenderer`, last-child margin reset in `index.css`
- [x] **No placeholders:** All tasks contain exact code, exact commands, exact expected output
- [x] **Type consistency:** `MarkdownRenderer` props (`children`, `className`, `streaming`) used identically across all 3 consumer tasks
- [x] **Streaming prop:** All three surfaces pass `streaming` correctly — `AgentChat` uses `status === 'streaming'`, `BriefingCard` uses `status === 'streaming'`, `SummaryTab` uses `status === 'streaming'`
