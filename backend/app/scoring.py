"""Deterministic scoring. No LLM here: every fact sentence is built from the source-derived JSON data
(app/test_data) and the user's answers. These facts are the only material the narrative layer may use."""

import re

from . import insights as ins
from .catalog import load


class AnswerError(ValueError):
    pass


def _require(answers: dict, ids: list[str], allowed=None) -> None:
    missing = [i for i in ids if i not in answers or answers[i] in (None, "")]
    if missing:
        raise AnswerError(f"{len(missing)} question(s) unanswered")
    if allowed is not None:
        bad = [i for i in ids if answers[i] not in allowed]
        if bad:
            raise AnswerError(f"invalid answer for {bad[0]}")


def _join(words: list[str]) -> str:
    words = [w for w in words if w]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _compare(pct: float, n: int) -> str:
    if pct >= 50:
        return f"higher than about {min(99, max(1, round(pct)))}% of the {n:,} people in the Open Psychometrics comparison sample"
    return f"lower than about {min(99, max(1, round(100 - pct)))}% of the {n:,} people in the Open Psychometrics comparison sample"


# ------------------------------------------------------------------ Big Five (IPIP-50)

def score_big_five(answers: dict) -> dict:
    data = load("big_five.json")
    items = data["items"]
    _require(answers, [i["id"] for i in items], allowed={1, 2, 3, 4, 5})
    bands = data["level_bands"]
    labels = {s["value"]: s["label"] for s in data["scale"]}

    traits, facts = [], []
    for code, info in data["factors"].items():
        f_items = [i for i in items if i["factor"] == code]
        raw = sum(answers[i["id"]] if i["key"] == 1 else 6 - answers[i["id"]] for i in f_items)
        norm = data["norms"][code]
        pct = norm["percentile_by_score"][str(raw)]
        level = "higher" if pct > bands["high_above_percentile"] else "lower" if pct < bands["low_below_percentile"] else "average"
        traits.append({"code": code, "name": info["name"], "score": raw, "min": 10, "max": 50,
                       "percentile": pct, "level": level, "definition": info["definition"]})

        facts.append(f"{info['name']}: raw score {raw} out of 50, {_compare(pct, norm['n'])} ({level} range).")
        if level == "higher":
            facts.append(f"In personality research (John, Naumann & Soto, 2008), people at the high end of "
                         f"{info['name']} are described with words such as {_join(info['high'][:4])}.")
        elif level == "lower":
            facts.append(f"In personality research (John, Naumann & Soto, 2008), people at the low end of "
                         f"{info['name']} are described with words such as {_join(info['low'][:4])}.")
        else:
            facts.append(f"An average-range {info['name']} score means neither end of this trait stands out strongly.")
        facts.append(f"Definition of {info['name']} (John, Naumann & Soto, 2008): {info['definition']}")

    # The person's own strongest self-descriptions, quoted verbatim
    strongest = [i for i in items if answers[i["id"]] == 5][:4]
    if strongest:
        quoted = "; ".join(f"\"{i['text'].rstrip('.')}\"" for i in strongest)
        facts.append(f"Statements you rated '{labels[5]}' about yourself include: {quoted}.")
    rejected = [i for i in items if answers[i["id"]] == 1][:3]
    if rejected:
        quoted = "; ".join(f"\"{i['text'].rstrip('.')}\"" for i in rejected)
        facts.append(f"Statements you rated '{labels[1]}' about yourself include: {quoted}.")

    top = max(traits, key=lambda t: abs(t["percentile"] - 50))  # furthest from the average
    notes_ins = ins.big_five(traits)
    facts += ins.as_facts(notes_ins, "What research says about your trait levels")
    return {
        "insights": notes_ins,
        "headline": f"Most distinctive trait: {top['name']} ({_ordinal(max(1, round(top['percentile'])))} percentile)",
        "traits": traits,
        "norm_n": data["norms"]["E"]["n"],
        "facts": facts,
        "notes": [bands["note"]],
    }


# ------------------------------------------------------------------ OEJTS (MBTI alternative)

def _strength(distance: int) -> str:
    # App convention: distance from the midpoint (max 16)
    return "slight" if distance <= 4 else "moderate" if distance <= 10 else "clear"


