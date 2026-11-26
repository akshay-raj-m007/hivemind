import json
import random

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import narrative

client = TestClient(app)
TEST_IDS = ["rorschach", "rmet", "big-five", "jungian-type", "riasec", "self-esteem", "attachment"]


def answers_for(test_id: str, q: dict) -> dict:
    rnd = random.Random(42)
    if q["type"] == "image_text":
        return {i["id"]: "a bat" for i in q["items"]}
    if q["type"] == "image_choice":
        return {i["id"]: rnd.choice(i["options"]) for i in q["items"] if not i["practice"]}
    if q["type"] == "bipolar":
        return {i["id"]: rnd.randint(1, 5) for i in q["items"]}
    values = [s["value"] for s in q["scale"]]
    return {i["id"]: rnd.choice(values) for i in q["items"]}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["llm_enabled"] is False


def test_catalog_has_seven_available_tests():
    tests = client.get("/api/tests").json()
    assert [t["id"] for t in tests] == TEST_IDS
    assert all(t["available"] and t["question_count"] > 0 for t in tests)


@pytest.mark.parametrize("test_id", TEST_IDS)
def test_questions_never_leak_answer_keys(test_id):
    q = client.get(f"/api/tests/{test_id}").json()
    raw = json.dumps(q)
    assert '"answer"' not in raw and "match_terms" not in raw and '"key"' not in raw


@pytest.mark.parametrize("test_id", TEST_IDS)
def test_submit_returns_structured_result(test_id):
    q = client.get(f"/api/tests/{test_id}").json()
    r = client.post(f"/api/tests/{test_id}/submit",
                    json={"distinct_id": "ci", "answers": answers_for(test_id, q), "use_ai": True,
                          "meta": {"duration_sec": 120, "question_count": len(q["items"])}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["story_title"] and d["sections"]
    assert d["paragraph_source"] == "template"  # no key in CI, so nothing is sent to an AI
    for sec in d["sections"]:
        assert sec["heading"]
        for quote in sec["quotes"]:
            assert quote["text"] and quote["url"].startswith("http")


def test_incomplete_answers_rejected():
    r = client.post("/api/tests/big-five/submit", json={"distinct_id": "ci", "answers": {"ipip1": 3}})
    assert r.status_code == 422


def test_unknown_test_404():
    assert client.get("/api/tests/mmpi").status_code == 404


def test_analytics_needs_passkey():
    assert client.get("/api/analytics/summary").status_code == 401
    assert client.get("/api/analytics/summary", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/api/analytics/summary", headers={"X-Admin-Key": "test-passkey"}).status_code == 200


def test_only_expands_are_counted():
    body = {"distinct_id": "counter", "card_id": "big-five", "client": {}}
    first = client.post("/api/track/card-click", json={**body, "action": "expand"}).json()
    ignored = client.post("/api/track/card-click", json={**body, "action": "collapse"}).json()
    second = client.post("/api/track/card-click", json={**body, "action": "expand"}).json()
    assert ignored.get("ignored") is True
    assert second["card_click_count"] == first["card_click_count"] + 1


def test_polish_guard_rejects_invented_content():
    original = "Your score is 13 out of 30, “satisfied with myself”, in Tirupati."
    assert narrative.faithful(original, "Your score is 13 out of 30, “satisfied with myself”, in Tirupati.") == []
    assert narrative.faithful(original, "Your score is 15 out of 30, “satisfied with myself”, in Tirupati.")
    assert narrative.faithful(original, "Your score is 13 out of 30, “satisfied”, in Mumbai.")
