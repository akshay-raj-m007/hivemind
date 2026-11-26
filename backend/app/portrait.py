"""Deterministic, structured "portraits" built only from verified data.

Each builder returns:
    {"title": str, "tagline": str, "sections": [{"heading", "icon", "body", "bullets", "quotes"}]}
- body: a paragraph (the only part the optional AI step may reword)
- bullets: short factual lines (never reworded)
- quotes: verbatim research quotes [{"text", "source", "url"}] (never reworded)

Research quotes come from app/test_data/insights.json (each verified against its source). Levels such as
"higher/average/lower" use the app's percentile convention (<30th, 30th-70th, >70th) unless stated otherwise.
"""

from __future__ import annotations

from .catalog import load

LQ, RQ = "“", "”"


def _q(text: str) -> str:
    return f"{LQ}{text.strip().rstrip('.')}{RQ}"


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _ord(n: float) -> str:
    n = min(99, max(1, round(n)))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _cmp(pct: float) -> str:
    if pct >= 50:
        return f"higher than about {min(99, max(1, round(pct)))}% of people"
    return f"lower than about {min(99, max(1, round(100 - pct)))}% of people"


def _ins() -> dict:
    return load("insights.json")


def _quotes(items: list[dict]) -> list[dict]:
    src = _ins()["sources"]
    out, seen = [], set()
    for i in items:
        if i["text"] in seen:
            continue
        seen.add(i["text"])
        out.append({"text": i["text"], "source": src[i["source"]]["title"], "url": src[i["source"]]["url"]})
    return out


def S(heading: str, icon: str, body: str = "", bullets: list[str] | None = None, quotes: list[dict] | None = None):
    return {"heading": heading, "icon": icon, "body": body.strip(), "bullets": bullets or [], "quotes": quotes or []}


LEVEL_WORDS = {"higher": "high", "average": "middle", "lower": "low"}


# ------------------------------------------------------------------ Big Five

def big_five(result: dict, answers: dict) -> dict:
    data = load("big_five.json")
    ins = _ins()["big-five"]
    labels = {s["value"]: s["label"] for s in data["scale"]}
    traits = sorted(result["traits"], key=lambda t: abs(t["percentile"] - 50), reverse=True)
    top = traits[0]

    def echo(code: str, level: str) -> str | None:
        for it in data["items"]:
            if it["factor"] != code:
                continue
            a = answers.get(it["id"])
            up = (it["key"] == 1 and a == 5) or (it["key"] == -1 and a == 1)
            down = (it["key"] == 1 and a == 1) or (it["key"] == -1 and a == 5)
            if (level == "higher" and up) or (level == "lower" and down):
                return f"You rated {_q(it['text'])} as {labels[a]}."
        return None

    sections = [S(
        "At a glance", "spark",
        f"Your most distinctive trait is {top['name']}, where your score is {_cmp(top['percentile'])} in a sample of "
        f"{result['norm_n']:,} test-takers. "
        + (f"Your {_join([t['name'] for t in traits if t['level'] == 'average'])} sit in the average range, so "
           "neither end of those traits stands out strongly." if any(t["level"] == "average" for t in traits) else ""),
        [f"{t['name']}: {LEVEL_WORDS[t['level']]} ({_ord(t['percentile'])} percentile)" for t in traits])]

    for t in traits:
        if t["level"] == "average":
            continue
        quotes = ins[t["code"]].get(t["level"], [])
        e = echo(t["code"], t["level"])
        sections.append(S(
            f"{t['name']}: the {LEVEL_WORDS[t['level']]} end", "trait",
            f"You are {_cmp(t['percentile'])} on {t['name']}. Here is how the research summary describes people at "
            f"this end of the trait." + (f" {e}" if e else ""),
            quotes=_quotes(quotes)))

    adjectives = [a for t in traits if t["level"] == "higher" for a in load("big_five.json")["factors"][t["code"]]["high"][:3]]
    sections.append(S(
        "How to read your levels", "compass",
        "Each trait is compared with the norm sample: below the 30th percentile counts as low, the 30th to 70th as "
        "the middle, and above the 70th as high (an app convention). A low score is not a bad score: each end of a "
        "trait has its own strengths."
        + (f" The words researchers use for the traits where you score highest: {_join(adjectives)} (John, "
           f"Naumann & Soto, 2008)." if adjectives else ""),
        quotes=_quotes(ins["general"])))
    return {"title": f"{top['name']} stands out",
            "tagline": f"Most distinctive: {top['name']} ({_ord(top['percentile'])} percentile)", "sections": sections}


