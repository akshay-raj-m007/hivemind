import { Fragment, useCallback, useEffect, useState } from 'react'
import { API_URL } from '../lib/analytics.js'

const fmt = new Intl.NumberFormat()

function BarList({ rows, labelKey, valueKey, subKey, subLabel }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(1, ...rows.map((r) => r[valueKey]))
  if (!rows.length) return <p className="muted">No data yet.</p>
  return (
    <ul className="barlist">
      {rows.map((r, i) => (
        <li
          key={r[labelKey]}
          className="bar-row"
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)}
          tabIndex={0}
          onFocus={() => setHover(i)}
          onBlur={() => setHover(null)}
        >
          <span className="bar-label">{r[labelKey]}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(r[valueKey] / max) * 100}%` }} />
            <span className="bar-value">{fmt.format(r[valueKey])}</span>
          </span>
          {hover === i && (
            <span className="tooltip" role="tooltip">
              <strong>{r[labelKey]}</strong>
              <span>{fmt.format(r[valueKey])} clicks</span>
              {subKey && <span>{fmt.format(r[subKey])} {subLabel}</span>}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function location(c) {
  return [c.city, c.properties?.region, c.country].filter(Boolean).join(', ') || '—'
}

function network(p) {
  const parts = []
  if (p.network_effective_type) parts.push(p.network_effective_type.toUpperCase())
  if (p.network_downlink_mbps != null) parts.push(`${p.network_downlink_mbps} Mbps`)
  if (p.network_rtt_ms != null) parts.push(`${p.network_rtt_ms}ms RTT`)
  return parts.join(' · ') || 'n/a'
}

export default function AnalyticsDashboard() {
  const [key, setKey] = useState(() => sessionStorage.getItem('hive_admin_key') || '')
  const [input, setInput] = useState('')
  const [summary, setSummary] = useState(null)
  const [recent, setRecent] = useState([])
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(async () => {
    if (!key) return
    try {
      const headers = { 'X-Admin-Key': key }
      const [s, r] = await Promise.all([
        fetch(`${API_URL}/api/analytics/summary`, { headers }),
        fetch(`${API_URL}/api/analytics/recent?limit=50`, { headers }),
      ])
      if (s.status === 401) {
        sessionStorage.removeItem('hive_admin_key')
        setKey('')
        setError('That passkey is not valid.')
        return
      }
      setSummary(await s.json())
      setRecent(await r.json())
      setError(null)
    } catch {
      setError('Could not reach the API.')
    }
  }, [key])

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  if (!key) {
    return (
      <main className="container narrow">
        <form
          className="login"
          onSubmit={(e) => {
            e.preventDefault()
            sessionStorage.setItem('hive_admin_key', input)
            setKey(input)
          }}
        >
          <span className="modal-mark" aria-hidden="true" />
          <h2>Restricted area</h2>
          <p className="muted">Enter passkey for access.</p>
          {error && <div className="alert">{error}</div>}
          <input type="password" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Passkey"
                 autoComplete="current-password" autoFocus />
          <button className="btn" type="submit">Enter</button>
          <a className="text-link small" href="#/">← Back to the tests</a>
        </form>
      </main>
    )
  }

  return (
    <main className="container">
      <div className="dash-head">
        <div>
          <p className="eyebrow">Live · refreshes every 10s</p>
          <h1>Card analytics</h1>
        </div>
        <button className="btn ghost" onClick={() => { sessionStorage.removeItem('hive_admin_key'); setKey('') }}>Lock</button>
      </div>
      {error && <div className="alert">{error}</div>}

      {summary && (
        <>
          <section className="tiles">
            <div className="tile"><span className="tile-value">{fmt.format(summary.total_clicks)}</span><span className="tile-label">Total clicks</span></div>
            <div className="tile"><span className="tile-value">{fmt.format(summary.unique_users)}</span><span className="tile-label">Unique visitors</span></div>
            <div className="tile"><span className="tile-value">{fmt.format(summary.countries)}</span><span className="tile-label">Countries</span></div>
          </section>

          <section className="panels">
            <div className="panel">
              <h3>Clicks per card</h3>
              <BarList rows={summary.per_card} labelKey="card_title" valueKey="clicks" subKey="users" subLabel="unique visitors" />
            </div>
            <div className="panel">
              <h3>Clicks by country</h3>
              <BarList rows={summary.per_country} labelKey="country" valueKey="clicks" />
            </div>
          </section>
        </>
      )}

      <section className="panel">
        <h3>Recent clicks</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th><th>Visitor</th><th>Card</th><th>Action</th><th>IP address</th>
                <th>Location</th><th>ISP</th><th>Network</th><th className="num">Clicks on card</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((c) => (
                <Fragment key={c.id}>
                  <tr className="clickable" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
                    <td>{new Date(c.ts).toLocaleString()}</td>
                    <td className="mono" title={c.distinct_id}>{c.distinct_id.slice(-8)}</td>
                    <td>{c.card_title}</td>
                    <td>{c.action}</td>
                    <td className="mono">{c.ip || '—'}</td>
                    <td>{location(c)}</td>
                    <td>{c.isp || '—'}</td>
                    <td>{network(c.properties)}</td>
                    <td className="num">{c.properties.card_click_count ?? '—'}</td>
                  </tr>
                  {expanded === c.id && (
                    <tr className="detail-row">
                      <td colSpan={9}>
                        <dl className="kv">
                          {Object.entries(c.properties).map(([k, v]) => (
                            <Fragment key={k}><dt>{k}</dt><dd>{Array.isArray(v) ? v.join(', ') : String(v)}</dd></Fragment>
                          ))}
                        </dl>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {!recent.length && (
                <tr><td colSpan={9} className="muted">No clicks yet — go open some cards.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
