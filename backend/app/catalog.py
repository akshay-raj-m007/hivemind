"""The seven Hive test cards. Content for runnable tests is loaded from app/test_data/*.json,
which is generated from primary sources by tools/build_test_data.py."""

import json
from functools import lru_cache
from pathlib import Path

from . import config

DATA_DIR = Path(__file__).resolve().parent / "test_data"


@lru_cache
def load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


CATALOG = [
    {
        "id": "rorschach",
        "title": "Rorschach Inkblot Test",
        "tag": "Projective",
        "summary": "Ten classic inkblots. Tell us what you see in each one.",
        "details": "Uses Hermann Rorschach's original ten plates (public domain). Your descriptions are compared with "
        "the 'popular' responses published for each card (Beck, Piotrowski, Dana). A full Rorschach assessment also "
        "codes location, determinants and form quality, which needs a trained examiner, so Hive reports only how "
        "conventional or individual your perceptions were.",
        "data_file": "rorschach.json",
        "format": "Free text",
        "minutes": 5,
        "available": True,
    },
    {
        "id": "rmet",
        "title": "Reading the Mind in the Eyes (RMET)",
        "tag": "Social cognition",
        "summary": "36 photos of eyes. Pick the word that fits what the person is thinking or feeling.",
        "details": "The revised adult Eyes Test from the Autism Research Centre, University of Cambridge "
        "(Baron-Cohen et al., 2001). Correct answers are the words a clear majority of judges agreed on. Your score "
        "is compared with the published adult averages. Not a diagnostic test.",
        "data_file": "rmet.json",
        "format": "Multiple choice",
        "minutes": 7,
        "available": config.ENABLE_RMET,
        "unavailable_reason": None if config.ENABLE_RMET else "Disabled on this server (ENABLE_RMET=false).",
        "license": "Autism Research Centre test, used with acknowledgement for non-commercial purposes.",
        "official_url": "https://www.autismresearchcentre.com/tests/eyes-test-adult/",
    },
    {
        "id": "big-five",
        "title": "The Big Five (OCEAN)",
        "tag": "Personality",
        "summary": "50 statements. Measure Extraversion, Agreeableness, Conscientiousness, Emotional Stability and Openness.",
        "details": "Uses the public-domain IPIP 50-item Big-Five Factor Markers (Goldberg, 1992). Your scores are "
        "compared with 19,718 people from the Open Psychometrics dataset, and each trait is described using the "
        "definitions in John, Naumann & Soto (2008).",
        "data_file": "big_five.json",
        "format": "Rating scale",
        "minutes": 8,
        "available": True,
    },
    {
        "id": "jungian-type",
        "title": "Myers-Briggs-style Type (MBTI alternative)",
        "tag": "Personality type",
        "summary": "32 either/or pairs. Get your four-letter type.",
        "details": "The official MBTI is a paid product of The Myers-Briggs Company. Hive uses the Open Extended "
        "Jungian Type Scales 1.2 (Open Psychometrics), an open alternative built from people who knew their type. "
        "It gives the same four preferences (E/I, S/N, T/F, J/P) but is not the MBTI.",
        "data_file": "oejts.json",
        "format": "Either/or scale",
        "minutes": 5,
        "available": True,
    },
    {
        "id": "riasec",
        "title": "Holland Code (RIASEC) Career Interests",
        "tag": "Career",
        "summary": "48 work activities. Discover which of six interest areas fit you best.",
        "details": "Uses public-domain items from the Interest Item Pool (Liao, Armstrong & Rounds, 2008), with "
        "interest areas defined by O*NET (U.S. Department of Labor). Your scores are compared with over 135,000 "
        "people from the Open Psychometrics dataset.",
        "data_file": "riasec.json",
        "format": "Rating scale",
        "minutes": 6,
        "available": True,
    },
    {
        "id": "self-esteem",
        "title": "Rosenberg Self-Esteem Scale",
        "tag": "Self-concept",
        "summary": "10 statements about how you feel about yourself.",
        "details": "The most widely used self-esteem measure (Rosenberg, 1965), now in the public domain. Scored "
        "using the University of Maryland's instructions and compared with over 46,000 people from the Open "
        "Psychometrics dataset.",
        "data_file": "rse.json",
        "format": "Agree / disagree",
        "minutes": 2,
        "available": True,
    },
    {
        "id": "attachment",
        "title": "Attachment Style (ECR)",
        "tag": "Relationships",
        "summary": "36 statements about close relationships. Measure attachment anxiety and avoidance.",
        "details": "The Experiences in Close Relationships scale (Brennan, Clark & Shaver, 1998), the standard "
        "measure of adult attachment's two dimensions. Items and scoring come from R. Chris Fraley's site, and your "
        "scores are compared with over 46,000 people from the Open Psychometrics dataset.",
        "data_file": "ecr.json",
        "format": "Agree / disagree",
        "minutes": 6,
        "available": True,
    },
]

CATALOG_BY_ID = {c["id"]: c for c in CATALOG}


def public_card(card: dict) -> dict:
    """Card metadata for the UI (no data file paths)."""
    out = {k: v for k, v in card.items() if k != "data_file"}
    if card.get("data_file") and card["available"]:
        data = load(card["data_file"])
        out["question_count"] = len([i for i in data.get("items", data.get("cards", [])) if not i.get("practice")])
        out["sources"] = data.get("sources", [])
        out["license"] = data.get("license")
    return out


def questions_for(test_id: str) -> dict:
    """Test content for the runner. Answer keys and matching rules never leave the server."""
    card = CATALOG_BY_ID[test_id]
    data = load(card["data_file"])
    if test_id in ("big-five", "riasec", "self-esteem", "attachment"):
        return {
            "type": "likert",
            "instructions": data["instructions"],
            "scale": data["scale"],
            "items": [{"id": i["id"], "text": i["text"]} for i in data["items"]],
        }
    if test_id == "jungian-type":
        return {
            "type": "bipolar",
            "instructions": data["instructions"],
            "items": [{"id": i["id"], "left": i["left"], "right": i["right"]} for i in data["items"]],
        }
    if test_id == "rmet":
        return {
            "type": "image_choice",
            "instructions": data["instructions"],
            "glossary_url": data["glossary_url"],
            "items": [
                {"id": i["id"], "image": i["image"], "options": i["options"], "practice": i["practice"]}
                for i in data["items"]
            ],
        }
    if test_id == "rorschach":
        return {
            "type": "image_text",
            "instructions": data["instructions"],
            "items": [{"id": c["id"], "image": c["image"], "label": f"Card {c['roman']}"} for c in data["cards"]],
        }
    raise KeyError(test_id)
