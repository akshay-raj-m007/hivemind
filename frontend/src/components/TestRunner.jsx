import { useEffect, useMemo, useRef, useState } from 'react'
import { API_URL, getDistinctId } from '../lib/analytics.js'
import ResultView from './ResultView.jsx'

const BIPOLAR_LABELS = ['Fully left', 'Mostly left', 'Mix of both', 'Mostly right', 'Fully right']

export default function TestRunner({ testId, aiConsent, onExit }) {
  const [test, setTest] = useState(null)
  const [error, setError] = useState(null)
  const [stage, setStage] = useState('intro') // intro | questions | submitting | result
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)
  const advanceTimer = useRef(null)
  const startedAt = useRef(null)

  useEffect(() => {
    fetch(`${API_URL}/api/tests/${testId}`)
      .then(async (r) => (r.ok ? r.json() : Promise.reject(new Error((await r.json()).detail || `HTTP ${r.status}`))))
      .then(setTest)
      .catch((e) => setError(e.message))
    return () => clearTimeout(advanceTimer.current)
  }, [testId])

  const items = test?.items || []
  const item = items[index]
  const scored = useMemo(() => items.filter((i) => !i.practice), [items])
  const answeredCount = scored.filter((i) => answers[i.id] !== undefined && answers[i.id] !== '').length
  const isLast = index === items.length - 1

  const setAnswer = (value, autoAdvance) => {
    setAnswers((a) => ({ ...a, [item.id]: value }))
    if (autoAdvance && !isLast) {
      clearTimeout(advanceTimer.current)
      advanceTimer.current = setTimeout(() => setIndex((i) => Math.min(i + 1, items.length - 1)), 220)
    }
  }

  const submit = async () => {
    setStage('submitting')
    const payload = Object.fromEntries(scored.map((i) => [i.id, typeof answers[i.id] === 'string' ? answers[i.id].trim() : answers[i.id]]))
    try {
      const r = await fetch(`${API_URL}/api/tests/${testId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          distinct_id: getDistinctId(),
          answers: payload,
          use_ai: Boolean(aiConsent),
          meta: startedAt.current
            ? { duration_sec: Math.round((Date.now() - startedAt.current) / 1000), question_count: scored.length }
            : {},
        }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
      setResult(data)
      setStage('result')
      scrollTo({ top: 0 })
    } catch (e) {
      setError(e.message)
      setStage('questions')
    }
  }

  if (error && !test) {
    return (
      <main className="container narrow">
        <div className="alert">{error}</div>
        <button className="btn ghost" onClick={onExit}>← Back to tests</button>
      </main>
    )
  }
  if (!test) return <main className="container narrow"><p className="muted">Loading…</p></main>

  if (stage === 'result') {
    return <ResultView data={result} onExit={onExit} onRetake={() => { setAnswers({}); setIndex(0); setStage('intro') }} />
  }

  if (stage === 'submitting') {
    return (
      <main className="container narrow center">
        <div className="loader" aria-hidden="true" />
        <h2>Scoring your answers…</h2>
        <p className="muted">
          Matching your responses against the published data{aiConsent ? ', then asking the AI to word your result' : ''}.
        </p>
      </main>
    )
  }

  if (stage === 'intro') {
    return (
      <main className="container narrow">
        <button className="back-link" onClick={onExit}>← All tests</button>
        <p className="eyebrow">{test.card.tag}</p>
        <h1 className="test-title">{test.card.title}</h1>
        <p className="lede">{test.instructions}</p>
        {test.glossary_url && (
          <p className="muted small">
            Unsure what a word means? The official{' '}
            <a className="text-link" href={test.glossary_url} target="_blank" rel="noreferrer">word definitions handout ↗</a>{' '}
            may be consulted at any time.
          </p>
        )}
        {items.some((i) => i.practice) && <p className="muted small">The first photo is a practice item and is not scored.</p>}
        <button className="btn" onClick={() => { startedAt.current = Date.now(); setStage('questions') }}>Begin · {scored.length} questions</button>
      </main>
    )
  }

  const value = answers[item.id]
  const canNext = test.type === 'image_text' ? Boolean(value && value.trim()) : value !== undefined
  const progress = Math.round((answeredCount / scored.length) * 100)

  return (
    <main className="container runner">
      <div className="runner-top">
        <button className="back-link" onClick={onExit}>✕ Exit</button>
        <span className="muted small">{test.card.title}</span>
        <span className="muted small">
          {item.practice ? 'Practice' : `${scored.indexOf(item) + 1} / ${scored.length}`}
        </span>
      </div>
      <div className="progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${progress}%` }} />
      </div>

      <section className="question" key={item.id}>
        {test.type === 'likert' && (
          <>
            <p className="q-text">{item.text}</p>
            <div className="likert">
              {test.scale.map((s) => (
                <button key={s.value} className={`opt ${value === s.value ? 'selected' : ''}`} onClick={() => setAnswer(s.value, true)}>
                  {s.label}
                </button>
              ))}
            </div>
          </>
        )}

        {test.type === 'bipolar' && (
          <div className="bipolar">
            <span className="pole left">{item.left}</span>
            <div className="dots" role="radiogroup" aria-label={`${item.left} to ${item.right}`}>
              {[1, 2, 3, 4, 5].map((v) => (
                <button
                  key={v}
                  role="radio"
                  aria-checked={value === v}
                  aria-label={BIPOLAR_LABELS[v - 1]}
                  className={`dot d${v} ${value === v ? 'selected' : ''}`}
                  onClick={() => setAnswer(v, true)}
                />
              ))}
            </div>
            <span className="pole right">{item.right}</span>
          </div>
        )}

        {test.type === 'image_choice' && (
          <div className="eyes">
            <div className="eyes-grid">
              {item.options.slice(0, 2).map((o) => (
                <button key={o} className={`opt word ${value === o ? 'selected' : ''}`} onClick={() => setAnswer(o, true)}>{o}</button>
              ))}
              <img className="eyes-img" src={item.image} alt={`Eyes, photo ${item.practice ? 'practice' : scored.indexOf(item) + 1}`} />
              {item.options.slice(2).map((o) => (
                <button key={o} className={`opt word ${value === o ? 'selected' : ''}`} onClick={() => setAnswer(o, true)}>{o}</button>
              ))}
            </div>
          </div>
        )}

        {test.type === 'image_text' && (
          <div className="inkblot">
            <p className="eyebrow">{item.label}</p>
            <img className="inkblot-img" src={item.image} alt={`Rorschach inkblot ${item.label}`} />
            <label className="sr-only" htmlFor="blot-answer">What might this be?</label>
            <textarea
              id="blot-answer"
              rows={3}
              maxLength={500}
              placeholder="What might this be? Describe what you see…"
              value={value || ''}
              onChange={(e) => setAnswer(e.target.value, false)}
              autoFocus
            />
          </div>
        )}
      </section>

      {error && <div className="alert">{error}</div>}

      <div className="runner-nav">
        <button className="btn ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}>← Back</button>
        {isLast ? (
          <button className="btn" disabled={!canNext || answeredCount < scored.length} onClick={submit}>
            See my result
          </button>
        ) : (
          <button className="btn" disabled={!canNext} onClick={() => setIndex(index + 1)}>Next →</button>
        )}
      </div>
    </main>
  )
}