# ------------------------------------------------------------------ OEJTS

def jungian(result: dict, answers: dict) -> dict:
    data = load("oejts.json")
    ins = _ins()["jungian-type"]
    strength_text = {"slight": "a slight lean", "moderate": "a moderate preference", "clear": "a clear preference"}
    letter_bullets, letter_sections = [], []
    for d in result["dimensions"]:
        names, code = d["names"], d["code"]
        a_pole, b_pole = d["poles"]
        if not d["chosen"]:
            letter_bullets.append(f"X: exactly balanced between {names[a_pole]} and {names[b_pole]}")
            letter_sections.append(S(
                f"Balanced: {names[a_pole]} and {names[b_pole]}", "balance",
                f"You scored exactly in the middle on this dimension, so neither {names[a_pole]} nor "
                f"{names[b_pole]} wins out. In the words of the test's author, this dimension is about this: "
                f"{_q(data['dimensions'][code]['definition'])}."))
            continue
        pole, other = d["chosen"], (b_pole if d["chosen"] == a_pole else a_pole)
        letter_bullets.append(f"{pole}: {names[pole]} ({strength_text[d['strength']]})")
        own = []
        for it in data["items"]:
            if it["dimension"] != code:
                continue
            v = answers.get(it["id"])
            if v in (4, 5) and it["right_pole"] == pole:
                own.append((v == 5, f"{_q(it['right'])} rather than {_q(it['left'])}"))
            elif v in (1, 2) and it["left_pole"] == pole:
                own.append((v == 1, f"{_q(it['left'])} rather than {_q(it['right'])}"))
        own.sort(key=lambda x: not x[0])
        quotes = ins.get(pole, []) + [q for q in ins["extra"].get(pole, [])
                                      if not q["text"].startswith(("Jung identified", "Myers and Briggs added"))]
        letter_sections.append(S(
            f"{pole} · {names[pole]}", "letter",
            f"You show {strength_text[d['strength']]} for {names[pole]} over {names[other]}. The test's author "
            f"describes this dimension like this: {_q(data['dimensions'][code]['definition'])}."
            + (" In your own answers you described yourself as:" if own else ""),
            [o for _, o in own[:3]], _quotes(quotes)))

    mapping = {"I": "lower Big Five extraversion", "E": "higher Big Five extraversion",
               "P": "lower Big Five conscientiousness", "J": "higher Big Five conscientiousness",
               "F": "higher Big Five agreeableness", "T": "lower Big Five agreeableness",
               "N": "higher Big Five openness", "S": "lower Big Five openness"}
    links = [f"{d['chosen']} tends to go with {mapping[d['chosen']]}" for d in result["dimensions"]
             if d["chosen"] in mapping]
    sections = [S(
        f"Your type: {result['type']}", "spark",
        f"Your four letters come from four separate scales. Each letter shows which side you lean toward and how "
        f"strongly. {'An X marks a dimension where you came out perfectly balanced.' if 'X' in result['type'] else ''}",
        letter_bullets), *letter_sections]
    if links:
        sections.append(S(
            "How your type connects to the Big Five", "link",
            "Research comparing the MBTI with the Big Five (McCrae & Costa, 1989) found that four of the letters line "
            "up with Big Five traits. For your letters: " + "; ".join(links) + ".",
            quotes=_quotes(ins["big5_link"] + ins["dimensions_note"])))
    sections.append(S(
        "How to read the strengths", "compass",
        "Each dimension runs from 8 to 40 with 24 as the midpoint. Hive calls 1-4 points from the midpoint a slight "
        "lean, 5-10 a moderate preference and 11-16 a clear preference (an app convention). Slight leans mean you "
        "use both sides comfortably.", quotes=_quotes(ins["general"])))
    names_list = [d["names"][d["chosen"]] for d in result["dimensions"] if d["chosen"]]
    return {"title": f"Type {result['type']}", "tagline": _join(names_list), "sections": sections}


