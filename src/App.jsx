import { useEffect } from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import StatsBar from './components/StatsBar'
import Dashboard from './components/Dashboard'
import SiteMap from './components/SiteMap'
import LiveTicker from './components/LiveTicker'
import Scoring from './components/Scoring'
import Workflow from './components/Workflow'
import DataSources from './components/DataSources'
import Markets from './components/Markets'
import DataQuality from './components/DataQuality'
import Testimonials from './components/Testimonials'
import CTA from './components/CTA'
import Footer from './components/Footer'

export default function App() {
  useEffect(() => {
    // Single reveal observer for all .reveal elements
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return
        e.target.classList.add('visible')
        const fill = e.target.querySelector('.score-fill')
        if (fill) setTimeout(() => { fill.style.width = fill.dataset.width + '%' }, 300)
      })
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' })

    // Single score-card observer (one observer watching all cards, not N observers)
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
      nav.style.background = window.scrollY > 40
        ? 'rgba(12,11,9,0.97)'
        : 'rgba(12,11,9,0.85)'
    }
    window.addEventListener('scroll', handleScroll)

    return () => {
      revealObserver.disconnect()
      scoreCardObserver.disconnect()
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  return (
    <>
      <Navbar />
      <Hero />
      <StatsBar />
      <Dashboard />
      <SiteMap />
      <LiveTicker />
      <Scoring />
      <Workflow />
      <DataSources />
      <Markets />
      <DataQuality />
      <Testimonials />
      <CTA />
      <Footer />
    </>
  )
}
