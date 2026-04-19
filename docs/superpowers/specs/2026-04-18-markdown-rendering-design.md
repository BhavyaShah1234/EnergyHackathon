# Markdown Rendering for AI Responses

**Date:** 2026-04-18  
**Status:** Approved

## Problem

All three AI response surfaces in the COLLIDE frontend render text as unstyled plain strings. Backend prompts explicitly prohibited markdown output (`"No bullet points."`, `"Use plain English."`) because raw markdown syntax (asterisks, hashes, backticks) would leak visibly into the UI. This prevents the AI from structuring responses with headers, bullets, tables, bold emphasis, and code blocks.

## Solution

Add `react-markdown` + `remark-gfm` for display rendering. Update backend prompts to allow and encourage markdown output. No backend streaming changes required.

## Architecture

```
src/components/MarkdownRenderer.jsx   ← new shared component
    AgentChat.jsx                     ← swap Message body render
    BriefingCard.jsx                  ← swap section render, remove manual split
    SummaryTab.jsx                    ← swap narrative-box content
```

Single shared `MarkdownRenderer` component keeps all markdown config (plugins, element overrides, theme styles) in one file.

## Component: MarkdownRenderer

**Props:**
- `children` — the markdown string to render
- `className` — optional wrapper class
- `streaming` — boolean; enables streaming-safe fence-closing when `true`

**Element overrides** (inline styles, dark theme):
| Element | Treatment |
|---------|-----------|
| `p` | Preserves existing line-height/color, no extra margin fighting parent |
| `h1`–`h3` | Slightly larger, `#E8DFD0`, bottom border in muted color |
| `ul` / `ol` | Left-padded, `#C8C0B4`, rhythm-consistent spacing |
| `code` (inline) | `rgba(255,255,255,0.08)` bg, monospace, no wrap |
| `pre` / `code` (block) | Dark panel, slight border, scrollable, whitespace preserved |
| `table` | Full-width, `thead` border-bottom, alternating row tint |
| `a` | Accent color, `target="_blank"`, `rel="noopener noreferrer"` |
| `strong` / `em` | Inherit color, standard weight/italic |
| `blockquote` | Left border accent, indented, italic |

## Streaming Safety

`react-markdown` parses the full accumulated string on every render. During streaming, unclosed code fences (` ``` ` without a closing fence) cause everything after them to render as a code block. Fix: a small utility that appends a closing fence if the string contains an odd number of ` ``` ` occurrences. Applied only when `streaming={true}` — no-op on completed messages.

Partial bold/italic mid-stream is acceptable; it resolves once the token closes.

## Affected Files

### Frontend

| File | Change |
|------|--------|
| `src/components/MarkdownRenderer.jsx` | New component |
| `src/components/AgentChat.jsx` | Replace `<div className="chat-bubble">{text}</div>` with `<MarkdownRenderer streaming={streaming}>{text}</MarkdownRenderer>` |
| `src/components/BriefingCard.jsx` | Remove `split(/\n\n+/)` + div map; replace with `<MarkdownRenderer streaming={isStreaming}>{tokens}</MarkdownRenderer>` |
| `src/components/SummaryTab.jsx` | Replace `<div className="narrative-box">{narrative}</div>` with `<MarkdownRenderer className="narrative-box" streaming={status === 'streaming'}>{narrative}</MarkdownRenderer>` |

### Backend

| File | Change |
|------|--------|
| `backend/agent/graph.py` — `_SYNTHESIZE_SYSTEM` | Remove `"No bullet points."` Add markdown permission: headers, bullets, bold for key numbers, tables for comparisons |
| `backend/pipeline/evaluate.py` — `_NARRATION_SYSTEM` | Remove `"No bullet points."` and `"Use plain English."` Add markdown permission: bold key metrics, bullets where appropriate |
| `backend/agent/graph.py` — `_INTENT_SYSTEM` | **No change** — structured JSON output node, `"no markdown"` constraint stays |

## Dependencies

```
react-markdown    ^9.x
remark-gfm        ^4.x
```

## What Stays the Same

- SSE streaming infrastructure (`main.py`, `useAgent.js`, `useEvaluate.js`) — no changes
- Content quality constraints in prompts: specific numbers, cite headlines, no hedging, 3-5 paragraph structure
- `_INTENT_SYSTEM` prompt — untouched
- Existing CSS classes (`.chat-bubble`, `.briefing-section`, `.narrative-box`) remain on wrapper elements