# ------------------------------------------------------------------ RMET

def rmet(result: dict, answers: dict) -> dict:
    data = load("rmet.json")
    ins = _ins()["rmet"]
    gp = result["norms"][0]
    low, high = round(gp["mean"] - gp["sd"], 1), round(gp["mean"] + gp["sd"], 1)
    meaning = {
        "above the typical range": "You picked the same word as the majority of judges more often than most adults "
                                   "do: your reading of these eye expressions closely matches the common one.",
        "within the typical range": "You picked the same word as the majority of judges about as often as most "
                                    "adults do.",
        "below the typical range": "Your readings of these eye expressions often differed from the word most judges "
                                   "agreed on. That can reflect many things, including unfamiliar words, the "
                                   "photographs themselves or simply answering quickly.",
    }[result["band"]]
    diffs = [i for i in data["items"] if not i["practice"] and answers.get(i["id"]) not in (None, i["answer"])][:4]
    sections = [
        S("Your score", "spark",
          f"You matched the consensus word on {result['score']} of 36 photographs, {result['band']} for adults.",
          [f"Your score: {result['score']} of 36",
           f"General-population average: {gp['mean']} (Baron-Cohen et al., 2001)",
           f"Most adults score between {low} and {high}"]),
        S("What your score means", "compass",
          meaning + " Each photo shows only the eyes, and each correct word is the one a large majority of judges "
                    "agreed on."),
        S("The skill behind the test", "brain",
          "This test is used as a measure of theory of mind, the everyday skill of working out what someone else is "
          "thinking or feeling.", quotes=_quotes(ins["general"])),
    ]
    if diffs:
        sections.append(S("Where you saw it differently", "eye",
                          "A few photos where your word differed from the majority's:",
                          [f"Photo {i['n']}: you chose {_q(answers[i['id']])}, most chose {_q(i['answer'])}" for i in diffs]))
    sections.append(S("Keep in mind", "info",
                      "Treat your score as a snapshot rather than a verdict. It is not a diagnostic test.",
                      quotes=_quotes(ins["caveat"])))
    return {"title": f"{result['score']} of 36: reading the mind in the eyes", "tagline": result["band"].capitalize(),
            "sections": sections}


# ------------------------------------------------------------------ Rorschach

