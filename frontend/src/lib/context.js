/**
 * Everything the browser can tell us for free, flattened into Mixpanel-friendly
 * key/value pairs. Static info is gathered once at startup (initContext);
 * per-click info is computed in collectClickContext().
 *
 * APIs marked (Chromium) only exist in Chrome / Edge / Opera / Android; other
 * browsers simply omit those keys.
 */

const LS = 'hive_'
const PAGE_LOADED_AT = performance.timeOrigin || Date.now()

const staticCtx = {}
const perfCtx = {}
const session = {
  clicks: 0,
  expands: 0,
  collapses: 0,
  uniqueCards: new Set(),
  lastClickAt: null,
  lastCardId: null,
  lastCardTitle: null,
  openedAt: {}, // card_id -> timestamp of expand
  recentClicks: {}, // card_id -> [timestamps]
  maxScrollPct: 0,
  tabHiddenCount: 0,
  hiddenMs: 0,
  hiddenSince: null,
  lastApiRttMs: null,
}

/* ---------------- helpers ---------------- */

const safe = (fn, fallback = null) => {
  try {
    const v = fn()
    return v === undefined ? fallback : v
  } catch {
    return fallback
  }
}
const ls = {
  get: (k) => safe(() => localStorage.getItem(LS + k)),
  set: (k, v) => safe(() => localStorage.setItem(LS + k, v)),
}
const ss = {
  get: (k) => safe(() => sessionStorage.getItem(LS + k)),
  set: (k, v) => safe(() => sessionStorage.setItem(LS + k, v)),
}
const mq = (q) => safe(() => matchMedia(q).matches, null)
const round = (n, d = 0) => (typeof n === 'number' && isFinite(n) ? Number(n.toFixed(d)) : null)
const partOfDay = (h) => (h < 5 ? 'night' : h < 12 ? 'morning' : h < 17 ? 'afternoon' : h < 21 ? 'evening' : 'night')
const domainOf = (url) => safe(() => (url ? new URL(url).hostname : null))

export function getSessionId() {
  let id = ss.get('session_id')
  if (!id) {
    id = crypto.randomUUID()
    ss.set('session_id', id)
    ss.set('session_started_at', String(Date.now()))
  }
  return id
}

export function recordApiRtt(ms) {
  session.lastApiRttMs = Math.round(ms)
}

/* ---------------- one-time collection ---------------- */

function collectVisit() {
  const now = Date.now()
  const isNewSession = !ss.get('session_id')
  getSessionId()

  let first = Number(ls.get('first_visit_at'))
  if (!first) {
    first = now
    ls.set('first_visit_at', String(now))
  }
  let visits = Number(ls.get('visit_count') || 0)
  const prevVisitAt = Number(ls.get('last_visit_at') || 0)
  if (isNewSession) {
    visits += 1
    ls.set('visit_count', String(visits))
    ls.set('last_visit_at', String(now))
  }
  const pageViews = Number(ss.get('page_views') || 0) + 1
  ss.set('page_views', String(pageViews))

  Object.assign(staticCtx, {
    first_visit_at: new Date(first).toISOString(),
    days_since_first_visit: round((now - first) / 86400000, 2),
    visit_count: visits,
    is_returning_visitor: visits > 1,
    days_since_previous_visit: isNewSession && prevVisitAt ? round((now - prevVisitAt) / 86400000, 2) : null,
    session_page_views: pageViews,
  })
}

