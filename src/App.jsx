import { useEffect, useState } from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import StatsBar from './components/StatsBar'
import Dashboard from './components/Dashboard'
import SiteMap from './components/SiteMap'
import LiveTicker from './components/LiveTicker'
import Scoring from './components/Scoring'
import Footer from './components/Footer'
import ScorecardPanel from './components/ScorecardPanel'
import BottomStrip from './components/BottomStrip'
import AIAnalystPanel from './components/AIAnalystPanel'
import CompareMode from './components/CompareMode'
import { useEvaluate } from './hooks/useEvaluate'
import { useCompare } from './hooks/useCompare'
import { useOptimize } from './hooks/useOptimize'
import { useOptimizeConfig } from './hooks/useOptimizeConfig'
import { useMapContext } from './hooks/useMapContext'
import { useAgent } from './hooks/useAgent'

export default function App() {
  const { scorecard, narrative, status: evalStatus, error, evaluate, reset: resetEval } = useEvaluate()
  const { pins, results: compareResults, status: compareStatus, addPin, removePin, clearPins, runCompare } = useCompare()
  const { progress, optimal, status: optStatus, optimize, reset: resetOpt } = useOptimize()
  const { config, updateConfig, resetConfig } = useOptimizeConfig()
  const { chips, addChip, removeChip } = useMapContext()
  const { tokens, citations, status: agentStatus, ask, reset: resetAgent } = useAgent()

  const [panelOpen, setPanelOpen] = useState(false)
  const [analystOpen, setAnalystOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)

  const globalBusy = optStatus === 'running'
    || compareStatus === 'loading'
    || evalStatus === 'loading'
    || agentStatus === 'loading'
    || agentStatus === 'streaming'

  const mapBusyLabel = optStatus === 'running' ? 'Optimizing…'
    : compareStatus === 'loading' ? 'Comparing…'
    : evalStatus === 'loading' ? 'Evaluating…'
    : ''

  useEffect(() => {
    const handler = e => { evaluate(e.detail.lat, e.detail.lon); setPanelOpen(true) }
    window.addEventListener('collide:evaluate', handler)
    return () => window.removeEventListener('collide:evaluate', handler)
  }, [evaluate])

  useEffect(() => {
    if (compareStatus === 'done' && compareResults.length > 0) setCompareOpen(true)
  }, [compareStatus, compareResults])

  useEffect(() => {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return
        e.target.classList.add('visible')
        const fill = e.target.querySelector('.score-fill')
        if (fill) setTimeout(() => { fill.style.width = fill.dataset.width + '%' }, 300)
      })
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' })

    const scoreCardObserver = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return
        const fill = e.target.querySelector('.score-fill')
        if (fill) setTimeout(() => { fill.style.width = fill.dataset.width + '%' }, 500)
      })
    }, { threshold: 0.3 })

    document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el))
    document.querySelectorAll('.score-card').forEach(el => scoreCardObserver.observe(el))

    const nav = document.querySelector('nav')
    const handleScroll = () => {
      nav.style.background = window.scrollY > 40 ? 'rgba(12,11,9,0.97)' : 'rgba(12,11,9,0.85)'
    }
    window.addEventListener('scroll', handleScroll)
    return () => {
      revealObserver.disconnect()
      scoreCardObserver.disconnect()
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  const analystContext = { scorecard: scorecard || null, pins, chips }

  return (
    <>
      <Navbar onAnalystToggle={() => setAnalystOpen(o => !o)} analystOpen={analystOpen} />
      <Hero />
      <StatsBar />
      <Dashboard />
      <SiteMap
        comparePins={pins}
        onCompareAdd={addPin}
        onCompareRemove={removePin}
        onCompareClear={clearPins}
        onCompareRun={runCompare}
        compareStatus={compareStatus}
        optimize={optimize}
        optimal={optimal}
        optStatus={optStatus}
        config={config}
        updateConfig={updateConfig}
        resetConfig={resetConfig}
        onAddContextChip={(chip) => { addChip(chip); setAnalystOpen(true) }}
        globalBusy={globalBusy}
        mapBusyLabel={mapBusyLabel}
      />
      {compareOpen && (
        <CompareMode
          results={compareResults}
          status={compareStatus}
          onClose={() => { setCompareOpen(false); clearPins() }}
        />
      )}
      <BottomStrip />
      <LiveTicker />
      <Scoring />
      <Footer />
      {panelOpen && (
        <ScorecardPanel
          scorecard={scorecard}
          narrative={narrative}
          status={evalStatus}
          error={error}
          onClose={() => { resetEval(); setPanelOpen(false) }}
        />
      )}
      <AIAnalystPanel
        open={analystOpen}
        onClose={() => setAnalystOpen(false)}
        context={analystContext}
        chips={chips}
        onRemoveChip={removeChip}
        ask={ask}
        reset={resetAgent}
        tokens={tokens}
        citations={citations}
        agentStatus={agentStatus}
      />
    </>
  )
}