def score_oejts(answers: dict) -> dict:
    data = load("oejts.json")
    items = data["items"]
    _require(answers, [i["id"] for i in items], allowed={1, 2, 3, 4, 5})
    mid = data["scoring"]["midpoint"]

    dims, letters, facts = [], [], []
    for code, info in data["dimensions"].items():
        a, b = info["poles"]  # e.g. I, E
        d_items = [i for i in items if i["dimension"] == code]
        # score toward pole b: value as-is when the right statement is pole b, else reversed
        toward_b = sum(answers[i["id"]] if i["right_pole"] == b else 6 - answers[i["id"]] for i in d_items)
        if toward_b > mid:
            pole, score = b, toward_b
        elif toward_b < mid:
            pole, score = a, 48 - toward_b  # mirror so the score reads toward the chosen pole
        else:
            pole, score = None, mid
        distance = abs(toward_b - mid)
        strength = _strength(distance) if pole else "balanced"
        letters.append(pole or "X")
        dims.append({"code": code, "poles": [a, b], "names": info["names"], "chosen": pole, "score": score,
                     "toward_b": toward_b, "min": 8, "max": 40, "strength": strength,
                     "definition": info["definition"]})
        if pole:
            facts.append(f"{info['names'][a]} vs {info['names'][b]}: you lean {info['names'][pole]} ({pole}), a "
                         f"{strength} preference (score {score} of 40 toward {info['names'][pole]}; 24 is the midpoint).")
        else:
            facts.append(f"{info['names'][a]} vs {info['names'][b]}: exactly balanced (24 of 40), no preference.")
        facts.append(f"Definition ({info['names'][a]}/{info['names'][b]}, Open Psychometrics): {info['definition']}")

        # Their most emphatic answers on this dimension, quoted
        emphatic = [i for i in d_items if answers[i["id"]] in (1, 5)][:2]
        for i in emphatic:
            chosen, other = (i["right"], i["left"]) if answers[i["id"]] == 5 else (i["left"], i["right"])
            facts.append(f"You described yourself fully as \"{chosen}\" rather than \"{other}\".")

    type_code = "".join(letters)
    notes_ins = ins.jungian(dims)
    facts += ins.as_facts(notes_ins, "What the type literature says about your preferences")
    facts.insert(0, f"Your four-letter type on the Open Extended Jungian Type Scales is {type_code}"
                    + (" (X marks a dimension with no preference)." if "X" in type_code else "."))
    return {
        "headline": f"Type {type_code}",
        "insights": notes_ins,
        "type": type_code,
        "dimensions": dims,
        "facts": facts,
        "notes": ["Preference strength is an app convention: 1-4 points from the midpoint = slight, 5-10 = moderate, "
                  "11-16 = clear.", data["trademark_note"]],
    }


# ------------------------------------------------------------------ RMET

def score_rmet(answers: dict) -> dict:
    data = load("rmet.json")
    items = [i for i in data["items"] if not i["practice"]]
    _require(answers, [i["id"] for i in items])
    for i in items:
        if answers[i["id"]] not in i["options"]:
            raise AnswerError(f"invalid answer for {i['id']}")

    correct = [i for i in items if answers[i["id"]] == i["answer"]]
    score = len(correct)
    gp = data["norms"]["groups"][0]
    z = (score - gp["mean"]) / gp["sd"]
    band = "above the typical range" if z > 1 else "below the typical range" if z < -1 else "within the typical range"
    low, high = round(gp["mean"] - gp["sd"], 1), round(gp["mean"] + gp["sd"], 1)

    facts = [
        f"You chose the consensus word on {score} of 36 photographs.",
        f"In Baron-Cohen et al. (2001), general-population adults (n={gp['n']}) averaged {gp['mean']} out of 36 "
        f"(SD {gp['sd']}); one standard deviation either side is {low} to {high}. Your score is {band}.",
        "In this test each photo shows only the eye region, and the task is to judge what the person is thinking or "
        "feeling. The correct word for each photo was set by agreement among a large majority of judges.",
    ]
    missed = [i for i in items if answers[i["id"]] != i["answer"]][:4]
    if missed:
        facts.append("Examples where your choice differed from the consensus: "
                     + "; ".join(f"photo {i['n']}: chose \"{answers[i['id']]}\", consensus \"{i['answer']}\""
                                 for i in missed) + ".")
    notes_ins = ins.rmet()
    facts += ins.as_facts(notes_ins, "What this test is about")
    return {
        "headline": f"{score} / 36 correct",
        "insights": notes_ins,
        "score": score,
        "max": 36,
        "band": band,
        "norms": data["norms"]["groups"],
        "facts": facts,
        "notes": [data["disclaimer"]],
    }