function collectAttribution() {
  const params = new URLSearchParams(location.search)
  const keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id']
  const clickIds = ['gclid', 'fbclid', 'msclkid', 'ttclid', 'li_fat_id', 'twclid', 'dclid', 'ref']
  const current = {}
  for (const k of [...keys, ...clickIds]) if (params.get(k)) current[k] = params.get(k).slice(0, 200)

  const referrer = document.referrer || null
  const refDomain = domainOf(referrer)
  const touch = {
    referrer,
    referring_domain: refDomain,
    landing_page: location.href,
    ...current,
  }

  // first touch persists forever, last touch per session
  if (!ls.get('first_touch')) ls.set('first_touch', JSON.stringify({ ...touch, at: new Date().toISOString() }))
  const first = safe(() => JSON.parse(ls.get('first_touch')), {})

  let trafficSource = 'direct'
  if (current.gclid || current.msclkid || /cpc|ppc|paid/i.test(current.utm_medium || '')) trafficSource = 'paid'
  else if (current.utm_source) trafficSource = 'campaign'
  else if (refDomain && /google|bing|duckduckgo|yahoo|baidu|yandex|ecosia/i.test(refDomain)) trafficSource = 'organic_search'
  else if (refDomain && /facebook|instagram|t\.co|twitter|x\.com|linkedin|reddit|youtube|tiktok|pinterest|whatsapp/i.test(refDomain))
    trafficSource = 'social'
  else if (refDomain && refDomain !== location.hostname) trafficSource = 'referral'

  Object.assign(staticCtx, current, {
    referrer,
    referring_domain: refDomain,
    traffic_source: trafficSource,
    landing_page: ss.get('landing_page') || (ss.set('landing_page', location.href), location.href),
    first_touch_referrer: first.referrer || null,
    first_touch_referring_domain: first.referring_domain || null,
    first_touch_landing_page: first.landing_page || null,
    first_touch_utm_source: first.utm_source || null,
    first_touch_utm_medium: first.utm_medium || null,
    first_touch_utm_campaign: first.utm_campaign || null,
    first_touch_at: first.at || null,
  })
}

function collectDevice() {
  const n = navigator
  const s = screen
  Object.assign(staticCtx, {
    user_agent: n.userAgent,
    platform: n.userAgentData?.platform || n.platform || null,
    vendor: n.vendor || null,
    is_mobile_hint: n.userAgentData?.mobile ?? null,
    language: n.language,
    languages: n.languages ? [...n.languages].slice(0, 5) : null,
    timezone: safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
    utc_offset_min: -new Date().getTimezoneOffset(),
    locale: safe(() => Intl.DateTimeFormat().resolvedOptions().locale),
    calendar: safe(() => Intl.DateTimeFormat().resolvedOptions().calendar),
    number_format_sample: safe(() => (1234567.89).toLocaleString()),
    screen: `${s.width}x${s.height}`,
    screen_width: s.width,
    screen_height: s.height,
    screen_avail: `${s.availWidth}x${s.availHeight}`,
    color_depth: s.colorDepth,
    pixel_ratio: devicePixelRatio,
    orientation: safe(() => s.orientation.type),
    cpu_cores: n.hardwareConcurrency ?? null,
    device_memory_gb: n.deviceMemory ?? null, // (Chromium)
    max_touch_points: n.maxTouchPoints ?? 0,
    touch_support: 'ontouchstart' in window || n.maxTouchPoints > 0,
    primary_pointer: mq('(pointer: coarse)') ? 'coarse' : mq('(pointer: fine)') ? 'fine' : 'none',
    can_hover: mq('(hover: hover)'),
    cookies_enabled: n.cookieEnabled,
    pdf_viewer: n.pdfViewerEnabled ?? null,
    webdriver: n.webdriver === true, // true for Selenium/Puppeteer/Playwright
    browser_dnt: n.doNotTrack === '1' || window.doNotTrack === '1',
    browser_gpc: n.globalPrivacyControl === true,
    is_pwa_standalone: mq('(display-mode: standalone)'),
    is_in_iframe: safe(() => window.self !== window.top, true),
    color_scheme: mq('(prefers-color-scheme: dark)') ? 'dark' : 'light',
    reduced_motion: mq('(prefers-reduced-motion: reduce)'),
    reduced_data: mq('(prefers-reduced-data: reduce)'),
    prefers_contrast: mq('(prefers-contrast: more)') ? 'more' : mq('(prefers-contrast: less)') ? 'less' : 'no-preference',
    forced_colors: mq('(forced-colors: active)'),
    color_gamut: mq('(color-gamut: rec2020)') ? 'rec2020' : mq('(color-gamut: p3)') ? 'p3' : 'srgb',
    hdr_display: mq('(dynamic-range: high)'),
    webgl_supported: !!safe(() => document.createElement('canvas').getContext('webgl')),
    webgpu_supported: 'gpu' in n,
    service_worker_supported: 'serviceWorker' in n,
    web_share_supported: 'share' in n,
    bluetooth_supported: 'bluetooth' in n,
    js_heap_limit_mb: round(performance.memory?.jsHeapSizeLimit / 1048576), // (Chromium)
  })

  // GPU model via WebGL
  safe(() => {
    const gl = document.createElement('canvas').getContext('webgl')
    const ext = gl?.getExtension('WEBGL_debug_renderer_info')
    if (ext) {
      staticCtx.gpu_vendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL)
      staticCtx.gpu_renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
    }
  })
}

