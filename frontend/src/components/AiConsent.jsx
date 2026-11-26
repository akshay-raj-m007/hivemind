// Opt-in consent for AI. Sent: the result sections (portrait.py) for rewording, and descriptive
// visit facts (visitor.greeting_facts) for the greeting. Counts/durations/battery are never sent.

const SENT = [
  'The wording of your result: scores, research quotes and a few of your answers quoted in it',
  'For a personal greeting: city, region and country (worked out from your IP address), day and part of day',
  'Device type, operating system and processor architecture, whether a touch screen was detected',
  'Browser name and version, light or dark mode',
  'Internet provider, whether it is mobile data, connection speed class, VPN/proxy and private-network checks',
  'Whether this is your first visit (counts like clicks, duration and battery are shown to you but never sent)',
]

const NOT_SENT = [
  'Your IP address, exact coordinates or postal code',
  'Your anonymous visitor ID, click history, click counts or test duration',
  'Battery, screen, graphics card, device model or other hardware details',
  'Your full answer sheet',
  'Your name or email (Hive never asks for them)',
]

export default function AiConsent({ checked, onChange, model }) {
  return (
    <div className="consent">
      <label className="consent-check">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>
          Use AI to polish the wording of my result <span className="muted">(optional)</span>
        </span>
      </label>
      <p className="muted small consent-lead">
        Your conclusions are always written by Hive from verified data and research. If you tick this, your
        written result (listed below) is sent to NVIDIA's AI API{model ? ` (${model})` : ''} to polish the wording only. Quotes and
        numbers are locked, and any rewrite that adds or changes a fact is thrown away. If you leave it unticked,
        nothing leaves Hive's server.
      </p>
      <details className="consent-details">
        <summary>What is and isn't sent to NVIDIA</summary>
        <div className="consent-cols">
          <div>
            <h4>Sent (only if ticked)</h4>
            <ul>{SENT.map((s) => <li key={s}>{s}</li>)}</ul>
          </div>
          <div>
            <h4>Never sent</h4>
            <ul>{NOT_SENT.map((s) => <li key={s}>{s}</li>)}</ul>
          </div>
        </div>
      </details>
    </div>
  )
}
