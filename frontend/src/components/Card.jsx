import { useRef, useState } from 'react'
import { trackCardClick } from '../lib/analytics.js'

export default function Card({ card, index, open, onToggle, onStart }) {
  const ref = useRef(null)
  const hoverStart = useRef(null)
  const [count, setCount] = useState(null)

  const handleClick = async (e) => {
    const action = open ? 'collapse' : 'expand'
    const native = e.nativeEvent
    const hoverMs = hoverStart.current ? Math.round(performance.now() - hoverStart.current) : null
    onToggle()
    if (action !== 'expand') return // only opening a card counts as a click
    const result = await trackCardClick(native, card, { action, index, hoverMs, element: ref.current })
    if (result) setCount(result.card_click_count)
  }

  const panelId = `card-panel-${card.id}`

  return (
    <article
      ref={ref}
      className={`card ${open ? 'open' : ''} ${card.available ? '' : 'unavailable'}`}
      onPointerEnter={() => (hoverStart.current = performance.now())}
      onPointerLeave={() => (hoverStart.current = null)}
    >
      <button className="card-head" onClick={handleClick} aria-expanded={open} aria-controls={panelId}>
        <span className="card-index">{String(index + 1).padStart(2, '0')}</span>
        <span className="card-tag">{card.available ? card.tag : 'Not offered'}</span>
        <h2 className="card-title">{card.title}</h2>
        <p className="card-summary">{card.summary}</p>
        <span className="card-toggle" aria-hidden="true">+</span>
      </button>

      <div id={panelId} className="card-body" role="region" aria-hidden={!open}>
        <div className="card-body-inner">
          {card.available ? (
            <>
              <p>{card.details}</p>
              <div className="card-stats">
                <div className="stat"><span className="stat-value">{card.question_count}</span><span className="stat-label">Questions</span></div>
                <div className="stat"><span className="stat-value">~{card.minutes}m</span><span className="stat-label">{card.format}</span></div>
              </div>
              {card.license && <p className="card-license">{card.license}</p>}
              <button className="btn start-btn" onClick={onStart} tabIndex={open ? 0 : -1}>Start test →</button>
            </>
          ) : (
            <>
              <p><strong className="why">Why Hive doesn't offer this test:</strong> {card.unavailable_reason}</p>
              {card.official_url && (
                <a className="text-link" href={card.official_url} target="_blank" rel="noreferrer" tabIndex={open ? 0 : -1}>
                  Learn more about this test ↗
                </a>
              )}
            </>
          )}
          {count !== null && (
            <p className="card-count">
              You've opened this card <strong>{count}</strong> {count === 1 ? 'time' : 'times'}
            </p>
          )}
        </div>
      </div>
    </article>
  )
}