async function collectAsync() {
  const n = navigator
  const tasks = []

  // Detailed OS / device model (Chromium User-Agent Client Hints)
  if (n.userAgentData?.getHighEntropyValues) {
    tasks.push(
      n.userAgentData
        .getHighEntropyValues(['platformVersion', 'architecture', 'bitness', 'model', 'fullVersionList', 'wow64', 'formFactors'])
        .then((h) => {
          Object.assign(staticCtx, {
            ch_platform_version: h.platformVersion || null,
            ch_architecture: h.architecture || null,
            ch_bitness: h.bitness || null,
            ch_model: h.model || null,
            ch_wow64: h.wow64 ?? null,
            ch_form_factors: h.formFactors?.length ? h.formFactors : null,
            ch_browser_versions: h.fullVersionList?.map((b) => `${b.brand} ${b.version}`).filter((b) => !/Not.?A.?Brand/i.test(b)),
          })
          // Windows 11 reports platformVersion >= 13
          if (h.platform === 'Windows' && h.platformVersion)
            staticCtx.ch_windows_version = Number(h.platformVersion.split('.')[0]) >= 13 ? 'Windows 11' : 'Windows 10 or older'
        })
        .catch(() => {}),
    )
  }

  // Storage quota (very low quota often means private/incognito mode)
  if (n.storage?.estimate) {
    tasks.push(
      n.storage.estimate().then((e) => {
        staticCtx.storage_quota_mb = round(e.quota / 1048576)
        staticCtx.storage_used_kb = round(e.usage / 1024)
      }).catch(() => {}),
    )
  }
  if (n.storage?.persisted) tasks.push(n.storage.persisted().then((p) => (staticCtx.storage_persisted = p)).catch(() => {}))

  // Ad blocker detection via a bait element
  tasks.push(
    new Promise((resolve) => {
      const bait = document.createElement('div')
      bait.className = 'adsbox ad-banner ad-placement pub_300x250 textads'
      bait.style.cssText = 'position:absolute;left:-9999px;width:1px;height:1px;'
      document.body.appendChild(bait)
      setTimeout(() => {
        const cs = getComputedStyle(bait)
        staticCtx.ad_blocker_detected = bait.offsetHeight === 0 || cs.display === 'none' || cs.visibility === 'hidden'
        bait.remove()
        resolve()
      }, 100)
    }),
  )

  await Promise.allSettled(tasks)
}

function collectPerformance() {
  const nav = performance.getEntriesByType('navigation')[0]
  if (nav) {
    Object.assign(perfCtx, {
      perf_navigation_type: nav.type, // navigate | reload | back_forward | prerender
      perf_protocol: nav.nextHopProtocol || null, // h2, h3, http/1.1
      perf_dns_ms: round(nav.domainLookupEnd - nav.domainLookupStart),
      perf_tcp_ms: round(nav.connectEnd - nav.connectStart),
      perf_tls_ms: nav.secureConnectionStart > 0 ? round(nav.connectEnd - nav.secureConnectionStart) : null,
      perf_ttfb_ms: round(nav.responseStart - nav.requestStart),
      perf_dom_interactive_ms: round(nav.domInteractive),
      perf_dom_content_loaded_ms: round(nav.domContentLoadedEventEnd),
      perf_page_load_ms: nav.loadEventEnd > 0 ? round(nav.loadEventEnd) : null,
      perf_transfer_kb: round(nav.transferSize / 1024, 1),
      perf_served_from_cache: nav.transferSize === 0 && nav.decodedBodySize > 0,
    })
  }
  const fcp = performance.getEntriesByName('first-contentful-paint')[0]
  if (fcp) perfCtx.perf_fcp_ms = round(fcp.startTime)
}

