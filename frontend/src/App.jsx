import { useEffect, useState } from 'react'
import { API_URL } from './lib/analytics.js'
import Card from './components/Card.jsx'
import ConfirmModal from './components/ConfirmModal.jsx'
import AiConsent from './components/AiConsent.jsx'
import TestRunner from './components/TestRunner.jsx'
import AnalyticsDashboard from './components/AnalyticsDashboard.jsx'

function parseRoute() {
  const h = location.hash.replace(/^#\/?/, '')
  if (h === 'analytics') return { view: 'analytics' }
  if (h.startsWith('test/')) return { view: 'test', testId: h.slice(5) }
  return { view: 'home' }
}

export default function App() {
  const [route, setRoute] = useState(parseRoute)
  const [cards, setCards] = useState([])
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [confirming, setConfirming] = useState(null)
  const [llm, setLlm] = useState({ on: false, model: null })
  const [aiChoice, setAiChoice] = useState(false)

  useEffect(() => {
    const onHash = () => setRoute(parseRoute())
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    fetch(`${API_URL}/api/tests`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setCards)
      .catch(() => setError('Could not reach the Hive server. Please refresh in a moment.'))
    fetch(`${API_URL}/api/health`)
      .then((r) => r.json())
      .then((h) => setLlm({ on: Boolean(h.llm_enabled), model: h.llm_model }))
      .catch(() => {})
  }, [])

  const go = (hash) => {
    location.hash = hash
    scrollTo({ top: 0 })
  }

  const available = cards.filter((c) => c.available).length

  return (
    <>
      <header className="nav">
        <a className="brand" href="#/" onClick={() => go('#/')}>
          <span className="brand-mark" aria-hidden="true" />
          HIVE
        </a>
        <nav className="tabs" aria-label="Main">
          <button className="active" onClick={() => go('#/')}>Tests</button>
        </nav>
      </header>

      {route.view === 'home' && (
        <main className="container">
          <section className="hero">
            <p className="eyebrow">Psychological tests · open & evidence-based</p>
            <h1>
              Know your <span className="hl">mind</span>.
            </h1>
            <p className="lede">
              Classic psychology tests, scored only from published datasets and research. Pick a card to see what it
              measures and where its questions come from.
            </p>
            {cards.length > 0 && (
              <p className="hero-meta">
                <strong>{available}</strong> tests · every question, image and score traced to a published source
              </p>
            )}
          </section>

          {error && <div className="alert">{error}</div>}
          {!error && cards.length === 0 && (
            <div className="waking">
              <div className="loader" aria-hidden="true" />
              <p className="muted">Loading the tests… if Hive has been idle, the server can take up to a minute to wake up.</p>
            </div>
          )}

          <section className="grid">
            {cards.map((card, i) => (
              <Card
                key={card.id}
                card={card}
                index={i}
                open={openId === card.id}
                onToggle={() => setOpenId((cur) => (cur === card.id ? null : card.id))}
                onStart={() => {
                  setAiChoice(false)
                  setConfirming(card)
                }}
              />
            ))}
          </section>

          <p className="fineprint">
            Hive is for education and self-reflection. None of these results are a clinical assessment or diagnosis.
          </p>
        </main>
      )}

      {route.view === 'test' && (
        <TestRunner
          key={route.testId}
          testId={route.testId}
          aiConsent={llm.on && sessionStorage.getItem(`hive_ai_consent_${route.testId}`) === 'yes'}
          onExit={() => go('#/')}
        />
      )}
      {route.view === 'analytics' && <AnalyticsDashboard />}

      {confirming && (
        <ConfirmModal
          title={confirming.title}
          body={`${confirming.question_count} questions · about ${confirming.minutes} minutes. Your answers are scored on Hive's server.`}
          confirmLabel="Yes, enter"
          onCancel={() => setConfirming(null)}
          onConfirm={() => {
            const id = confirming.id
            sessionStorage.setItem(`hive_ai_consent_${id}`, aiChoice ? 'yes' : 'no')
            setConfirming(null)
            go(`#/test/${id}`)
          }}
        >
          {llm.on && <AiConsent checked={aiChoice} onChange={setAiChoice} model={llm.model} />}
        </ConfirmModal>
      )}

      <footer className="footer">
        HIVE · FastAPI · React · Mixpanel
        <button className="owner-link" onClick={() => go('#/analytics')} aria-label="Owner access">
          Owner access
        </button>
      </footer>
    </>
  )
}
