"""Client IP extraction + IP geolocation / network lookup (ip-api.com, no key needed)."""

import asyncio
import ipaddress
import logging
import time

import httpx
from fastapi import Request

from . import config

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}  # one in-flight lookup per IP
_TTL_SECONDS = 6 * 3600
_FIELDS = (
    "status,message,continent,continentCode,country,countryCode,region,regionName,city,district,zip,"
    "lat,lon,timezone,offset,currency,isp,org,as,asname,reverse,mobile,proxy,hosting,query"
)


def client_ip(request: Request) -> str | None:
    """Best-effort client IP. Proxy headers are only trusted when TRUST_PROXY=true."""
    if config.TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return request.client.host if request.client else None


def is_public(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


async def lookup(ip: str | None) -> dict:
    """Return location + network details for an IP.

    Passing ``None`` asks ip-api for the caller's (this server's) public IP,
    which is what we want in local development.
    """
    key = ip or "__self__"
    if len(_LOCKS) > 10_000:  # keep memory bounded on busy servers
        for k in [k for k, lock in _LOCKS.items() if not lock.locked()]:
            _LOCKS.pop(k, None)
    async with _LOCKS.setdefault(key, asyncio.Lock()):
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < _TTL_SECONDS:
            return cached[1]
        geo = await _fetch(ip)
        if geo:
            _CACHE[key] = (time.time(), geo)
        return geo


async def _fetch(ip: str | None) -> dict:
    # Free tier is HTTP-only and limited to 45 req/min; results are cached above.
    url = f"http://ip-api.com/json/{ip or ''}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, params={"fields": _FIELDS})
            data = resp.json()
    except Exception as exc:  # network errors, rate limiting, bad JSON
        log.warning("Geo lookup failed for %s: %s", ip, exc)
        return {}

    if data.get("status") != "success":
        log.info("Geo lookup unsuccessful for %s: %s", ip, data.get("message"))
        return {}

    geo = {
        "resolved_ip": data.get("query"),
        "continent": data.get("continent"),
        "continent_code": data.get("continentCode"),
        "country": data.get("country"),
        "country_code": data.get("countryCode"),
        "region": data.get("regionName"),
        "region_code": data.get("region"),
        "city": data.get("city"),
        "district": data.get("district") or None,
        "postal_code": data.get("zip"),
        "latitude": data.get("lat"),
        "longitude": data.get("lon"),
        "ip_timezone": data.get("timezone"),
        "ip_utc_offset_min": (data["offset"] // 60) if isinstance(data.get("offset"), int) else None,
        "local_currency": data.get("currency"),
        "reverse_dns": data.get("reverse") or None,
        "isp": data.get("isp"),
        "organization": data.get("org"),
        "asn": data.get("as"),
        "as_name": data.get("asname"),
        "is_mobile_network": data.get("mobile"),
        "is_proxy_or_vpn": data.get("proxy"),
        "is_hosting_or_datacenter": data.get("hosting"),
    }
    return geo
