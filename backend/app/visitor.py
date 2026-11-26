"""'About you' context facts, built from the analytics we already recorded for this visitor's clicks
(the same properties that are sent to Mixpanel). Facts are only included when the data exists."""

import json

from . import db


def latest_properties(distinct_id: str) -> dict:
    with db._lock:
        row = db._conn.execute(
            "SELECT properties FROM clicks WHERE distinct_id = ? ORDER BY id DESC LIMIT 1", (distinct_id,)
        ).fetchone()
    return json.loads(row[0]) if row else {}


def _os_name(p: dict) -> str | None:
    os_name = p.get("ua_os")
    if not os_name or os_name == "Other":
        return None
    if os_name == "Windows" and p.get("ch_windows_version") == "Windows 11":
        return "Windows 11"
    if os_name == "Mac OS X":
        return "macOS"
    version = p.get("ua_os_version")
    if os_name in ("Android", "iOS") and version:
        return f"{os_name} {version.split('.')[0]}"
    return os_name


def _duration(sec: int) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m} minute{'s' if m != 1 else ''} {s} seconds" if m else f"{s} seconds"


def _per_answer(dur: int, n: int, before: str, after: str) -> str:
    per = round(dur / n)
    if per < 1:
        return ""  # too fast to say anything meaningful
    return f"{before}roughly {per} second{'s' if per != 1 else ''} per answer{after}"


def context_facts(distinct_id: str, meta: dict | None = None) -> list[str]:
    p = latest_properties(distinct_id)
    meta = meta or {}
    facts = []
    dur, n = meta.get("duration_sec"), meta.get("question_count")
    if isinstance(dur, int) and isinstance(n, int) and 0 < dur < 4 * 3600 and n > 0:
        facts.append(f"You answered {n} questions in about {_duration(dur)}{_per_answer(dur, n, ' (', ')')}.")
    if not p:
        return facts

    place = [x for x in (p.get("city"), p.get("region"), p.get("country")) if x]
    # drop duplicates such as "Singapore, Singapore"
    place = [x for i, x in enumerate(place) if x not in place[:i]]
    if place:
        vpn = " (the IP may belong to a VPN or proxy)" if p.get("likely_vpn_or_proxy") else ""
        facts.append(f"Based on your IP address, you appear to be in {', '.join(place)}{vpn}.")

    os_name = _os_name(p)
    kind = p.get("ua_device_kind")
    model = p.get("ch_model") or p.get("ua_device_model")
    device_bits = []
    if os_name:
        device_bits.append(f"runs {os_name}")
    if kind in ("desktop", "mobile", "tablet"):
        device_bits.append(f"is a {'desktop or laptop computer' if kind == 'desktop' else kind + ' device'}")
    if model and model not in ("K", "Other"):
        device_bits.append(f"reports its model as {model}")
    if device_bits:
        joined = device_bits[0] if len(device_bits) == 1 else ", ".join(device_bits[:-1]) + " and " + device_bits[-1]
        facts.append(f"Your device {joined}.")

    if p.get("touch_support") is False or p.get("max_touch_points") == 0:
        facts.append("No touch screen was detected on your device.")
    elif p.get("touch_support") is True:
        facts.append("Your device has a touch screen.")

    if p.get("ua_browser") and p.get("ua_browser") != "Other":
        facts.append(f"You are using the {p['ua_browser']} browser.")

    if p.get("isp"):
        mobile = " on a mobile network" if p.get("is_mobile_network") else ""
        facts.append(f"Your internet provider is {p['isp']}{mobile}.")
    if p.get("network_effective_type"):
        facts.append(f"Your browser rates your connection speed in the '{p['network_effective_type']}' class.")

    visits = p.get("visit_count")
    if isinstance(visits, int):
        facts.append("This is your first visit to Hive." if visits <= 1 else f"This is visit number {visits} to Hive "
                     "for you.")
    cards_seen = p.get("session_unique_cards")
    if isinstance(cards_seen, int) and cards_seen > 1:
        facts.append(f"You explored {cards_seen} different test cards during this visit.")
    source = {"organic_search": "a search engine", "social": "a social media link", "referral": "a link on another site",
              "campaign": "a campaign link", "paid": "an ad"}.get(p.get("traffic_source"))
    if source:
        facts.append(f"You arrived at Hive through {source}.")

    if p.get("part_of_day"):
        facts.append(f"You are taking this in the {p['part_of_day']} (your local time).")
    return facts


