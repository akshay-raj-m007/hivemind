import { useState } from 'react'

const ord = (v) => {
  const n = Math.min(99, Math.max(1, Math.round(v)))
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'
  return [n, suffix]
}

function BigFive({ result }) {
  return (
    <div className="panel">
      <h3>Your Big Five profile</h3>
      <p className="muted small">Percentile vs. {result.norm_n.toLocaleString()} people in the Open Psychometrics sample. Shaded band = average range (30–70).</p>
      <ul className="pct-list">
        {result.traits.map((t) => (
          <li key={t.code} className="pct-row" title={`${t.name}: raw ${t.score}/50, ${t.percentile}th percentile (${t.level})`}>
            <span className="pct-label">{t.name}</span>
            <span className="pct-track">
              <span className="pct-band" />
              <span className="pct-fill" style={{ width: `${Math.max(t.percentile, 1.5)}%` }} />
            </span>
            <span className="pct-value">{ord(t.percentile)[0]}<small>{ord(t.percentile)[1]}</small></span>
          </li>
        ))}
      </ul>
      <div className="trait-defs">
        {result.traits.map((t) => (
          <p key={t.code}><strong>{t.name}</strong> <span className={`level ${t.level}`}>{t.level}</span> {t.definition}</p>
        ))}
      </div>
    </div>
  )
}

