# COLLIDE Docs Pages — Design Spec
_Date: 2026-04-19_

## Problem

The COLLIDE platform has no user-facing documentation. The footer has placeholder links ("Schema Reference", "API Docs") that go nowhere. Users and developers have no reference for how the scoring engine works, what data sources are used, or what the API contracts look like.

## Goal

Add six `/docs/*` pages rendered from markdown, accessible via a shared Navbar "Docs" link and an in-page sidebar. Use `marked` with GFM + `mermaid` for diagrams.

---

## Routes

| Path | Title |
|---|---|
| `/docs/overview` | What is COLLIDE? |
| `/docs/architecture` | System Architecture |
| `/docs/howitworks` | How the Scoring Works |
| `/docs/features` | Platform Features |
| `/docs/data` | Data Sources & Pipeline |
| `/docs/schema` | Schema Reference |

Navigating to `/docs` (no page) redirects to `/docs/overview`.

---

## Architecture

```
main.jsx
└── BrowserRouter
    └── Routes
        ├── /          → <App />            (unchanged)
        ├── /docs      → redirect to /docs/overview
        └── /docs/:page → <DocsPage />
               ├── shared <Navbar />         (+ Docs link added)
               └── <DocsLayout>
                   ├── <DocsSidebar />
                   └── <DocsContent />
```

### New files

```
src/
  docs/
    DocsPage.jsx       — route component, reads :page param
    DocsLayout.jsx     — flex wrapper: sidebar + content
    DocsSidebar.jsx    — nav list, active state via useParams
    DocsContent.jsx    — renders md string via marked, runs mermaid
    pages/
      overview.js
      architecture.js
      howitworks.js
      features.js
      data.js
      schema.js
```

### Modified files

| File | Change |
|---|---|
| `src/main.jsx` | Wrap in BrowserRouter, add Routes for / and /docs/:page |
| `src/components/Navbar.jsx` | Add Docs link (react-router Link) |
| `src/components/Footer.jsx` | Wire "Schema Reference" and "API Docs" to /docs/schema and /docs/schema#api |
| `vercel.json` | Add SPA fallback rewrite (before existing /api rewrite) |
| `package.json` | Add react-router-dom, marked, mermaid |

---

## Component Details

### DocsPage.jsx
- Reads `useParams().page`
- Looks up page in a `{ overview, architecture, ... }` map
- If not found, renders a 404 message
- Renders `<DocsLayout>` with the matched markdown string

### DocsSidebar.jsx
- List of 6 `<NavLink>` items
- Active item styled with `--orange-light` left border + colour
- On mobile (< 640px): renders as horizontal scrollable strip above content

### DocsContent.jsx
- Receives a markdown string
- Calls `marked.parse(md)` with GFM enabled
- Sets HTML via `dangerouslySetInnerHTML`
- `useEffect` after render: calls `mermaid.run()` on all `.language-mermaid` blocks
- Wraps in a `docs-content` div with scoped prose styles

### Navbar.jsx change
- Add `<Link to="/docs/overview" className="nav-link">Docs</Link>` to `nav-links`
- Use `react-router-dom` `Link` (not `<a>`) so it doesn't hard-reload

---

## Styling

- Background: `var(--dark)` / `var(--dark-card)` — same as main site
- Content max-width: `760px`, centred in content area
- Sidebar width: `200px`, fixed on desktop; horizontal strip on mobile
- Active sidebar item: `border-left: 2px solid var(--orange-light)`, `color: var(--orange-light)`
- Prose: `font-family: var(--sans)`, `line-height: 1.75`, `color: var(--text-dark)`
- Code blocks: `var(--mono)`, same dark card background as existing MarkdownRenderer
- Tables: same style as MarkdownRenderer (`--dark-border` borders)
- Mermaid: `theme: 'dark'`, `background: transparent`
- Top padding: `64px` (navbar height) + `32px`

---

## Markdown Content Plan

### overview.js
- What COLLIDE is (1 paragraph, plain English)
- The problem it solves (3 bullet points)
- Who it's for
- Quick-start (numbered list: open app → click map → read scorecard → ask AI)
- Key stats badge strip (10 data sources, 3 scoring dimensions, 5 AI intents, 72h forecast)

### architecture.js
- Stack table (Frontend / Backend / Data)
- Mermaid diagram: full system (browser → API → scoring → live data)
- SSE streaming explained simply
- WebSocket LMP stream
- Deployment (Vite + FastAPI on Vercel)

### howitworks.js
- The three sub-problems (Sub-A land, Sub-B gas, Sub-C power) with bullet breakdowns
- Mermaid diagram: scoring pipeline (features → disqualifiers → scores → TOPSIS → cost)
- TOPSIS weights table (land 30%, gas 35%, power 35%)
- Cost model: NPV Monte Carlo briefly explained
- Web enrichment (Tavily + Claude Haiku) section

### features.js
- One section per major feature: Map, Scorecard, Compare, Optimizer, AI Analyst, Live Ticker, Heat Layers, Forecast
- Each: what it does + how to use (2–4 bullets)

### data.js
- Data sources table (source, what it provides, cadence, format)
- Mermaid pipeline flow (ingest → validate → parquet → DuckDB → API)
- DQ guarantees (schema validation, audit trail, freshness checks)
- Background refresh schedule (5 min / 30 min / 1 hr)

### schema.js
- Site model fields table
- Scorecard fields table
- CostEstimate fields table
- API endpoints table (method, path, purpose)
- SSE event formats (scorecard / web_context / narrative / done)
- Agent intent types

---

## Constraints

- No breaking changes to existing `App.jsx` or any existing component logic
- `marked` replaces `react-markdown` only in the docs pages — existing `MarkdownRenderer` is untouched
- Vercel SPA fallback rewrite must come after the `/api/*` rewrite so backend routes are not affected
- Mermaid initialised once per page render, not globally, to avoid conflicts with Leaflet

---

## Out of Scope

- Search within docs
- Versioning
- Dark/light mode toggle
- Auto-generating docs from code (all content hand-written)