def context_story(distinct_id: str, meta: dict | None = None) -> str | None:
    """A short, natural opening paragraph about the visit, built only from recorded analytics."""
    p = latest_properties(distinct_id)
    meta = meta or {}
    opener = {"morning": "One morning", "afternoon": "One afternoon", "evening": "One evening",
              "night": "Late at night"}.get(p.get("part_of_day"), "")
    where = ", ".join(dict.fromkeys(x for x in (p.get("city"), p.get("region"), p.get("country")) if x))
    os_name = _os_name(p) if p else None
    kind = {"desktop": "desktop or laptop", "mobile": "phone", "tablet": "tablet"}.get(p.get("ua_device_kind"))
    device = " ".join(x for x in (os_name, kind) if x)
    if p.get("touch_support") is False and device:
        device += " without a touch screen"
    isp, speed = p.get("isp"), p.get("network_effective_type")
    mobile = " mobile" if p.get("is_mobile_network") else ""

    first = ""
    if opener or where:
        first = (opener + (" in " + where if where else "")).strip()
        first = first[0].upper() + first[1:] + ", you took this test"
    elif device or isp:
        first = "You took this test"
    if first:
        if device:
            first += f" on a {device}"
        if isp:
            first += f", connected through {isp}" + (" on mobile data" if mobile else "") + (
                f" at {speed}-class speed" if speed else "")
        first += "."
    sentences = [first] if first else []

    dur, n = meta.get("duration_sec"), meta.get("question_count")
    if isinstance(dur, int) and isinstance(n, int) and 0 < dur < 4 * 3600 and n > 0:
        sentences.append(f"You worked through {n} questions in about {_duration(dur)}{_per_answer(dur, n, ', ', '')}.")
    visits, cards = p.get("visit_count"), p.get("session_unique_cards")
    bits = []
    if isinstance(visits, int):
        bits.append("It was your first visit to Hive" if visits <= 1 else f"It was visit number {visits} to Hive")
    if isinstance(cards, int) and cards > 1:
        bits.append(f"you looked at {cards} different tests along the way")
    if bits:
        sentences.append(", and ".join(bits) + ".")
    return " ".join(sentences) or None


# ---------------------------------------------------------------- greeting profile (for the varied intro)

def visit_profile(distinct_id: str, meta: dict | None = None) -> dict[str, str]:
    """Labelled, human-readable facts about this visit, taken only from recorded analytics."""
    import ipaddress
    from datetime import datetime

    p = latest_properties(distinct_id)
    meta = meta or {}
    f: dict[str, str] = {}
    place = ", ".join(dict.fromkeys(x for x in (p.get("city"), p.get("region"), p.get("country")) if x))
    if place:
        f["place"] = place
    if isinstance(p.get("local_hour"), int):
        f["local time"] = f"around {p['local_hour']:02d}:00 your time ({p.get('part_of_day', '')})".replace(" ()", "")
    if p.get("local_day_of_week"):
        f["day"] = p["local_day_of_week"] + (" (weekend)" if p.get("is_weekend") else "")
    os_name = _os_name(p)
    if os_name:
        arch = " ".join(x for x in (p.get("ch_architecture"), f"{p['ch_bitness']}-bit" if p.get("ch_bitness") else None) if x)
        f["operating system"] = os_name + (f" ({arch.replace(' ', ', ')})" if arch else "")
    kind = {"desktop": "desktop or laptop", "mobile": "mobile phone", "tablet": "tablet"}.get(p.get("ua_device_kind"))
    if kind:
        f["device"] = kind + (" with no touch screen" if p.get("touch_support") is False else
                              " with a touch screen" if p.get("touch_support") else "")
    if p.get("ua_browser") and p["ua_browser"] not in ("Other", "HeadlessChrome"):
        f["browser"] = f"{p['ua_browser']} {str(p.get('ua_browser_version') or '').split('.')[0]}".strip()
    if p.get("color_scheme"):
        f["screen theme"] = f"{p['color_scheme']} mode"
    if p.get("isp"):
        f["internet provider"] = p["isp"] + (" (mobile network)" if p.get("is_mobile_network") else " (not a mobile network)")
    if p.get("network_effective_type"):
        speed = f"{p['network_effective_type']}-class connection"
        if p.get("network_downlink_mbps"):
            speed += f", about {p['network_downlink_mbps']} Mbps"
        f["connection"] = speed
    if p.get("likely_vpn_or_proxy"):
        f["vpn"] = "your connection looks like it goes through a VPN or proxy"
    elif "is_proxy_or_vpn" in p:
        f["vpn"] = "no VPN or proxy detected"
    raw = p.get("raw_request_ip")
    try:
        if raw and ipaddress.ip_address(raw).is_private:
            f["network"] = "you reached Hive from a private (local) network address"
    except ValueError:
        pass
    if isinstance(p.get("battery_level_pct"), int):
        f["battery"] = f"{p['battery_level_pct']}%" + (", charging" if p.get("battery_charging") else ", not charging")
    visits = p.get("visit_count")
    if isinstance(visits, int):
        f["visits"] = "first visit to Hive" if visits <= 1 else f"visit number {visits} to Hive"
    first = p.get("first_visit_at") or p.get("first_touch_at")
    if first and isinstance(visits, int) and visits > 1:
        try:
            f["first visit"] = datetime.fromisoformat(first.replace("Z", "+00:00")).strftime("%d %B %Y")
        except ValueError:
            pass
    if isinstance(p.get("clicks_today"), int):
        f["card clicks today (all visits, all tests)"] = str(p["clicks_today"])
    if isinstance(p.get("session_unique_cards"), int) and p["session_unique_cards"] > 1:
        f["different test cards opened during this visit"] = str(p["session_unique_cards"])
    src = {"organic_search": "a search engine", "social": "social media", "referral": "a link on another site",
           "campaign": "a campaign link", "paid": "an ad"}.get(p.get("traffic_source"))
    if src:
        f["arrived via"] = src
    dur, n = meta.get("duration_sec"), meta.get("question_count")
    if isinstance(dur, int) and isinstance(n, int) and 0 < dur < 4 * 3600 and n > 0:
        f["the test you just finished"] = f"{n} questions in about {_duration(dur)}" + _per_answer(dur, n, " (", ")")
    return f