def rorschach(result: dict, answers: dict) -> dict:
    ins = _ins()["rorschach"]
    cards = result["cards"]
    hits = [c for c in cards if c["matched"]]
    misses = [c for c in cards if not c["matched"] and c["answer"]]
    n = len(hits)
    if n >= 8:
        band, phrase, meaning = "mostly conventional", "a mostly conventional way of seeing", (
            "You saw what most people see on nearly every card. Your way of organising these ambiguous shapes "
            "closely follows the shared, common way of seeing them.")
    elif n >= 4:
        band, phrase, meaning = "a mix of common and individual", "a mix of common and individual ways of seeing", (
            "You saw the common percept on some cards and your own on others. Your way of organising these "
            "ambiguous shapes mixes the shared way of seeing with an individual one.")
    else:
        band, phrase, meaning = "mostly individual", "a mostly individual way of seeing", (
            "You rarely saw the most common percept. Your way of organising these ambiguous shapes is mostly your "
            "own rather than the shared, common one.")
    sections = [
        S("Your perception at a glance", "spark",
          f"You gave a popular response on {n} of the 10 cards: {phrase}. {meaning}",
          [f"Popular responses: {n} of 10", f"Individual responses: {10 - n} of 10",
           "Bands (app convention): 0-3 mostly individual, 4-7 a mix, 8-10 mostly conventional"]),
        S("What you saw", "eye",
          "Your popular responses, followed by the cards where you saw something of your own:",
          [f"Card {c['card']}: {_q(c['answer'])} (popular{', spelling' if c.get('how') == 'spelling' else ''})" for c in hits]
          + [f"Card {c['card']}: {_q(c['answer'])} (your own)" for c in misses]),
        S("What the test looks at", "compass",
          "The Rorschach is first of all a test of perception. Popularity is one of the classic ways to read a "
          "record, and what counts as \"common\" also depends on culture.",
          quotes=_quotes(ins["about"])),
    ]
    picks = [c for c in misses if c.get("card_note")][:2] + [c for c in hits if c.get("card_note")][:1]
    if picks:
        sections.append(S("What the literature says about your cards", "book",
                          "Notes from the literature on cards you answered, next to what you saw:",
                          [f"Card {c['card']} (you saw {_q(c['answer'])}): {_q(c['card_note'])}" for c in picks]))
    sections.append(S("How professionals go further", "info",
                      "A trained examiner also codes where on the blot you saw something, what made it look that "
                      "way and how well it fits the shape. Research uses these scores, even with eye tracking. Hive "
                      "only reads popularity, and online self-evaluation has clear limits.",
                      quotes=_quotes(ins["research"] + ins["caveat"])))
    title = {"mostly conventional": "Seeing what others see", "a mix of common and individual":
             "Familiar shapes, individual eyes", "mostly individual": "Your own way of seeing"}[band]
    return {"title": title, "tagline": f"{n} of 10 popular responses", "sections": sections}


# ------------------------------------------------------------------ RIASEC

def riasec(result: dict, answers: dict) -> dict:
    data = load("riasec.json")
    h = _ins()["riasec"]
    code = result["code"]
    areas = sorted(result["areas"], key=lambda a: a["score"], reverse=True)
    nick = [h[c]["nickname"][:-1] if h[c]["nickname"].endswith("s") else h[c]["nickname"] for c in code]
    level_text = {"higher": "high", "average": "middle", "lower": "low"}

    def area_line(a: dict) -> str:
        work = a["work"].replace("Work involves ", "").rstrip(".")
        if a["level"] == "higher":
            return f"{a['name']} ({_ord(a['percentile'])} percentile, high): you would enjoy work that involves {work} more than most people"
        if a["level"] == "lower":
            return f"{a['name']} ({_ord(a['percentile'])} percentile, low): work that involves {work} appeals to you less than to most people"
        return f"{a['name']} ({_ord(a['percentile'])} percentile, middle): about as interested as most people in work that involves {work}"

    high = [a["name"] for a in areas if a["level"] == "higher"]
    mid = [a["name"] for a in areas if a["level"] == "average"]
    low = [a["name"] for a in areas if a["level"] == "lower"]
    summary = []
    if high:
        summary.append(f"Your interests are strongest in {_join(high)}, where you scored higher than most people.")
    if mid:
        summary.append(f"{_join(mid)} {'sits' if len(mid) == 1 else 'sit'} in the middle: about as appealing to you as to most people.")
    if low:
        summary.append(f"{_join(low)} {'appeals' if len(low) == 1 else 'appeal'} to you less than to most people.")

    first = next(a for a in result["areas"] if a["code"] == code[0])
    liked = [i for i in data["items"] if i["type"] == code[0] and answers.get(i["id"]) == 5][:3]
    sections = [
        S(f"Your Holland code: {code}", "spark",
          f"Your three strongest interest areas, in order, are {_join([next(a['name'] for a in areas if a['code'] == c) for c in code])}. "
          f"In Holland's own nicknames for the six types, that makes you a {_join(nick)}.",
          [f"{c} = {h[c]['name']} ({h[c]['nickname']})" for c in code]),
        S("High, middle and low: your six areas", "chart",
          " ".join(summary) + " Your code is built from your raw interest scores (how much you like each kind of "
          "work), while high, middle and low compare you with other people, so the two can differ slightly.",
          [area_line(a) for a in areas]),
        S(f"Your top area: {first['name']}", "trait",
          f"O*NET describes {first['name']} work like this: {_q(first['work'])}. {first['occupations']}"
          + (" You showed it when you said you would enjoy tasks like:" if liked else ""),
          [_q(i["text"]) for i in liked]),
    ]
    if result.get("careers"):
        sections.append(S("Careers to explore", "compass",
                          "Careers that the Holland Codes literature lists for your interest areas, ranked by how many "
                          "of your code's letters they share:",
                          [f"{c['title']} ({c['letters']})" for c in result["careers"][:8]]))
    sections.append(S("How to read your levels", "info",
                      "Each area is compared with over 135,000 people: below the 30th percentile counts as low, the "
                      "30th to 70th as the middle, and above the 70th as high (an app convention). Interests describe "
                      "what you would enjoy doing, not what you are able to do, and the strongest careers usually "
                      "combine your top two or three areas."))
    return {"title": f"{code}: {_join([h[c]['nickname'] for c in code])}",
            "tagline": f"{_join([h[c]['name'] for c in code])}", "sections": sections}