# ------------------------------------------------------------------ Rorschach (popular responses only)

def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z\-]*", text.lower()))


def _one_edit(a: str, b: str) -> bool:
    """True if a and b differ by exactly one insertion, deletion or substitution."""
    if abs(len(a) - len(b)) > 1 or a == b:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
        else:
            i += 1
            j += 1
    return edits + (len(b) - j) <= 1


def _match(words: set[str], terms: list[str]) -> str | None:
    """Exact word match, or a one-letter typo for words of 6+ letters (e.g. 'chamaleon' -> 'chameleon')."""
    if words & set(terms):
        return "word"
    for w in words:
        if len(w) >= 6 and any(len(t) >= 6 and _one_edit(w, t) for t in terms):
            return "spelling"
    return None


def score_rorschach(answers: dict) -> dict:
    data = load("rorschach.json")
    cards = data["cards"]
    _require(answers, [c["id"] for c in cards])
    for c in cards:
        if not isinstance(answers[c["id"]], str) or len(answers[c["id"]]) > 500:
            raise AnswerError(f"invalid answer for {c['id']}")

    results = []
    for c in cards:
        text = answers[c["id"]].strip()
        words = _words(text)
        hows = {label: _match(words, terms) for label, terms in c["match_terms"].items()}
        matched = [label for label, how in hows.items() if how]
        results.append({"card": c["roman"], "id": c["id"], "answer": text, "matched": matched,
                        "how": hows[matched[0]] if matched else None,
                        "popular": [p["text"] for p in c["popular_responses"] if p["text"] != "none"]})

    hits = [r for r in results if r["matched"]]
    misses = [r for r in results if not r["matched"]]
    facts = [
        f"Your descriptions matched a published 'popular' response on {len(hits)} of the 10 inkblot cards"
        + (f" (cards {_join([r['card'] for r in hits])})." if hits else "."),
        data["popular_definition"],
    ]
    for r in hits[:4]:
        facts.append(f"On card {r['card']} you saw \"{r['answer'][:80]}\", which matches the popular response "
                     f"\"{r['matched'][0]}\".")
    if misses:
        facts.append("On card(s) " + _join([r["card"] for r in misses]) + " your perceptions differed from the "
                     "published popular responses: " + "; ".join(f"card {r['card']}: \"{r['answer'][:80]}\""
                                                               for r in misses[:4] if r["answer"]) + ".")
    facts.append("A full Rorschach assessment also codes location, determinants and form quality, which requires a "
                 "trained examiner. This result only describes how often your perceptions matched the most common "
                 "ones.")
    notes_ins = []
    for r in results:
        card_notes = ins.rorschach_card(r["card"])
        r["card_note"] = card_notes[0]["text"] if card_notes else None
        notes_ins += card_notes
        if card_notes and r["answer"]:
            facts.append(f"Card {r['card']} - you saw \"{r['answer'][:80]}\". What the literature says about this card "
                         f"(research summary, Wikipedia \"Rorschach test\"): \"{card_notes[0]['text']}\"")
    return {
        "headline": f"{len(hits)} / 10 popular responses",
        "insights": notes_ins,
        "popular_count": len(hits),
        "cards": results,
        "facts": facts,
        "notes": [data["matching_note"]],
    }


# ------------------------------------------------------------------ shared helpers for norm-based scales

def _level(pct: float) -> str:
    # App convention shared by all norm-referenced scales
    return "higher" if pct > 70 else "lower" if pct < 30 else "average"


