"""Select verified research quotes (app/test_data/insights.json) that apply to a given result.
Selection is deterministic; the quotes themselves are verbatim from their sources."""

from .catalog import load


def _data() -> dict:
    return load("insights.json")


def _pack(quotes: list[dict]) -> list[dict]:
    srcs = _data()["sources"]
    return [{"text": qt["text"], "source": srcs[qt["source"]]["title"], "url": srcs[qt["source"]]["url"]}
            for qt in quotes]


def as_facts(items: list[dict], lead: str) -> list[str]:
    return [f"{lead} (research summary, Wikipedia \"{i['source']}\"): \"{i['text']}\"" for i in items]


def big_five(traits: list[dict]) -> list[dict]:
    spec = _data()["big-five"]
    picked = []
    for t in traits:
        picked += spec[t["code"]].get(t["level"], [])
    return _pack(picked + spec["general"])


def jungian(dims: list[dict]) -> list[dict]:
    spec = _data()["jungian-type"]
    picked, seen = [], set()
    for d in dims:
        if d["chosen"] and d["strength"] != "slight":
            for qt in spec[d["chosen"]]:
                if qt["text"] not in seen:
                    seen.add(qt["text"])
                    picked.append(qt)
    return _pack(picked + spec["general"])


def riasec(code: str) -> tuple[list[str], list[dict]]:
    """Holland nicknames for the code + careers from the Holland Codes article that share the most letters."""
    h = _data()["riasec"]
    nick = [f"{h[c]['name']} = \"{h[c]['nickname']}\"" for c in code]
    scored = {}
    for c in code:
        for career in h[c]["careers"]:
            overlap = len(set(career["letters"]) & set(code))
            # prefer careers whose first letter is higher in the person's code
            rank = (overlap, -code.index(career["letters"][0]) if career["letters"][0] in code else -9)
            if career["title"] not in scored or rank > scored[career["title"]][0]:
                scored[career["title"]] = (rank, career["letters"])
    best = sorted(scored.items(), key=lambda kv: kv[1][0], reverse=True)[:8]
    careers = [{"title": t, "letters": "".join(letters)} for t, (_, letters) in best]
    return nick, careers


def self_esteem(level: str) -> list[dict]:
    spec = _data()["self-esteem"]
    return _pack(spec[level] + spec["general"])


ATTACHMENT_STYLE_NAMES = {
    "secure": "secure",
    "anxious-preoccupied": "anxious-preoccupied",
    "dismissive-avoidant": "dismissive-avoidant",
    "fearful-avoidant": "fearful-avoidant",
}


def attachment(style: str) -> list[dict]:
    spec = _data()["attachment"]
    return _pack(spec[style] + spec["general"])


def rmet() -> list[dict]:
    spec = _data()["rmet"]
    return _pack(spec["general"] + spec["caveat"])


def rorschach_card(roman: str) -> list[dict]:
    return _pack(_data()["rorschach"].get(roman, []))
