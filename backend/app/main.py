import hmac

import logging
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import catalog, config, db, enrich, geo, llm, narrative, portrait, scoring, tracking, visitor
from .cards import CARDS, CARDS_BY_ID

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

if config.ADMIN_KEY == "change-me":
    log.warning("ADMIN_KEY is the default value - change it in backend/.env before deploying.")

app = FastAPI(title="Hive API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=config.CORS_ORIGIN_REGEX,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


# ---------- models ----------

class CardClick(BaseModel):
    distinct_id: str = Field(min_length=1, max_length=200)
    card_id: str = Field(min_length=1, max_length=64)
    action: Literal["expand", "collapse"] = "expand"
    # Browser-collected context: flat key/value pairs, sanitized server-side.
    client: dict[str, Any] = Field(default_factory=dict)


class TestSubmission(BaseModel):
    distinct_id: str = Field(min_length=1, max_length=200)
    answers: dict[str, int | str] = Field(max_length=100)
    # Explicit opt-in from the consent checkbox. Without it nothing is sent to NVIDIA.
    use_ai: bool = False
    # Optional timing info from the browser (shown in the "about you" part of the result)
    meta: dict[str, int] = Field(default_factory=dict, max_length=5)


def require_admin(x_admin_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_admin_key, config.ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin key")


# ---------- routes ----------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mixpanel_enabled": tracking.mp is not None,
        "llm_enabled": llm.enabled(),
        "llm_model": config.NVIDIA_CHAT_MODEL if llm.enabled() else None,
    }


@app.get("/api/cards")
def list_cards():
    return CARDS


@app.post("/api/track/card-click")
async def track_card_click(event: CardClick, request: Request, background: BackgroundTasks):
    card = CARDS_BY_ID.get(event.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Unknown card")
    if event.action != "expand":  # only opening a card counts; collapses are not recorded or sent to Mixpanel
        return {"card_id": card["id"], "ignored": True}

    ip = geo.client_ip(request)
    if geo.is_public(ip):
        location = await geo.lookup(ip)
    elif config.DEV_RESOLVE_PUBLIC_IP:
        location = await geo.lookup(None)  # local dev: geolocate this machine's public IP
    else:
        location = {}

    # IP used for geolocation in Mixpanel: the real one, or the dev-resolved public one.
    geo_ip = ip if geo.is_public(ip) else location.get("resolved_ip")

    client = enrich.sanitize_client(event.client)
    props = {
        **client,  # browser context first, so server-derived values below win on any key clash
        "card_id": card["id"],
        "card_title": card["title"],
        "card_tag": card["tag"],
        "action": event.action,
        "tracked_via": "server",
        "ip_address": geo_ip or ip,
        "raw_request_ip": ip,
        **location,
        **enrich.ip_props(geo_ip or ip),
        **enrich.user_agent_props(request.headers.get("user-agent")),
        **enrich.header_props(request),
        **enrich.time_props(client.get("utc_offset_min"), location.get("ip_utc_offset_min"), location.get("ip_timezone")),
    }
    props.update(enrich.derived_flags(props))
    props = {k: v for k, v in props.items() if v is not None}

    stats = await run_in_threadpool(
        db.record_click, event.distinct_id, card["id"], card["title"], event.action, props
    )
    props.update(stats)

    background.add_task(tracking.send_card_click, event.distinct_id, props, geo_ip)

    return {
        "card_id": card["id"],
        "card_click_count": stats["card_click_count"],
        "total_click_count": stats["total_click_count"],
    }


@app.get("/api/analytics/summary", dependencies=[Depends(require_admin)])
async def analytics_summary():
    return await run_in_threadpool(db.summary)


@app.get("/api/analytics/recent", dependencies=[Depends(require_admin)])
async def analytics_recent(limit: int = 50):
    return await run_in_threadpool(db.recent, max(1, min(limit, 200)))


# ---------- tests ----------

def _runnable(test_id: str) -> dict:
    card = catalog.CATALOG_BY_ID.get(test_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Unknown test")
    if not card["available"]:
        raise HTTPException(status_code=409, detail=card.get("unavailable_reason") or "Test not available")
    return card


@app.get("/api/tests")
def list_tests():
    return CARDS


@app.get("/api/tests/{test_id}")
def get_test(test_id: str):
    card = _runnable(test_id)
    return {"card": CARDS_BY_ID[test_id], **catalog.questions_for(test_id)}


@app.post("/api/tests/{test_id}/submit")
async def submit_test(test_id: str, submission: TestSubmission):
    card = _runnable(test_id)
    try:
        result = await scoring.score(test_id, submission.answers)
    except scoring.AnswerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    context = await run_in_threadpool(visitor.context_facts, submission.distinct_id, submission.meta)
    profile = await run_in_threadpool(visitor.visit_profile, submission.distinct_id, submission.meta)
    story = await narrative.compose(portrait.build(test_id, result, submission.answers),
                                    visitor.greeting_facts(profile), visitor.greeting_fallback(profile),
                                    use_ai=submission.use_ai)
    return {
        "test_id": test_id,
        "title": card["title"],
        "result": result,
        "context_facts": context,
        "visit_profile": profile,
        "visit_stats": visitor.visit_stats(profile),
        "story_title": story["title"],
        "tagline": story["tagline"],
        "greeting": story["greeting"],
        "ai_greeting": story["ai_greeting"],
        "sections": story["sections"],
        "paragraph_source": story["source"],
        "paragraph_model": story["model"],
        "polished_paragraphs": story["polished"],
        "polish_targets": story.get("polish_targets", 0),
        "ai_requested": submission.use_ai,
        "sources": CARDS_BY_ID[test_id].get("sources", []),
    }
