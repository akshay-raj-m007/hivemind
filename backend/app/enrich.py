"""Server-side enrichment: things only the server can see or compute reliably."""

import ipaddress
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import Request
from user_agents import parse as parse_ua

MAX_KEYS = 200
MAX_STR = 255  # Mixpanel truncates string values at 255 bytes anyway
MAX_LIST = 20


def sanitize_client(raw: dict) -> dict:
    """Keep only flat, scalar (or list-of-scalar) values with safe keys and sizes."""
    out: dict = {}
    for k, v in list(raw.items())[:MAX_KEYS]:
        if not isinstance(k, str) or not k or len(k) > 64 or k.startswith(("$", "mp_")):
            continue  # don't let the browser overwrite Mixpanel reserved properties
        if v is None:
            continue
        if isinstance(v, bool | int | float):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:MAX_STR]
        elif isinstance(v, list):
            items = [x[:MAX_STR] if isinstance(x, str) else x for x in v[:MAX_LIST] if isinstance(x, str | int | float | bool)]
            out[k] = items
    return out


def user_agent_props(ua_string: str | None) -> dict:
    if not ua_string:
        return {}
    ua = parse_ua(ua_string)
    device_kind = (
        "bot" if ua.is_bot else "tablet" if ua.is_tablet else "mobile" if ua.is_mobile else "desktop" if ua.is_pc else "other"
    )
    return {
        "ua_browser": ua.browser.family,
        "ua_browser_version": ua.browser.version_string or None,
        "ua_os": ua.os.family,
        "ua_os_version": ua.os.version_string or None,
        "ua_device_family": ua.device.family,
        "ua_device_brand": ua.device.brand,
        "ua_device_model": ua.device.model,
        "ua_device_kind": device_kind,
        "ua_is_mobile": ua.is_mobile,
        "ua_is_tablet": ua.is_tablet,
        "ua_is_pc": ua.is_pc,
        "ua_is_touch_capable": ua.is_touch_capable,
        "ua_is_bot": ua.is_bot,
    }


def header_props(request: Request) -> dict:
    h = request.headers
    return {
        "http_version": request.scope.get("http_version"),
        "request_scheme": request.url.scheme,
        "request_host": h.get("host"),
        "request_origin": h.get("origin"),
        "request_referer": h.get("referer"),
        "accept_language": h.get("accept-language"),
        "accept_encoding": h.get("accept-encoding"),
        "do_not_track": h.get("dnt") == "1",
        "global_privacy_control": h.get("sec-gpc") == "1",
        "client_hint_brands": h.get("sec-ch-ua"),
        "client_hint_mobile": h.get("sec-ch-ua-mobile"),
        "client_hint_platform": (h.get("sec-ch-ua-platform") or "").strip('"') or None,
        "fetch_site": h.get("sec-fetch-site"),
        "fetch_mode": h.get("sec-fetch-mode"),
        "save_data_header": h.get("save-data") == "on",
        "via_proxy_header": bool(h.get("via") or h.get("x-forwarded-for")),
    }


def ip_props(ip: str | None) -> dict:
    try:
        addr = ipaddress.ip_address(ip) if ip else None
    except ValueError:
        addr = None
    if addr is None:
        return {}
    return {
        "ip_version": f"IPv{addr.version}",
        "ip_is_private": addr.is_private,
        "ip_is_loopback": addr.is_loopback,
    }


def time_props(browser_offset_min: int | None, ip_offset_min: int | None, ip_tz: str | None) -> dict:
    now = datetime.now(timezone.utc)
    props = {
        "server_received_at": now.isoformat(),
        "server_hour_utc": now.hour,
        "server_day_of_week_utc": now.strftime("%A"),
    }
    # Time of day where the visitor's IP is located
    if ip_tz:
        try:
            local = now.astimezone(ZoneInfo(ip_tz))
            props["ip_local_hour"] = local.hour
            props["ip_local_day_of_week"] = local.strftime("%A")
        except Exception:
            pass
    # Browser clock offset that differs from the IP location's offset is a common VPN / travel signal.
    # (Offsets, not zone names: "Asia/Calcutta" and "Asia/Kolkata" are the same zone.)
    if isinstance(browser_offset_min, int) and isinstance(ip_offset_min, int):
        props["timezone_mismatch"] = browser_offset_min != ip_offset_min
    return props


def derived_flags(props: dict) -> dict:
    """Combine signals into a few easy-to-filter flags."""
    vpn_signals = [
        props.get("is_proxy_or_vpn"),
        props.get("is_hosting_or_datacenter"),
        props.get("timezone_mismatch"),
    ]
    bot_signals = [props.get("ua_is_bot"), props.get("webdriver"), props.get("is_trusted_event") is False]
    return {
        "vpn_signal_count": sum(bool(s) for s in vpn_signals),
        "likely_vpn_or_proxy": sum(bool(s) for s in vpn_signals) >= 2 or bool(props.get("is_proxy_or_vpn")),
        "likely_bot": any(bool(s) for s in bot_signals),
    }