function observeVitals() {
  safe(() => {
    new PerformanceObserver((list) => {
      const last = list.getEntries().at(-1)
      if (last) perfCtx.perf_lcp_ms = round(last.startTime)
    }).observe({ type: 'largest-contentful-paint', buffered: true })
  })
  safe(() => {
    let cls = 0
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) if (!e.hadRecentInput) cls += e.value
      perfCtx.perf_cls = round(cls, 4)
    }).observe({ type: 'layout-shift', buffered: true })
  })
  safe(() => {
    let worst = 0
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) worst = Math.max(worst, e.duration)
      perfCtx.perf_worst_interaction_ms = round(worst)
    }).observe({ type: 'event', buffered: true, durationThreshold: 16 })
  })
}

function observeSession() {
  const onScroll = () => {
    const max = document.documentElement.scrollHeight - innerHeight
    const pct = max > 0 ? Math.round((scrollY / max) * 100) : 100
    if (pct > session.maxScrollPct) session.maxScrollPct = pct
  }
  addEventListener('scroll', onScroll, { passive: true })
  onScroll()
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      session.tabHiddenCount += 1
      session.hiddenSince = Date.now()
    } else if (session.hiddenSince) {
      session.hiddenMs += Date.now() - session.hiddenSince
      session.hiddenSince = null
    }
  })
}

let ready = null
export function initContext() {
  if (ready) return ready
  collectVisit()
  collectAttribution()
  collectDevice()
  observeVitals()
  observeSession()
  if (document.readyState === 'complete') collectPerformance()
  else addEventListener('load', () => setTimeout(collectPerformance, 0), { once: true })
  ready = collectAsync()
  return ready
}

/** Super properties for mixpanel-browser (attached to page views / autocapture too). */
export function superProperties() {
  const keys = [
    'visit_count', 'is_returning_visitor', 'traffic_source', 'timezone', 'language', 'screen',
    'pixel_ratio', 'color_scheme', 'cpu_cores', 'device_memory_gb', 'gpu_renderer', 'ad_blocker_detected',
    'ch_model', 'ch_platform_version', 'first_touch_referring_domain', 'first_touch_utm_source',
  ]
  return Object.fromEntries(keys.filter((k) => staticCtx[k] != null).map((k) => [k, staticCtx[k]]))
}

/* ---------------- per-click collection ---------------- */

async function batteryInfo() {
  if (!navigator.getBattery) return {} // (Chromium)
  try {
    const b = await navigator.getBattery()
    return {
      battery_level_pct: Math.round(b.level * 100),
      battery_charging: b.charging,
    }
  } catch {
    return {}
  }
}

function networkInfo() {
  const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection // (Chromium)
  return {
    online: navigator.onLine,
    network_effective_type: c?.effectiveType ?? null,
    network_type: c?.type ?? null,
    network_downlink_mbps: c?.downlink ?? null,
    network_downlink_max_mbps: c?.downlinkMax ?? null,
    network_rtt_ms: c?.rtt ?? null,
    network_save_data: c?.saveData ?? null,
  }
}

/**
 * @param {MouseEvent|PointerEvent} e   the click event
 * @param {object} card                 card data
 * @param {object} meta                 { action, index, hoverMs, element }
 */
