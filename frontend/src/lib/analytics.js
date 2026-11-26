import mixpanel from 'mixpanel-browser'
import { collectClickContext, initContext, recordApiRtt, superProperties } from './context.js'

const TOKEN = import.meta.env.VITE_MIXPANEL_TOKEN
const REPLAY_PERCENT = Number(import.meta.env.VITE_MIXPANEL_REPLAY_PERCENT ?? 100)
const API_HOST = import.meta.env.VITE_MIXPANEL_API_HOST // e.g. https://api-eu.mixpanel.com
export const API_URL = import.meta.env.VITE_API_URL || ''

let enabled = false

export function initAnalytics() {
  const ready = initContext()
  if (!TOKEN) {
    console.warn('[analytics] VITE_MIXPANEL_TOKEN not set — client-side Mixpanel disabled.')
    return
  }
  mixpanel.init(TOKEN, {
    persistence: 'localStorage',
    ip: true, // geolocate browser events from the request IP
    ...(API_HOST ? { api_host: API_HOST } : {}),

    // Autocapture: page views, clicks, dead/rage clicks, scroll depth, inputs, form submits, page leave
    autocapture: {
      pageview: 'full-url',
      click: true,
      dead_click: true,
      rage_click: true,
      input: true,
      submit: true,
      scroll: true,
      scroll_depth_percent_checkpoints: [10, 25, 50, 75, 90, 100],
      page_leave: true,
      capture_text_content: true,
    },

    // Session Replay + heatmaps (free plan includes a monthly replay quota)
    record_sessions_percent: REPLAY_PERCENT,
    record_heatmap_data: true,
    record_mask_inputs: true, // never record what people type
    record_console: true,
  })
  enabled = true

  // Super properties ride along on every browser-sent event (page views, autocapture, replay)
  ready.then(() => mixpanel.register(superProperties()))
}

/** Stable anonymous id shared by mixpanel-browser and the backend. */
export function getDistinctId() {
  if (enabled) return mixpanel.get_distinct_id()
  let id = localStorage.getItem('hive_distinct_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('hive_distinct_id', id)
  }
  return id
}

/**
 * Send a card click to the backend, which adds IP, location, ISP, user-agent
 * parsing and visitor history, then forwards it to Mixpanel server-side
 * (immune to ad blockers). Falls back to browser tracking if the API is down.
 */
export async function trackCardClick(event, card, meta) {
  const client = await collectClickContext(event, card, meta)
  const distinct_id = getDistinctId()
  if (enabled) {
    client.device_id = mixpanel.get_property('$device_id') || null
    client.replay_id = mixpanel.get_session_recording_properties?.()?.$mp_replay_id || null
  }

  const started = performance.now()
  try {
    const res = await fetch(`${API_URL}/api/track/card-click`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ distinct_id, card_id: card.id, action: meta.action, client }),
      keepalive: true,
    })
    recordApiRtt(performance.now() - started)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    console.warn('[analytics] backend tracking failed, using client fallback', err)
    if (enabled) {
      mixpanel.track('Card Clicked', {
        card_id: card.id,
        card_title: card.title,
        card_tag: card.tag,
        action: meta.action,
        tracked_via: 'browser_fallback',
        ...client,
      })
      mixpanel.people.increment({ 'Total Card Clicks': 1, [`Clicks: ${card.title}`]: 1 })
    }
    return null
  }
}