BAND_NOTE = ("Levels are an app convention: below the 30th percentile = lower, 30th-70th = average range, above the "
             "70th = higher, relative to the comparison sample (self-selected online test-takers).")


# ------------------------------------------------------------------ Holland Code (RIASEC)

def score_riasec(answers: dict) -> dict:
    data = load("riasec.json")
    items = data["items"]
    _require(answers, [i["id"] for i in items], allowed={1, 2, 3, 4, 5})
    labels = {s["value"]: s["label"] for s in data["scale"]}

    areas = []
    for t, info in data["types"].items():
        raw = sum(answers[i["id"]] for i in items if i["type"] == t)
        norm = data["norms"][t]
        pct = norm["percentile_by_score"][str(raw)]
        areas.append({"code": t, "name": info["name"], "score": raw, "min": 8, "max": 40, "percentile": pct,
                      "level": _level(pct), "work": info["work"], "occupations": info["occupations"]})
    ranked = sorted(areas, key=lambda a: (a["score"], a["percentile"]), reverse=True)
    code = "".join(a["code"] for a in ranked[:3])
    n = data["norms"]["R"]["n"]

    facts = [f"Your Holland code (your three highest interest areas, in order) is {code}: "
             + ", ".join(a["name"] for a in ranked[:3]) + "."]
    for a in ranked[:3]:
        facts.append(f"{a['name']} interest: score {a['score']} out of 40, {_compare(a['percentile'], n)}.")
        facts.append(f"O*NET describes {a['name']} work: {a['work']} {a['occupations']}")
    low = ranked[-1]
    facts.append(f"Your lowest interest area is {low['name']} (score {low['score']} out of 40).")
    liked = [i for i in items if answers[i["id"]] == 5][:4]
    if liked:
        facts.append(f"Tasks you rated '{labels[5]}' include: " + "; ".join(f"\"{i['text']}\"" for i in liked) + ".")
    nicknames, careers = ins.riasec(code)
    facts.append("In Holland's model the six types have nicknames; yours are: " + "; ".join(nicknames)
                 + " (research summary, Wikipedia \"Holland Codes\").")
    if careers:
        facts.append("Careers that Wikipedia's \"Holland Codes\" article lists for these interest areas, ranked by how "
                     "many of your code's letters they share: "
                     + ", ".join(f"{c['title']} ({c['letters']})" for c in careers) + ".")
    return {
        "headline": f"Holland code {code}",
        "careers": careers,
        "nicknames": nicknames,
        "code": code,
        "areas": areas,
        "norm_n": n,
        "facts": facts,
        "notes": ["Interest scores describe what you would enjoy doing, not your ability or what you should "
                  "choose. Holland code = your three highest-scoring areas.", BAND_NOTE],
    }


# ------------------------------------------------------------------ Rosenberg Self-Esteem Scale

def score_rse(answers: dict) -> dict:
    data = load("rse.json")
    items = data["items"]
    _require(answers, [i["id"] for i in items], allowed={0, 1, 2, 3})
    total = sum(answers[i["id"]] if i["key"] == 1 else 3 - answers[i["id"]] for i in items)
    norm = data["norms"]
    pct = norm["percentile_by_score"][str(total)]
    level = _level(pct)

    facts = [
        f"Your Rosenberg Self-Esteem Scale score is {total} out of 30 (higher scores mean higher self-esteem).",
        f"That is {_compare(pct, norm['n'])} ({level} range).",
        "About the scale: " + data["about"],
    ]
    agreed = [i for i in items if i["key"] == 1 and answers[i["id"]] == 3][:3]
    if agreed:
        facts.append("Statements you strongly agreed with include: "
                     + "; ".join(f"\"{i['text'].rstrip('.')}\"" for i in agreed) + ".")
    notes_ins = ins.self_esteem(level)
    facts += ins.as_facts(notes_ins, "What research says about self-esteem")
    return {
        "headline": f"Self-esteem {total} / 30",
        "insights": notes_ins,
        "score": total,
        "max": 30,
        "percentile": pct,
        "level": level,
        "norm": {"mean": norm["mean"], "sd": norm["sd"], "n": norm["n"]},
        "facts": facts,
        "notes": [BAND_NOTE, "How we feel about ourselves can be hard. If you're struggling, talking with someone "
                  "you trust or a qualified professional can help."],
    }