function Jungian({ result }) {
  return (
    <div className="panel">
      <h3>Your type</h3>
      <div className="type-code">
        {result.type.split('').map((l, i) => <span key={i}>{l}</span>)}
      </div>
      <ul className="dim-list">
        {result.dimensions.map((d) => {
          const pos = ((d.toward_b - 8) / 32) * 100
          return (
            <li key={d.code} title={`${d.names[d.poles[0]]} ↔ ${d.names[d.poles[1]]}: ${d.strength}`}>
              <span className={`dim-pole ${d.chosen === d.poles[0] ? 'on' : ''}`}>{d.names[d.poles[0]]}</span>
              <span className="dim-track">
                <span className="dim-mid" />
                <span className="dim-marker" style={{ left: `${pos}%` }} />
              </span>
              <span className={`dim-pole right ${d.chosen === d.poles[1] ? 'on' : ''}`}>{d.names[d.poles[1]]}</span>
              <span className="dim-strength">{d.strength}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Rmet({ result }) {
  const gp = result.norms[0]
  const x = (v) => `${(v / 36) * 100}%`
  return (
    <div className="panel">
      <h3>Your score</h3>
      <p className="big-score">{result.score}<small> / 36</small></p>
      <div className="numline" title={`Typical range ${(gp.mean - gp.sd).toFixed(1)}–${(gp.mean + gp.sd).toFixed(1)}`}>
        <span className="numline-band" style={{ left: x(gp.mean - gp.sd), width: x(2 * gp.sd) }} />
        <span className="numline-mean" style={{ left: x(gp.mean) }} />
        <span className="numline-you" style={{ left: x(result.score) }}><em>You</em></span>
      </div>
      <div className="numline-axis"><span>0</span><span>18</span><span>36</span></div>
      <p className="muted small">
        Shaded: general-population adults ±1 SD (mean {gp.mean}, n={gp.n}; Baron-Cohen et al., 2001). Your score is {result.band}.
      </p>
    </div>
  )
}

function Rorschach({ result }) {
  return (
    <div className="panel">
      <h3>Card by card</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Card</th><th>You saw</th><th>Popular?</th><th>Published popular responses</th><th>What the literature says about this card</th></tr>
          </thead>
          <tbody>
            {result.cards.map((c) => (
              <tr key={c.id}>
                <td>{c.card}</td>
                <td className="wrap">{c.answer}</td>
                <td>{c.matched.length ? <span className="level higher">yes{c.how === 'spelling' ? ' (spelling)' : ''}</span> : <span className="level lower">no</span>}</td>
                <td className="wrap muted">{c.popular.join(' · ') || 'none listed'}</td>
                <td className="wrap muted">{c.card_note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PercentileBars({ title, note, rows }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <p className="muted small">{note}</p>
      <ul className="pct-list">
        {rows.map((t) => (
          <li key={t.key} className="pct-row" title={t.tip}>
            <span className="pct-label">{t.label}</span>
            <span className="pct-track">
              <span className="pct-band" />
              <span className="pct-fill" style={{ width: `${Math.max(t.percentile, 1.5)}%` }} />
            </span>
            <span className="pct-value">{ord(t.percentile)[0]}<small>{ord(t.percentile)[1]}</small></span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Riasec({ result }) {
  const order = ['R', 'I', 'A', 'S', 'E', 'C']
  const areas = order.map((c) => result.areas.find((a) => a.code === c))
  return (
    <>
      <div className="panel">
        <h3>Your Holland code</h3>
        <div className="type-code">{result.code.split('').map((l, i) => <span key={i}>{l}</span>)}</div>
      </div>
      <PercentileBars
        title="Interest areas"
        note={`Percentile vs. ${result.norm_n.toLocaleString()} people in the Open Psychometrics sample. Shaded band = average range (30–70).`}
        rows={areas.map((a) => ({ key: a.code, label: a.name, percentile: a.percentile, tip: `${a.name}: ${a.score}/40 (${a.level})` }))}
      />
    </>
  )
}

function SelfEsteem({ result }) {
  const x = (v) => `${(v / 30) * 100}%`
  const { mean, sd } = result.norm
  return (
    <div className="panel">
      <h3>Your score</h3>
      <p className="big-score">{result.score}<small> / 30</small></p>
      <div className="numline" title={`Sample mean ${mean} (SD ${sd})`}>
        <span className="numline-band" style={{ left: x(Math.max(0, mean - sd)), width: x(Math.min(30, mean + sd) - Math.max(0, mean - sd)) }} />
        <span className="numline-mean" style={{ left: x(mean) }} />
        <span className="numline-you" style={{ left: x(result.score) }}><em>You</em></span>
      </div>
      <div className="numline-axis"><span>0</span><span>15</span><span>30</span></div>
      <p className="muted small">
        Shaded: the middle of the Open Psychometrics sample (mean {mean} ± 1 SD, n={result.norm.n.toLocaleString()}). You scored higher than about {Math.round(result.percentile)}% of them.
      </p>
    </div>
  )
}

function Attachment({ result }) {
  const { anxiety, avoidance } = result.dimensions
  return (
    <>
      <div className="panel">
        <h3>Your position on the two attachment dimensions</h3>
        <div className="quad">
          <span className="quad-axis-y">Anxiety →</span>
          <div className="quad-plot" title={`Anxiety ${Math.round(anxiety.percentile)}th, avoidance ${Math.round(avoidance.percentile)}th percentile`}>
            <span className="quad-mid-x" />
            <span className="quad-mid-y" />
            <span className={`quad-label tl ${result.style === 'anxious-preoccupied' ? 'on' : ''}`}>anxious-preoccupied</span>
            <span className={`quad-label tr ${result.style === 'fearful-avoidant' ? 'on' : ''}`}>fearful-avoidant</span>
            <span className={`quad-label bl ${result.style === 'secure' ? 'on' : ''}`}>secure</span>
            <span className={`quad-label br ${result.style === 'dismissive-avoidant' ? 'on' : ''}`}>dismissive-avoidant</span>
            <span className="quad-you" style={{ left: `${avoidance.percentile}%`, bottom: `${anxiety.percentile}%` }}><em>You</em></span>
          </div>
          <span className="quad-axis-x">Avoidance →</span>
        </div>
        <p className="muted small">Axes are percentiles vs. {result.norm_n.toLocaleString()} people; the cross marks the sample median. Your region: <strong>{result.style.replace('-', ' ')}</strong> ({result.style_strength === 'clearly' ? 'both scores are in the outer ranges' : 'a tendency, as at least one score is in the average range'}). Regions follow the four clusters of Brennan, Clark and Shaver, which correspond to Bartholomew's four styles.</p>
      </div>
      <PercentileBars
        title="Dimension scores"
        note="Shaded band = average range (30–70th percentile)."
        rows={[
          { key: 'anx', label: 'Anxiety', percentile: anxiety.percentile, tip: `${anxiety.score}/90 (${anxiety.level})` },
          { key: 'avo', label: 'Avoidance', percentile: avoidance.percentile, tip: `${avoidance.score}/90 (${avoidance.level})` },
        ]}
      />
    </>
  )
}

export default function ResultView({ data, onExit, onRetake }) {
  const [showFacts, setShowFacts] = useState(false)
  const r = data.result
  return (
    <main className="container result">
      <button className="back-link" onClick={onExit}>← All tests</button>
      <p className="eyebrow">{data.title}</p>
      <h1 className="test-title">{r.headline}</h1>

      {data.tagline && <p className="tagline">{data.tagline}</p>}

      {(data.greeting || data.visit_stats?.length > 0) && (
        <section className="greeting">
          {data.greeting && <p className="greeting-text">{data.greeting}</p>}
          {data.visit_stats?.length > 0 && (
            <div className="stat-chips">
              {data.visit_stats.map((st) => (
                <span key={st.label} className="stat-chip"><small>{st.label}</small>{st.value}</span>
              ))}
            </div>
          )}
          <span className="story-source">
            {data.ai_greeting ? `Greeting written by ${data.paragraph_model} from your visit analytics` : 'From your visit analytics'}
          </span>
        </section>
      )}

      {data.test_id === 'big-five' && <BigFive result={r} />}
      {data.test_id === 'jungian-type' && <Jungian result={r} />}
      {data.test_id === 'rmet' && <Rmet result={r} />}
      {data.test_id === 'rorschach' && <Rorschach result={r} />}
      {data.test_id === 'riasec' && <Riasec result={r} />}
      {data.test_id === 'self-esteem' && <SelfEsteem result={r} />}
      {data.test_id === 'attachment' && <Attachment result={r} />}

      <h2 className="story-title">{data.story_title}</h2>
      <section className="sections">
        {data.sections.map((sec) => (
          <article key={sec.heading} className={`section-card icon-${sec.icon}`}>
            <h3><span className="section-mark" aria-hidden="true" />{sec.heading}</h3>
            {sec.body && <p>{sec.body}</p>}
            {sec.bullets.length > 0 && <ul className="section-bullets">{sec.bullets.map((b) => <li key={b}>{b}</li>)}</ul>}
            {sec.quotes.length > 0 && (
              <div className="section-quotes">
                {sec.quotes.map((q) => (
                  <blockquote key={q.text}>
                    {q.text}
                    <cite><a href={q.url} target="_blank" rel="noreferrer">{q.source}</a></cite>
                  </blockquote>
                ))}
              </div>
            )}
          </article>
        ))}
      </section>
      <p className="story-source standalone">
        {data.paragraph_source === 'llm'
          ? `Conclusions written by Hive from verified data and research quotes · wording polished by ${data.paragraph_model} (${data.polished_paragraphs} of ${data.polish_targets} paragraphs passed the accuracy check; quotes and numbers are never changed)`
          : data.ai_requested
            ? 'Conclusions written by Hive from verified data and research quotes · AI was requested but unavailable, so this is the original wording'
            : 'Conclusions written by Hive from verified data and research quotes (no AI, nothing sent outside Hive)'}
      </p>

      <div className="panel">
        <button className="facts-toggle" onClick={() => setShowFacts((s) => !s)} aria-expanded={showFacts}>
          {showFacts ? '−' : '+'} What this result is based on
        </button>
        {showFacts && (
          <div className="facts">
            {data.context_facts.length > 0 && (
              <>
                <h4>About your visit (from analytics)</h4>
                <ul>{data.context_facts.map((f) => <li key={f}>{f}</li>)}</ul>
              </>
            )}
            <h4>Scored facts</h4>
            <ul>{r.facts.map((f) => <li key={f}>{f}</li>)}</ul>
            {r.notes?.length > 0 && (
              <>
                <h4>Notes</h4>
                <ul>{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              </>
            )}
          </div>
        )}
      </div>

      {data.sources?.length > 0 && (
        <div className="panel sources">
          <h3>Sources</h3>
          <ul>
            {data.sources.map((s) => (
              <li key={s.cite}>
                <span className="muted">{s.what}:</span> {s.cite}{' '}
                {s.url && <a className="text-link" href={s.url} target="_blank" rel="noreferrer">link ↗</a>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="fineprint">
        For education and self-reflection only. This is not a clinical assessment or diagnosis. If something here worries
        you, talk to a qualified professional.
      </p>

      <div className="runner-nav">
        <button className="btn ghost" onClick={onRetake}>Retake</button>
        <button className="btn" onClick={onExit}>Take another test</button>
      </div>
    </main>
  )
}