# ------------------------------------------------------------------ Rosenberg Self-Esteem

def self_esteem(result: dict, answers: dict) -> dict:
    data = load("rse.json")
    ins = _ins()["self-esteem"]
    sub = data["subscale_norms"]
    pos = sum(answers[i["id"]] for i in data["items"] if i["key"] == 1)
    neg = sum(3 - answers[i["id"]] for i in data["items"] if i["key"] == -1)
    pos_pct = sub["positive"]["percentile_by_score"][str(pos)]
    neg_pct = sub["negative"]["percentile_by_score"][str(neg)]
    meaning = {
        "higher": "Your answers describe a more positive overall attitude toward yourself than most people's.",
        "average": "Your answers describe an overall attitude toward yourself that is similar to most people's: "
                   "neither unusually positive nor unusually critical.",
        "lower": "Your answers describe a more critical overall attitude toward yourself than most people's right "
                 "now. That is a description of how you feel at the moment, not a judgement of your worth.",
    }[result["level"]]
    agreed = [i for i in data["items"] if i["key"] == 1 and answers.get(i["id"]) in (2, 3)]
    rejected = [i for i in data["items"] if i["key"] == -1 and answers.get(i["id"]) in (0, 1)]
    neg_agreed = sum(1 for i in data["items"] if i["key"] == -1 and answers.get(i["id"]) in (2, 3))

    sections = [
        S("Your score", "spark",
          f"Your self-esteem score is {result['score']} out of 30, {_cmp(result['percentile'])} in the comparison "
          f"sample ({LEVEL_WORDS[result['level']]} range). {meaning}",
          [f"Score: {result['score']} of 30", f"Percentile: {_ord(result['percentile'])}",
           f"Level: {LEVEL_WORDS[result['level']]}"]),
        S("Two sides of self-esteem", "balance",
          "Studies of this scale have found two related factors: self-confidence (agreeing with positive statements "
          "about yourself) and self-deprecation (agreeing with negative ones). Looking at the two halves "
          "separately, where higher always means a more positive self-view:",
          [f"Positive statements (self-confidence): {pos} of 15, {_ord(pos_pct)} percentile",
           f"Negative statements, reversed (freedom from self-deprecation): {neg} of 15, {_ord(neg_pct)} percentile",
           f"You agreed with {neg_agreed} of the 5 negative statements"]),
    ]
    strengths = [f"You agree: {_q(i['text'])}" for i in agreed[:3]] + \
                [f"You disagree: {_q(i['text'])}" for i in rejected[:2]]
    if strengths:
        sections.append(S("Where your answers are strongest", "trait",
                          "The statements where your answers lean most positive:", strengths))
    level_quotes = ins[result["level"]]
    sections.append(S("What research says", "book",
                      {"higher": "The research summary describes people with a healthy level of self-esteem as "
                                 "people who:",
                       "average": "Two things research has found about how self-esteem works:",
                       "lower": "Two things research has found that are worth knowing:"}[result["level"]],
                      quotes=_quotes(level_quotes[:4] + ins["general"] + ins["development"][:1])))
    sections.append(S("Keep in mind", "info",
                      "Self-esteem can feel different from one period of life to another. If you are struggling with "
                      "how you see yourself, talking with someone you trust or a qualified professional can help.",
                      quotes=_quotes(ins["development"][1:])))
    return {"title": f"Self-esteem: {result['score']} of 30",
            "tagline": f"{LEVEL_WORDS[result['level']].capitalize()} range ({_ord(result['percentile'])} percentile)",
            "sections": sections}