# ------------------------------------------------------------------ Experiences in Close Relationships

def score_ecr(answers: dict) -> dict:
    data = load("ecr.json")
    items = data["items"]
    _require(answers, [i["id"] for i in items], allowed={1, 2, 3, 4, 5})
    d = data["definitions"]

    dims = {}
    for scale in ("avoidance", "anxiety"):
        raw = sum(answers[i["id"]] if i["key"] == 1 else 6 - answers[i["id"]] for i in items if i["scale"] == scale)
        norm = data["norms"][scale]
        pct = norm["percentile_by_score"][str(raw)]
        dims[scale] = {"score": raw, "min": 18, "max": 90, "percentile": pct, "level": _level(pct),
                       "median": norm["median"]}

    n = data["norms"]["anxiety"]["n"]
    facts = []
    for scale, label in (("anxiety", "Attachment-related anxiety"), ("avoidance", "Attachment-related avoidance")):
        x = dims[scale]
        facts.append(f"{label}: score {x['score']} (range 18-90), {_compare(x['percentile'], n)} ({x['level']} range).")
        if x["level"] == "higher":
            facts.append(f"Fraley (attachment researcher): {d[scale + '_high']}")
        elif x["level"] == "lower":
            facts.append(f"Fraley (attachment researcher): {d[scale + '_low']}")
    # Quadrant around the sample medians -> one of Bartholomew's four styles. Brennan et al. (1998) found their
    # four clusters on these two dimensions "corresponded conceptually to Bartholomew's four types"; Fraley defines
    # secure = low/low and dismissing = high avoidance + low anxiety, and calls the other avoidant group fearful.
    high_anx = dims["anxiety"]["percentile"] >= 50
    high_avo = dims["avoidance"]["percentile"] >= 50
    style = {(False, False): "secure", (True, False): "anxious-preoccupied",
             (False, True): "dismissive-avoidant", (True, True): "fearful-avoidant"}[(high_anx, high_avo)]
    outer = {"secure": ("lower", "lower"), "anxious-preoccupied": ("higher", "lower"),
             "dismissive-avoidant": ("lower", "higher"), "fearful-avoidant": ("higher", "higher")}[style]
    clear = (dims["anxiety"]["level"], dims["avoidance"]["level"]) == outer
    strength = "clearly" if clear else "leans toward"
    style_label = style.replace("-", " ")
    facts.append(f"Combining both dimensions, your scores {'clearly fall in' if clear else 'lean toward'} the "
                 f"{style_label} region of the attachment map (anxiety {'above' if high_anx else 'below'} and avoidance "
                 f"{'above' if high_avo else 'below'} the sample median"
                 + ("" if clear else "; at least one score is in the average range, so this is a tendency, not a type")
                 + ").")
    notes_ins = ins.attachment(style)
    facts += ins.as_facts(notes_ins, f"What research says about the {style_label} style")
    return {
        "style": style,
        "style_strength": strength,
        "insights": notes_ins,
        "headline": f"Anxiety {_ordinal(round(dims['anxiety']['percentile']))} · Avoidance "
                    f"{_ordinal(round(dims['avoidance']['percentile']))} percentile",
        "dimensions": dims,
        "norm_n": n,
        "facts": facts,
        "notes": [data["scale_note"], BAND_NOTE, "Attachment is measured on two continuous dimensions. The style shown is the region your scores "
                  "fall in; it is called a tendency unless both scores are outside the average range."],
    }


async def score(test_id: str, answers: dict) -> dict:
    if test_id == "big-five":
        return score_big_five(answers)
    if test_id == "jungian-type":
        return score_oejts(answers)
    if test_id == "rmet":
        return score_rmet(answers)
    if test_id == "rorschach":
        return score_rorschach(answers)
    if test_id == "riasec":
        return score_riasec(answers)
    if test_id == "self-esteem":
        return score_rse(answers)
    if test_id == "attachment":
        return score_ecr(answers)
    raise KeyError(test_id)