export async function collectClickContext(e, card, { action, index, hoverMs, element }) {
  await ready
  const now = Date.now()

  // rage / double click detection on the same card
  const recent = (session.recentClicks[card.id] || []).filter((t) => now - t < 2000)
  recent.push(now)
  session.recentClicks[card.id] = recent
  const sinceLastSameCard = recent.length > 1 ? now - recent.at(-2) : null

  // how long the card stayed open (on collapse)
  let openDurationMs = null
  if (action === 'expand') session.openedAt[card.id] = now
  else if (session.openedAt[card.id]) {
    openDurationMs = now - session.openedAt[card.id]
    delete session.openedAt[card.id]
  }

  const previousCardId = session.lastCardId
  const previousCardTitle = session.lastCardTitle
  const sinceLastClick = session.lastClickAt ? now - session.lastClickAt : null
  const isFirstTimeThisSession = !session.uniqueCards.has(card.id)

  session.clicks += 1
  session[action === 'expand' ? 'expands' : 'collapses'] += 1
  session.uniqueCards.add(card.id)
  session.lastClickAt = now
  session.lastCardId = card.id
  session.lastCardTitle = card.title

  // click geometry
  const rect = element?.getBoundingClientRect()
  const target = e?.target
  const viewportPct = rect
    ? round((Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0)) / rect.height) * 100)
    : null
  const keyboard = e?.detail === 0 // activated with Enter/Space

  const local = new Date(now)
  const sessionStart = Number(ss.get('session_started_at') || PAGE_LOADED_AT)
  const hiddenMs = session.hiddenMs + (session.hiddenSince ? now - session.hiddenSince : 0)

  return {
    ...staticCtx,
    ...perfCtx,
    ...networkInfo(),
    ...(await batteryInfo()),

    click_id: crypto.randomUUID(),
    session_id: getSessionId(),
    page_url: location.href,
    page_path: location.pathname + location.hash,
    page_title: document.title,

    // card
    card_position: index + 1,
    card_was_open_ms: openDurationMs,
    hover_before_click_ms: hoverMs,
    card_visible_pct: viewportPct,
    card_top_px: rect ? round(rect.top) : null,

    // click mechanics
    input_method: keyboard ? 'keyboard' : e?.pointerType || (staticCtx.primary_pointer === 'coarse' ? 'touch' : 'mouse'),
    click_x: keyboard ? null : round(e?.clientX),
    click_y: keyboard ? null : round(e?.clientY),
    click_page_x: keyboard ? null : round(e?.pageX),
    click_page_y: keyboard ? null : round(e?.pageY),
    click_x_in_card_pct: rect && !keyboard ? round(((e.clientX - rect.left) / rect.width) * 100) : null,
    click_y_in_card_pct: rect && !keyboard ? round(((e.clientY - rect.top) / rect.height) * 100) : null,
    click_target: target ? `${target.tagName.toLowerCase()}${target.className ? '.' + String(target.className).split(' ')[0] : ''}` : null,
    mouse_button: e?.button ?? null,
    alt_key: e?.altKey ?? null,
    ctrl_key: e?.ctrlKey ?? null,
    shift_key: e?.shiftKey ?? null,
    meta_key: e?.metaKey ?? null,
    is_trusted_event: e?.isTrusted ?? null,
    is_double_click: sinceLastSameCard !== null && sinceLastSameCard < 400,
    is_rage_click: recent.length >= 3,
    rapid_clicks_on_card_2s: recent.length,

    // session journey
    session_click_number: session.clicks,
    session_expands: session.expands,
    session_collapses: session.collapses,
    session_unique_cards: session.uniqueCards.size,
    is_first_click_on_card_this_session: isFirstTimeThisSession,
    previous_card_id: previousCardId,
    previous_card_title: previousCardTitle,
    ms_since_previous_click: sinceLastClick,
    ms_since_page_load: Math.round(now - PAGE_LOADED_AT),
    session_duration_sec: Math.round((now - sessionStart) / 1000),
    max_scroll_depth_pct: session.maxScrollPct,
    scroll_y_px: Math.round(scrollY),
    page_height_px: document.documentElement.scrollHeight,
    viewport: `${innerWidth}x${innerHeight}`,
    viewport_width: innerWidth,
    viewport_height: innerHeight,
    tab_hidden_count: session.tabHiddenCount,
    tab_hidden_sec: Math.round(hiddenMs / 1000),
    tab_has_focus: document.hasFocus(),
    last_api_rtt_ms: session.lastApiRttMs,
    js_heap_used_mb: round(performance.memory?.usedJSHeapSize / 1048576, 1), // (Chromium)

    // local time
    local_time: local.toString().slice(0, 24),
    local_hour: local.getHours(),
    local_day_of_week: local.toLocaleDateString('en-US', { weekday: 'long' }),
    is_weekend: [0, 6].includes(local.getDay()),
    part_of_day: partOfDay(local.getHours()),
  }
}