# ------------------------------------------------------------------ Attachment (ECR)

def attachment(result: dict, answers: dict) -> dict:
    data = load("ecr.json")
    ins = _ins()["attachment"]
    d = data["definitions"]
    dims = result["dimensions"]

    def where(scale: str) -> str:
        x = dims[scale]
        side = "the high end" if x["percentile"] >= 50 else "the low end"
        strength = "clearly toward" if x["level"] in ("higher", "lower") else "slightly toward"
        return f"{_ord(x['percentile'])} percentile, {strength} {side}"

    style = result["style"]
    label = style.replace("-", " ")
    clear = result["style_strength"] == "clearly"
    sections = [
        S("Your two dimensions", "chart",
          f"Attachment is measured on two dimensions. Your anxiety is {_cmp(dims['anxiety']['percentile'])} and your "
          f"avoidance is {_cmp(dims['avoidance']['percentile'])}.",
          [f"Anxiety: {where('anxiety')}", f"Avoidance: {where('avoidance')}"]),
        S("What each dimension means", "compass",
          "Here is how attachment researcher R. Chris Fraley describes each end. Your scores sit closer to the "
          f"{'high' if dims['anxiety']['percentile'] >= 50 else 'low'} end of anxiety and the "
          f"{'high' if dims['avoidance']['percentile'] >= 50 else 'low'} end of avoidance.",
          [f"High anxiety: {_q(d['anxiety_high'])}", f"Low anxiety: {_q(d['anxiety_low'])}",
           f"High avoidance: {_q(d['avoidance_high'])}", f"Low avoidance: {_q(d['avoidance_low'])}"]),
        S(f"Your region: {label}", "spark",
          f"Together, your scores {'clearly fall in' if clear else 'lean toward'} the {label} region of the "
          "attachment map."
          + ("" if clear else " Because at least one score is in the average range, read this as a tendency rather "
                              "than a type."),
          quotes=_quotes(ins[style] + ins["more"].get(style, []))),
        S("In relationships", "heart",
          "What research has found about attachment and relationship satisfaction:",
          quotes=_quotes(ins["outcomes"])),
        S("Attachment can change", "info",
          "Attachment styles are fairly stable, but not fixed.", quotes=_quotes(ins["general"])),
    ]
    return {"title": f"Attachment: {'clearly' if clear else 'leaning'} {label}",
            "tagline": f"Anxiety {_ord(dims['anxiety']['percentile'])} · Avoidance {_ord(dims['avoidance']['percentile'])} percentile",
            "sections": sections}


BUILDERS = {"big-five": big_five, "jungian-type": jungian, "rmet": rmet, "rorschach": rorschach,
            "riasec": riasec, "self-esteem": self_esteem, "attachment": attachment}


def build(test_id: str, result: dict, answers: dict) -> dict:
    return BUILDERS[test_id](result, answers)