def greeting_fallback(profile: dict[str, str]) -> str | None:
    """A code-written greeting, picked at random so it changes between visits."""
    import random

    if not profile:
        return None
    bits = []
    place, os_, dev = profile.get("place"), profile.get("operating system"), profile.get("device")
    openers = []
    if place:
        city = place.split(",")[0]
        openers += [f"Hello from Hive to {city}!", f"Greetings, {city}!", f"Hi there, {city}!",
                    f"Namaste from Hive, {city}!" if place.endswith("India") else f"Hey {city}!"]
    openers.append("Welcome back to Hive!" if profile.get("visits", "").startswith("visit number") else "Welcome to Hive!")
    bits.append(random.choice(openers))
    tech = [x for x in (os_ and f"a {os_} machine", dev and f"a {dev}", profile.get("browser") and f"{profile['browser']}") if x]
    if tech:
        bits.append(random.choice([
            f"You're here on {_join_simple(tech)}",
            f"Your setup today: {_join_simple(tech)}",
        ]) + (f", connected through {profile['internet provider']}" if profile.get("internet provider") else "") + ".")
    extras = []
    if profile.get("local time"):
        extras.append(f"it's {profile['local time']}")
    clicks = profile.get("card clicks today (all visits, all tests)")
    if clicks:
        extras.append(f"you've made {clicks} card clicks today")
    if profile.get("the test you just finished"):
        extras.append(f"you finished {profile['the test you just finished']}")
    if profile.get("battery"):
        extras.append(f"your battery is at {profile['battery']}")
    random.shuffle(extras)
    if extras:
        s = "; ".join(extras[:2])
        bits.append(s[0].upper() + s[1:] + ".")
    return " ".join(bits)


def _join_simple(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


NUMERIC_KEYS = ("battery", "visits", "first visit", "card clicks today (all visits, all tests)",
                "different test cards opened during this visit", "the test you just finished")


def greeting_facts(profile: dict[str, str]) -> dict[str, str]:
    """Descriptive facts only (no counts/durations), so the AI greeting cannot mix numbers between facts."""
    out = {k: v for k, v in profile.items() if k not in NUMERIC_KEYS}
    if "local time" in out:  # keep only the part of day, not the clock time
        part = out.pop("local time")
        if "(" in part:
            out["time of day"] = part.split("(")[1].rstrip(")")
    if profile.get("visits", "").startswith("first"):
        out["visit"] = "first visit to Hive"
    elif profile.get("visits"):
        out["visit"] = "returning visitor"
    return out


def visit_stats(profile: dict[str, str]) -> list[dict[str, str]]:
    """Numbers shown as chips under the greeting, rendered exactly as recorded."""
    stats = []
    if profile.get("the test you just finished"):
        stats.append({"label": "This test", "value": profile["the test you just finished"]})
    if profile.get("card clicks today (all visits, all tests)"):
        stats.append({"label": "Card clicks today", "value": profile["card clicks today (all visits, all tests)"]})
    if profile.get("different test cards opened during this visit"):
        stats.append({"label": "Tests explored this visit", "value": profile["different test cards opened during this visit"]})
    if profile.get("visits"):
        stats.append({"label": "Visit", "value": profile["visits"].replace(" to Hive", "")})
    if profile.get("first visit"):
        stats.append({"label": "First visit", "value": profile["first visit"]})
    if profile.get("local time"):
        stats.append({"label": "Local time", "value": profile["local time"]})
    if profile.get("connection"):
        stats.append({"label": "Connection", "value": profile["connection"]})
    if profile.get("battery"):
        stats.append({"label": "Battery", "value": profile["battery"]})
    return stats
