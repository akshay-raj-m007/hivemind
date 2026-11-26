"""Server-side Mixpanel delivery (not blocked by ad blockers, and carries the real client IP)."""

import logging
import uuid

from mixpanel import Consumer, Mixpanel, MixpanelException

from . import config

log = logging.getLogger(__name__)

mp: Mixpanel | None = (
    Mixpanel(config.MIXPANEL_TOKEN, consumer=Consumer(api_host=config.MIXPANEL_API_HOST))
    if config.MIXPANEL_TOKEN
    else None
)

if mp is None:
    log.warning("MIXPANEL_TOKEN not set - events will be stored locally only.")


def send_card_click(distinct_id: str, props: dict, geo_ip: str | None) -> None:
    """Send the event and update the user's People profile. Runs as a background task."""
    if mp is None:
        return

    event_props = dict(props)
    if geo_ip:
        # `ip` tells Mixpanel which address to geolocate; we also set its
        # reserved geo properties explicitly from our own lookup.
        event_props["ip"] = geo_ip
    if props.get("city"):
        event_props["$city"] = props["city"]
    if props.get("region"):
        event_props["$region"] = props["region"]
    if props.get("country_code"):
        event_props["mp_country_code"] = props["country_code"]

    # Fill Mixpanel's built-in properties so default reports/breakdowns work for server events
    reserved = {
        "$insert_id": props.get("click_id") or uuid.uuid4().hex,  # de-duplicates retries
        "$browser": props.get("ua_browser"),
        "$browser_version": props.get("ua_browser_version"),
        "$os": props.get("ua_os"),
        "$device": props.get("ua_device_model") or props.get("ua_device_family"),
        "$screen_width": props.get("screen_width"),
        "$screen_height": props.get("screen_height"),
        "$current_url": props.get("page_url"),
        "$referrer": props.get("referrer"),
        "$referring_domain": props.get("referring_domain"),
        "$device_id": props.get("device_id"),
        "utm_source": props.get("utm_source"),
        "utm_medium": props.get("utm_medium"),
        "utm_campaign": props.get("utm_campaign"),
        "utm_term": props.get("utm_term"),
        "utm_content": props.get("utm_content"),
    }
    event_props.update({k: v for k, v in reserved.items() if v is not None})

    g = props.get
    profile = {
        "Last Card Clicked": g("card_title"),
        "Last Seen": g("timestamp"),
        "Last IP": g("ip_address"),
        "ISP": g("isp"),
        "ASN": g("asn"),
        "Network Type": g("network_effective_type"),
        "Connection Speed (Mbps)": g("network_downlink_mbps"),
        "Is Mobile Network": g("is_mobile_network"),
        "Likely VPN/Proxy": g("likely_vpn_or_proxy"),
        "$city": g("city"),
        "$region": g("region"),
        "$country_code": g("country_code"),
        "Postal Code": g("postal_code"),
        "Browser": g("ua_browser"),
        "OS": g("ua_os"),
        "Device Kind": g("ua_device_kind"),
        "Device Model": g("ua_device_model") or g("ch_model"),
        "GPU": g("gpu_renderer"),
        "Screen": g("screen"),
        "Language": g("language"),
        "Browser Timezone": g("timezone"),
        "Visit Count": g("visit_count"),
        "Unique Cards Clicked": g("unique_cards_clicked"),
        "Lifetime Sessions": g("lifetime_sessions"),
        "Distinct IPs Used": g("distinct_ips_used"),
        "Ad Blocker": g("ad_blocker_detected"),
        "Do Not Track": g("do_not_track"),
        "Global Privacy Control": g("global_privacy_control"),
    }
    first_touch = {
        "First Card Clicked": g("card_title"),
        "First Click At": g("first_click_at"),
        "First City": g("city"),
        "First Country": g("country"),
        "First ISP": g("isp"),
        "First Referrer": g("first_touch_referrer"),
        "First Landing Page": g("first_touch_landing_page"),
        "First UTM Source": g("first_touch_utm_source"),
        "First UTM Medium": g("first_touch_utm_medium"),
        "First UTM Campaign": g("first_touch_utm_campaign"),
    }
    profile = {k: v for k, v in profile.items() if v is not None}
    first_touch = {k: v for k, v in first_touch.items() if v is not None}
    meta = {"$ip": geo_ip} if geo_ip else None

    try:
        mp.track(distinct_id, "Card Clicked", event_props)
        mp.people_set(distinct_id, profile, meta=meta)
        mp.people_set_once(distinct_id, first_touch, meta=meta)
        mp.people_union(
            distinct_id,
            {
                "Cards Opened": [g("card_title")],
                "IPs Seen": [g("ip_address")] if g("ip_address") else [],
                "Countries Seen": [g("country")] if g("country") else [],
                "Devices Seen": [f"{g('ua_device_kind')} / {g('ua_os')} / {g('ua_browser')}"],
            },
            meta=meta,
        )
        mp.people_increment(
            distinct_id,
            {
                "Total Card Clicks": 1,
                f"Clicks: {g('card_title')}": 1,
                **({"Total Expands": 1} if g("action") == "expand" else {"Total Collapses": 1}),
                **({"Total Rage Clicks": 1} if g("is_rage_click") else {}),
            },
            meta=meta,
        )
    except MixpanelException as exc:
        log.error("Mixpanel delivery failed: %s", exc)
