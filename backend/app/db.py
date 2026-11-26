"""Tiny SQLite store for click history and per-user click counts."""

import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS clicks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        distinct_id TEXT NOT NULL,
        card_id     TEXT NOT NULL,
        card_title  TEXT NOT NULL,
        action      TEXT NOT NULL,
        ip          TEXT,
        country     TEXT,
        city        TEXT,
        isp         TEXT,
        network     TEXT,
        properties  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_clicks_user ON clicks (distinct_id, card_id);
    CREATE INDEX IF NOT EXISTS idx_clicks_card ON clicks (card_id);
    """
)
# lightweight migration for databases created by the first version
if "session_id" not in {r[1] for r in _conn.execute("PRAGMA table_info(clicks)")}:
    _conn.execute("ALTER TABLE clicks ADD COLUMN session_id TEXT")
    _conn.commit()


def _seconds_between(earlier_iso: str | None, later: datetime) -> float | None:
    if not earlier_iso:
        return None
    return round((later - datetime.fromisoformat(earlier_iso)).total_seconds(), 1)


def record_click(distinct_id: str, card_id: str, card_title: str, action: str, props: dict) -> dict:
    """Store a click and return the visitor's history stats (including this click)."""
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    today = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    session_id = props.get("session_id")
    ip = props.get("ip_address")
    country = props.get("country")

    with _lock:
        u = _conn.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(card_id = ?), 0)      AS card_count,
                      COALESCE(SUM(ts >= ?), 0)          AS today,
                      COALESCE(SUM(session_id = ?), 0)   AS in_session,
                      COALESCE(SUM(card_id = ? AND session_id = ?), 0) AS card_in_session,
                      MIN(ts) AS first_ts, MAX(ts) AS last_ts,
                      COUNT(DISTINCT card_id)    AS uniq_cards,
                      COUNT(DISTINCT session_id) AS sessions,
                      COUNT(DISTINCT ip)         AS ips,
                      COUNT(DISTINCT country)    AS countries,
                      COALESCE(SUM(ip = ?), 0)      AS seen_ip,
                      COALESCE(SUM(country = ?), 0) AS seen_country
               FROM clicks WHERE distinct_id = ? AND action = 'expand'""",
            (card_id, today, session_id, card_id, session_id, ip, country, distinct_id),
        ).fetchone()
        last_card_ts = _conn.execute(
            "SELECT MAX(ts) FROM clicks WHERE distinct_id = ? AND card_id = ? AND action = 'expand'", (distinct_id, card_id)
        ).fetchone()[0]
        c = _conn.execute(
            "SELECT COUNT(*) AS clicks, COUNT(DISTINCT distinct_id) AS users FROM clicks WHERE card_id = ? AND action = 'expand'", (card_id,)
        ).fetchone()
        g = _conn.execute("SELECT COUNT(*) AS clicks, COUNT(DISTINCT distinct_id) AS users FROM clicks WHERE action = 'expand'").fetchone()

        first_on_card = u["card_count"] == 0
        stats = {
            "timestamp": now,
            # this visitor
            "card_click_count": u["card_count"] + 1,
            "total_click_count": u["total"] + 1,
            "clicks_today": u["today"] + 1,
            "session_click_count_server": u["in_session"] + 1,
            "card_clicks_this_session": u["card_in_session"] + 1,
            "unique_cards_clicked": u["uniq_cards"] + (1 if first_on_card else 0),
            "lifetime_sessions": u["sessions"] + (1 if session_id and u["in_session"] == 0 else 0),
            "distinct_ips_used": u["ips"] + (1 if ip and u["seen_ip"] == 0 else 0),
            "distinct_countries_seen": u["countries"] + (1 if country and u["seen_country"] == 0 else 0),
            "is_new_visitor": u["total"] == 0,
            "is_first_click_on_card": first_on_card,
            "is_new_ip_for_visitor": bool(ip) and u["total"] > 0 and u["seen_ip"] == 0,
            "first_click_at": u["first_ts"] or now,
            "days_since_first_click": round((now_dt - datetime.fromisoformat(u["first_ts"])).total_seconds() / 86400, 2)
            if u["first_ts"] else 0,
            "seconds_since_last_click": _seconds_between(u["last_ts"], now_dt),
            "seconds_since_last_click_on_card": _seconds_between(last_card_ts, now_dt),
            # this card / everyone
            "card_total_clicks_all_users": c["clicks"] + 1,
            "card_unique_users": c["users"] + (1 if first_on_card else 0),
            "app_total_clicks": g["clicks"] + 1,
            "app_unique_users": g["users"] + (1 if u["total"] == 0 else 0),
        }
        props = {**props, **stats}
        _conn.execute(
            """INSERT INTO clicks (ts, distinct_id, card_id, card_title, action, ip, country, city, isp, network,
                                   session_id, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now, distinct_id, card_id, card_title, action,
                ip, country, props.get("city"), props.get("isp"), props.get("network_effective_type"),
                session_id, json.dumps(props, default=str),
            ),
        )
        _conn.commit()
    return stats


def summary() -> dict:
    with _lock:
        totals = _conn.execute(
            "SELECT COUNT(*) AS clicks, COUNT(DISTINCT distinct_id) AS users, COUNT(DISTINCT country) AS countries FROM clicks WHERE action = 'expand'"
        ).fetchone()
        per_card = _conn.execute(
            """SELECT card_id, card_title, COUNT(*) AS clicks, COUNT(DISTINCT distinct_id) AS users
               FROM clicks WHERE action = 'expand' GROUP BY card_id, card_title ORDER BY clicks DESC"""
        ).fetchall()
        per_country = _conn.execute(
            """SELECT COALESCE(country, 'Unknown') AS country, COUNT(*) AS clicks
               FROM clicks WHERE action = 'expand' GROUP BY country ORDER BY clicks DESC LIMIT 8"""
        ).fetchall()
    return {
        "total_clicks": totals["clicks"],
        "unique_users": totals["users"],
        "countries": totals["countries"],
        "per_card": [dict(r) for r in per_card],
        "per_country": [dict(r) for r in per_country],
    }


def recent(limit: int = 50) -> list[dict]:
    with _lock:
        rows = _conn.execute("SELECT * FROM clicks WHERE action = 'expand' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["properties"] = json.loads(item["properties"])
        out.append(item)
    return out
