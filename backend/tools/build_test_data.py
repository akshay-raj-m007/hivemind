"""
Build Hive's test content from primary, citable sources - nothing is hand-invented.

Run from the backend folder:
    ../venv/Scripts/python tools/build_test_data.py

Outputs
    backend/app/test_data/{big_five,oejts,rmet,rorschach}.json
    frontend/public/tests/rmet/*.jpg           (Reading the Mind in the Eyes stimuli)
    frontend/public/tests/rorschach/*.jpg      (Rorschach plates, public domain)

Every JSON file carries a "sources" list describing exactly where each piece came from.
Downloads go to a temporary folder and are parsed as data only.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import statistics
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

try:  # verify TLS with the OS certificate store (handles servers with incomplete chains)
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[2]
DATA_OUT = ROOT / "backend" / "app" / "test_data"
IMG_OUT = ROOT / "frontend" / "public" / "tests"
UA = {"User-Agent": "HiveTestDataBuilder/1.0 (educational, non-commercial)"}
# Wikimedia's robot policy requires contact info (a URL or email) in the User-Agent.
# Set HIVE_BUILD_CONTACT=<your site or email> to fetch Rorschach data from Wikimedia directly,
# or pass --rorschach-cache=DIR containing rorschach.wiki and card_01.jpg ... card_10.jpg.
WIKIMEDIA_CONTACT = os.getenv("HIVE_BUILD_CONTACT", "").strip()
RORSCHACH_CACHE: Path | None = None
TMP = Path(tempfile.mkdtemp(prefix="hive_build_"))


def fetch(url: str, *, retries: int = 6, wait: float = 15.0, min_size: int = 0) -> bytes:
    """GET with retries/backoff. min_size guards against small error pages served with HTTP 200."""
    headers = dict(UA)
    if "wikimedia.org" in url or "wikipedia.org" in url:
        if not WIKIMEDIA_CONTACT:
            raise RuntimeError("Wikimedia requires contact info: set HIVE_BUILD_CONTACT or use --rorschach-cache=DIR")
        headers["User-Agent"] = f"HiveTestDataBuilder/1.0 ({WIKIMEDIA_CONTACT}; educational, non-commercial)"
    for attempt in range(1, retries + 1):
        try:
            r = httpx.get(url, headers=headers, timeout=60, follow_redirects=True)
            if r.status_code == 200 and len(r.content) >= min_size:
                return r.content
            print(f"  {url} -> HTTP {r.status_code}, {len(r.content)} bytes (attempt {attempt})")
        except httpx.HTTPError as exc:
            print(f"  {url} -> {exc} (attempt {attempt})")
        time.sleep(wait * attempt)
    raise RuntimeError(f"Could not download {url}")


def write_json(name: str, data: dict) -> None:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    (DATA_OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {name}")


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# --------------------------------------------------------------------------------------
# 1. Big Five - IPIP 50-item Big-Five Factor Markers (public domain) + norms from the
#    Open Psychometrics "BIG5" dataset (19,719 respondents).
# --------------------------------------------------------------------------------------

IPIP_URL = "https://ipip.ori.org/new_ipip-50-item-scale.htm"
BIG5_URL = "http://openpsychometrics.org/_rawdata/BIG5.zip"
JOHN_2008_URL = "https://www.colby.edu/wp-content/uploads/2019/06/John_et_al_2008.pdf"

# IPIP factor numbers -> our codes. Factor IV is keyed as Emotional Stability on IPIP.
IPIP_FACTORS = {"1": "E", "2": "A", "3": "C", "4": "ES", "5": "O"}

# Transcribed from John, Naumann & Soto (2008), Handbook of Personality (3rd ed.), ch. 4:
#   Table 4.2 "conceptual definition" (verbatim), and Table 4.4 "Big-Five prototypes" -
#   the six highest-loading adjectives per pole (low-pole lists exclude the most pejorative
#   entries; all words appear in the table). The build verifies each phrase exists in the PDF.
BIG5_FACTORS = {
    "E": {
        "name": "Extraversion",
        "definition": "Implies an energetic approach toward the social and material world and includes traits "
        "such as sociability, activity, assertiveness, and positive emotionality.",
        "high": ["talkative", "assertive", "active", "energetic", "outgoing", "outspoken"],
        "low": ["quiet", "reserved", "shy", "silent", "retiring"],
    },
    "A": {
        "name": "Agreeableness",
        "definition": "Contrasts a prosocial and communal orientation towards others with antagonism and includes "
        "traits such as altruism, tender-mindedness, trust, and modesty.",
        "high": ["sympathetic", "kind", "appreciative", "affectionate", "soft-hearted", "warm"],
        "low": ["fault-finding", "stern", "cold"],
    },
    "C": {
        "name": "Conscientiousness",
        "definition": "Describes socially prescribed impulse control that facilitates task- and goal-directed "
        "behavior, such as thinking before acting, delaying gratification, following norms and rules, and "
        "planning, organizing, and prioritizing tasks.",
        "high": ["organized", "thorough", "planful", "efficient", "responsible", "reliable"],
        "low": ["careless", "disorderly", "forgetful"],
    },
    "ES": {
        "name": "Emotional Stability",
        "note": "IPIP scores this factor as Emotional Stability, the opposite pole of Neuroticism.",
        "definition": "Contrasts emotional stability and even-temperedness with negative emotionality, such as "
        "feeling anxious, nervous, sad, and tense.",
        # High Emotional Stability = low Neuroticism pole, and vice versa.
        "high": ["stable", "calm", "contented"],
        "low": ["tense", "anxious", "nervous", "moody", "worrying", "touchy"],
    },
    "O": {
        "name": "Openness / Intellect",
        "note": "IPIP labels this factor Intellect/Imagination; John et al. call it Openness to Experience.",
        "definition": "Describes the breadth, depth, originality, and complexity of an individual's mental and "
        "experiential life.",
        "high": ["wide interests", "imaginative", "intelligent", "original", "insightful", "curious"],
        "low": ["commonplace", "narrow interests"],
    },
}


def build_big_five() -> None:
    print("Big Five (IPIP-50)")
    page = fetch(IPIP_URL)
    text = page.decode("utf-16") if page[:2] in (b"\xff\xfe", b"\xfe\xff") else page.decode("cp1252")
    lines = [strip_tags(x).lstrip("> ").strip() for x in re.split(r"<tr|</td>", text)]
    lines = [x for x in lines if x]
    items = []
    for i, line in enumerate(lines):
        m = re.fullmatch(r"(\d+)\.", line)
        if m and i + 1 < len(lines):
            # the key "(1+)" follows a few cells later
            for j in range(i + 2, min(i + 10, len(lines))):
                k = re.fullmatch(r"\(([1-5])([+-])\)", lines[j])
                if k:
                    items.append({
                        "id": f"ipip{m.group(1)}",
                        "n": int(m.group(1)),
                        "text": lines[i + 1],
                        "factor": IPIP_FACTORS[k.group(1)],
                        "key": 1 if k.group(2) == "+" else -1,
                    })
                    break
    assert len(items) == 50, f"expected 50 IPIP items, parsed {len(items)}"

    # Norms
    z = zipfile.ZipFile(io.BytesIO(fetch(BIG5_URL)))
    codebook = z.read("BIG5/codebook.txt").decode("utf-8", "replace")
    code_text = dict(re.findall(r"^([ENACO]\d+)\t(.+)$", codebook, re.M))

    def norm(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower().removeprefix("i "))

    by_text = {norm(t): c for c, t in code_text.items()}
    for it in items:
        it["dataset_code"] = by_text[norm(it["text"])]

    rows = list(csv.DictReader(io.StringIO(z.read("BIG5/data.csv").decode("utf-8")), delimiter="\t"))
    codes = [it["dataset_code"] for it in items]
    complete = [r for r in rows if all(r[c] in "12345" for c in codes)]
    norms = {}
    for f in IPIP_FACTORS.values():
        f_items = [it for it in items if it["factor"] == f]
        scores = [
            sum(int(r[it["dataset_code"]]) if it["key"] == 1 else 6 - int(r[it["dataset_code"]]) for it in f_items)
            for r in complete
        ]
        n = len(scores)
        pct = {}
        for s in range(10, 51):
            below = sum(1 for x in scores if x < s)
            equal = sum(1 for x in scores if x == s)
            pct[str(s)] = round(100 * (below + 0.5 * equal) / n, 1)
        norms[f] = {"n": n, "mean": round(statistics.mean(scores), 2), "sd": round(statistics.stdev(scores), 2),
                    "percentile_by_score": pct}

    # Verify transcribed adjectives / definitions against the John et al. (2008) PDF
    verify_john_2008()

    write_json("big_five.json", {
        "id": "big-five",
        "instructions": "Describe yourself as you generally are now, not as you wish to be in the future. Describe "
        "yourself as you honestly see yourself, in relation to other people you know of the same sex as you are, "
        "and roughly your same age. Indicate for each statement how accurately it describes you.",
        "scale": [
            {"value": 1, "label": "Very Inaccurate"},
            {"value": 2, "label": "Moderately Inaccurate"},
            {"value": 3, "label": "Neither Accurate Nor Inaccurate"},
            {"value": 4, "label": "Moderately Accurate"},
            {"value": 5, "label": "Very Accurate"},
        ],
        "items": items,
        "factors": BIG5_FACTORS,
        "norms": norms,
        "level_bands": {"low_below_percentile": 30, "high_above_percentile": 70,
                        "note": "App reporting convention (not part of IPIP): <30th percentile = lower, "
                                "30-70 = average range, >70 = higher, relative to the norm sample."},
        "sources": [
            {"what": "Items and scoring key (public domain)", "cite": "Goldberg, L. R. (1992). The development of "
             "markers for the Big-Five factor structure. Psychological Assessment, 4, 26-42. IPIP 50-item sample "
             "questionnaire.", "url": IPIP_URL},
            {"what": "Norms (percentiles)", "cite": f"Open Psychometrics BIG5 dataset, {len(complete)} complete "
             "responses collected online c. 2012 (self-selected, not a representative sample).", "url": BIG5_URL},
            {"what": "Factor definitions and trait adjectives", "cite": "John, O. P., Naumann, L. P., & Soto, C. J. "
             "(2008). Paradigm shift to the integrative Big Five trait taxonomy. In Handbook of Personality: Theory "
             "and Research (3rd ed.), Tables 4.2 and 4.4.", "url": JOHN_2008_URL},
        ],
    })


def verify_john_2008() -> None:
    import pymupdf

    pdf = pymupdf.open(stream=fetch(JOHN_2008_URL), filetype="pdf")
    text = " ".join(" ".join(p.get_text() for p in pdf).split()).lower().replace("’", "'")
    missing = []
    for f in BIG5_FACTORS.values():
        if f["definition"].lower().replace("’", "'") not in text:
            missing.append(f["definition"][:60])
        for adj in f["high"] + f["low"]:
            if adj.lower() not in text:
                missing.append(adj)
    assert not missing, f"Not found in John et al. (2008): {missing}"
    print("  verified Big Five definitions/adjectives against John et al. (2008)")


# --------------------------------------------------------------------------------------
# 2. OEJTS 1.2 - Open Extended Jungian Type Scales (CC BY-NC-SA 4.0), open alternative to MBTI.
#    Item text: 32-item form. Item keying: derived from the author's Appendix A statistics.
# --------------------------------------------------------------------------------------

OEJTS_DEV_URL = "https://openpsychometrics.org/tests/OEJTS/development/"
OEJTS_FORM_URL = "https://psytests.org/opm/oejtsen-bl.html"
OPPOSITE = {"E": "I", "I": "E", "S": "N", "N": "S", "F": "T", "T": "F", "J": "P", "P": "J"}
DIM_OF = {"E": "IE", "I": "IE", "S": "SN", "N": "SN", "F": "FT", "T": "FT", "J": "JP", "P": "JP"}


def build_oejts() -> None:
    print("OEJTS 1.2")
    form = fetch(OEJTS_FORM_URL).decode("utf-8", "replace")
    left = re.findall(r'<div class="blQN">(\d+)</div><div class="blQ">(.*?)</div>', form)
    right = re.findall(r'<div class="blQ blQL">(.*?)</div>', form)
    assert len(left) == len(right) == 32

    dev = fetch(OEJTS_DEV_URL).decode("utf-8", "replace")
    dev_lines = [strip_tags(x).strip(" |") for x in re.split(r"</tr>|</td>", dev)]
    dev_lines = [x for x in dev_lines if x]

    def norm(s: str) -> str:  # letters only, so "where ever" == "wherever" and quote glyphs don't matter
        return re.sub(r"[^a-z]", "", html.unescape(s).lower())

    table = {}
    for i, line in enumerate(dev_lines):
        if ";" in line and i + 4 < len(dev_lines):
            stats = dev_lines[i + 1:i + 5]
            if all(re.fullmatch(r"-?[\d.]+[EISNFTJP]", s) for s in stats):
                a, _, b = line.partition(";")
                table[(norm(a), norm(b))] = stats

    # Two form items are worded slightly differently from the development table
    aliases = {
        ("prefersmultiplechoicetests", "prefersessayquestions"): ("prefertotakemultiplechoicetest", "preferessayanswers"),
        ("keepsacleanroom", "justputsstuffwherever"): ("keepsacleanroom", "justputsstuffwhereever"),
    }

    def clean(s: str) -> str:
        s = html.unescape(s).replace("�", '"')
        return re.sub(r"\s+", " ", s).strip()

    items = []
    for (num, l_raw), r_raw in zip(left, right):
        L, R = norm(l_raw), norm(r_raw)
        L2, R2 = aliases.get((L, R), (L, R))
        if (L2, R2) in table:
            stats, flipped = table[(L2, R2)], False
        elif (R2, L2) in table:
            stats, flipped = table[(R2, L2)], True
        else:
            raise AssertionError(f"OEJTS item {num} not found in development table: {l_raw} / {r_raw}")
        diffs = [(float(s[:-1]), s[-1]) for s in stats]
        _, letter = max(diffs)
        right_pole = OPPOSITE[letter] if flipped else letter
        items.append({
            "id": f"q{num}", "n": int(num), "left": clean(l_raw), "right": clean(r_raw),
            "dimension": DIM_OF[right_pole], "right_pole": right_pole, "left_pole": OPPOSITE[right_pole],
            "evidence": {"dev_table_mean_differences": stats, "statements_reversed_in_table": flipped},
        })

    per_dim = {d: [it["n"] for it in items if it["dimension"] == d] for d in ("IE", "SN", "FT", "JP")}
    assert all(len(v) == 8 for v in per_dim.values()), per_dim

    write_json("oejts.json", {
        "id": "jungian-type",
        "instructions": "Each item is a pair of opposing descriptions on a five-point scale. Choose the point that "
        "best reflects your personality: from all of one, to a mix of the two, to all of the other.",
        "items": items,
        "dimensions": {
            "IE": {"poles": ["I", "E"], "names": {"I": "Introversion", "E": "Extraversion"},
                   "definition": "Sometimes described as a person's orientation, either oriented inside themselves or "
                   "to the outside world. Other times the focus is put more explicitly on social interaction, with "
                   "some claiming that social interactions wear out introverts whereas social interaction raises the "
                   "energy level in extroverts."},
            "SN": {"poles": ["S", "N"], "names": {"S": "Sensing", "N": "Intuition"},
                   "definition": "Defined as how a person takes in information by Myers-Briggs, who said that sensors "
                   "pay attention to the five senses while intuitives pay attention to possibilities."},
            "FT": {"poles": ["F", "T"], "names": {"F": "Feeling", "T": "Thinking"},
                   "definition": "Has been defined as what a person values and what they base their decisions on: "
                   "either interpersonal considerations or dispassionate logic."},
            "JP": {"poles": ["J", "P"], "names": {"J": "Judging", "P": "Perceiving"},
                   "definition": "Individuals who prefer a structured lifestyle are said to lean Judging; individuals "
                   "who prefer a flexible lifestyle are said to lean Perceiving."},
        },
        "scoring": {
            "method": "Each item is scored 1-5 from left to right. For each dimension, items are oriented so that a "
            "higher value always points to the same pole, then summed (range 8-40). 24 is the midpoint.",
            "midpoint": 24,
        },
        "license": "Open Extended Jungian Type Scales by Open Psychometrics, CC BY-NC-SA 4.0 "
                   "(https://creativecommons.org/licenses/by-nc-sa/4.0/) - non-commercial use only.",
        "sources": [
            {"what": "Test, item statistics and dichotomy definitions", "cite": "Jorgenson, E. (2014). Development of "
             "the Open Extended Jungian Type Scales 1.2. Open Psychometrics.", "url": OEJTS_DEV_URL},
            {"what": "32-item form wording", "cite": "OEJTS 1.2 answer sheet as reproduced by psytests.org; each item "
             "was matched to the author's development table above.", "url": OEJTS_FORM_URL},
        ],
        "trademark_note": "MBTI and Myers-Briggs Type Indicator are trademarks of The Myers-Briggs Company. "
                          "The OEJTS is not the MBTI.",
    })


# --------------------------------------------------------------------------------------
# 3. Reading the Mind in the Eyes Test (Revised) - Autism Research Centre, Cambridge.
#    Images + words from the official PDFs; answer key from the official key (bold = correct).
# --------------------------------------------------------------------------------------

ARC = "https://docs.autismresearchcentre.com"
RMET_PARTS = [f"{ARC}/tests/adult_part1.pdf", f"{ARC}/tests/adult_part2.pdf"]
RMET_KEY = f"{ARC}/tests/adult_instructions.pdf"
RMET_PAPER = f"{ARC}/papers/2001_BCetal_adulteyes.pdf"


def build_rmet() -> None:
    import pymupdf

    print("RMET (Eyes Test)")
    out = IMG_OUT / "rmet"
    out.mkdir(parents=True, exist_ok=True)
    stimuli = []
    for url in RMET_PARTS:
        doc = pymupdf.open(stream=fetch(url), filetype="pdf")
        for page in doc:
            words = page.get_text().split()
            label, options = words[0], words[1:5]
            assert len(options) == 4, (label, words)
            # Render the photo exactly as the PDF displays it (the embedded image uses an indexed palette
            # that does not survive raw extraction).
            xref = page.get_images()[0][0]
            rect = page.get_image_rects(xref)[0]
            pix = page.get_pixmap(clip=rect, dpi=160)
            name = f"{'practice' if label == 'practice' else int(label):0>2}.jpg"
            (out / name).write_bytes(pix.tobytes("jpeg", jpg_quality=88))
            stimuli.append({"label": label, "options": options, "image": f"/tests/rmet/{name}"})
    assert len(stimuli) == 37

    # Answer key: correct word is set in the bold font (same font as the "Answers - Adults" heading)
    key_doc = pymupdf.open(stream=fetch(RMET_KEY), filetype="pdf")
    key_page = next(p for p in key_doc if "Answers - Adults" in p.get_text())
    spans = [s for b in key_page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
             if s["text"].strip()]
    bold_font = next(s["font"] for s in spans if "Answers" in s["text"])
    tokens = [(t, s["font"] == bold_font) for s in spans if "Answers" not in s["text"] for t in s["text"].split()]
    key = {}
    i = 0
    while i < len(tokens):
        label = tokens[i][0]
        if label == "P" or label.isdigit():
            words = tokens[i + 1:i + 5]
            bold = [w for w, b in words if b]
            assert len(bold) == 1, (label, words)
            key[label] = {"options": [w for w, _ in words], "answer": bold[0], "sex": tokens[i + 5][0]}
            i += 6
        else:
            i += 1
    assert len(key) == 37, len(key)

    items = []
    for s in stimuli:
        k = key["P" if s["label"] == "practice" else s["label"]]
        assert k["options"] == s["options"], (s["label"], k["options"], s["options"])
        items.append({"id": "practice" if s["label"] == "practice" else f"e{s['label']}",
                      "n": 0 if s["label"] == "practice" else int(s["label"]),
                      "practice": s["label"] == "practice", "image": s["image"], "options": s["options"],
                      "answer": k["answer"]})

    write_json("rmet.json", {
        "id": "rmet",
        "instructions": "For each set of eyes, choose which word best describes what the person in the picture is "
        "thinking or feeling. You may feel that more than one word is applicable but please choose just one word, "
        "the word which you consider to be most suitable. Before making your choice, make sure that you have read "
        "all 4 words. You should try to do the task as quickly as possible but you will not be timed.",
        "glossary_url": RMET_KEY,
        "items": items,
        "norms": {
            "source": "Baron-Cohen, Wheelwright, Hill, Raste & Plumb (2001), Table 3",
            "groups": [
                {"group": "General population adults", "n": 122, "mean": 26.2, "sd": 3.6},
                {"group": "University students", "n": 103, "mean": 28.0, "sd": 3.5},
            ],
        },
        "disclaimer": "Our tests are not diagnostic: no single score on any of our tests indicates that an "
                      "individual is autistic. (Autism Research Centre)",
        "license": "Autism Research Centre tests are free for non-commercial research use with acknowledgement; "
                   "they must not be adapted or modified without permission. Commercial use: Cambridge Enterprise.",
        "sources": [
            {"what": "Stimuli, words and answer key", "cite": "Autism Research Centre, University of Cambridge - "
             "Adult Eyes Test (Revised).", "url": "https://www.autismresearchcentre.com/tests/eyes-test-adult/"},
            {"what": "Norms", "cite": "Baron-Cohen, S., Wheelwright, S., Hill, J., Raste, Y., & Plumb, I. (2001). The "
             "'Reading the Mind in the Eyes' Test revised version. Journal of Child Psychology and Psychiatry, 42, "
             "241-251.", "url": RMET_PAPER},
        ],
    })
    verify_rmet_norms()


def verify_rmet_norms() -> None:
    import pymupdf

    doc = pymupdf.open(stream=fetch(RMET_PAPER), filetype="pdf")
    text = " ".join(" ".join(p.get_text() for p in doc).split())
    # The PDF encodes the decimal point as an odd glyph; check the digits around it.
    for pattern in (r"General population controls All 122 26.2 3.6", r"Students All 103 28.0 3.5"):
        rx = pattern.replace(".", r"\W?").replace(" ", r"\s*")
        assert re.search(rx, text), f"norm not found in paper: {pattern}"
    print("  verified RMET norms against Baron-Cohen et al. (2001)")


# --------------------------------------------------------------------------------------
# 4. Rorschach plates (public domain) + popular responses as tabulated on Wikipedia,
#    citing Beck / Piotrowski (1987) / Dana (2000, France). Transcribed below.
# --------------------------------------------------------------------------------------

RORSCHACH_WIKI = ("https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Rorschach_test"
                  "&rvprop=content&rvslots=main&format=json&formatversion=2")
COMMONS_API = ("https://commons.wikimedia.org/w/api.php?action=query&titles=File:Rorschach_blot_{n}.jpg"
               "&prop=imageinfo&iiprop=url&iiurlwidth=800&format=json")

# Popular responses per card, exactly as listed in the article's table (checked by the build).
RORSCHACH_POPULAR = {
    1: [("Beck", "bat, butterfly, moth"), ("Piotrowski", "bat (53%), butterfly (29%)"), ("Dana (France)", "butterfly (39%)")],
    2: [("Beck", "two humans"), ("Piotrowski", "four-legged animal (34%, gray parts)"),
        ("Dana (France)", "animal: dog, elephant, bear (50%, gray)")],
    3: [("Beck", "two humans (gray)"), ("Piotrowski", "human figures (72%, gray)"), ("Dana (France)", "human (76%, gray)")],
    4: [("Beck", "animal hide, skin, rug"), ("Piotrowski", "animal skin, skin rug (41%)"), ("Dana (France)", "animal skin (46%)")],
    5: [("Beck", "bat, butterfly, moth"), ("Piotrowski", "butterfly (48%), bat (40%)"),
        ("Dana (France)", "butterfly (48%), bat (46%)")],
    6: [("Beck", "animal hide, skin, rug"), ("Piotrowski", "animal skin, skin rug (41%)"), ("Dana (France)", "animal skin (46%)")],
    7: [("Beck", "human heads or faces (top)"), ("Piotrowski", "heads of women or children (27%, top)"),
        ("Dana (France)", "human head (46%, top)")],
    8: [("Beck", "animal: not cat or dog (pink)"), ("Piotrowski", "four-legged animal (94%, pink)"),
        ("Dana (France)", "four-legged animal (93%, pink)")],
    9: [("Beck", "human (orange)"), ("Piotrowski", "none"), ("Dana (France)", "none")],
    10: [("Beck", "crab, lobster, spider (blue)"),
         ("Piotrowski", "crab, spider (37%, blue), rabbit head (31%, light green), caterpillars, worms, snakes (28%, deep green)"),
         ("Dana (France)", "none")],
}

# Words that count as naming each popular percept. The first group per card comes straight
# from the table; the "convention" words are plain-English equivalents (e.g. people = humans).
HUMAN_WORDS = ["human", "humans", "person", "persons", "people", "man", "men", "woman", "women", "lady", "ladies",
               "figure", "figures", "girl", "girls", "boy", "boys", "child", "children"]
FOUR_LEGGED = ["animal", "animals", "bear", "bears", "wolf", "wolves", "lion", "lions", "tiger", "tigers", "leopard",
               "panther", "rat", "rats", "mouse", "mice", "beaver", "badger", "pig", "pigs", "boar", "squirrel",
               "lizard", "lizards", "chameleon", "chameleons", "fox", "raccoon", "rodent", "rodents", "opossum", "possum"]
RORSCHACH_MATCH = {
    1: {"bat/butterfly/moth": ["bat", "bats", "butterfly", "butterflies", "moth", "moths"]},
    2: {"two humans": HUMAN_WORDS, "four-legged animal (dog, elephant, bear)":
        ["animal", "animals", "dog", "dogs", "elephant", "elephants", "bear", "bears", "four-legged", "puppy", "puppies"]},
    3: {"human figures": HUMAN_WORDS},
    4: {"animal hide / skin / rug": ["hide", "skin", "skins", "rug", "pelt", "fur"]},
    5: {"bat/butterfly/moth": ["bat", "bats", "butterfly", "butterflies", "moth", "moths"]},
    6: {"animal hide / skin / rug": ["hide", "skin", "skins", "rug", "pelt", "fur"]},
    7: {"human heads or faces": ["head", "heads", "face", "faces"] + HUMAN_WORDS},
    8: {"four-legged animal (not cat or dog)": FOUR_LEGGED},
    9: {"human": HUMAN_WORDS},
    10: {"crab/lobster/spider": ["crab", "crabs", "lobster", "lobsters", "spider", "spiders"],
         "rabbit head": ["rabbit", "rabbits", "bunny"],
         "caterpillars/worms/snakes": ["caterpillar", "caterpillars", "worm", "worms", "snake", "snakes"]},
}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def build_rorschach() -> None:
    print("Rorschach plates")
    if RORSCHACH_CACHE:
        wiki = (RORSCHACH_CACHE / "rorschach.wiki").read_text(encoding="utf-8")
        print(f"  using cached Wikipedia text from {RORSCHACH_CACHE}")
    else:
        wiki = json.loads(fetch(RORSCHACH_WIKI))["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    wiki_flat = re.sub(r"\{\{small\|\(([^)]*)\)\}\}", r"(\1)", wiki)
    wiki_flat = re.sub(r"<br\s*/>", "", wiki_flat)
    wiki_flat = re.sub(r"\s+", " ", wiki_flat)
    for card, rows in RORSCHACH_POPULAR.items():
        for _, text in rows:
            assert text in wiki_flat, f"card {card}: '{text}' not found in Wikipedia table"
    print("  verified popular-response table against Wikipedia")

    out = IMG_OUT / "rorschach"
    out.mkdir(parents=True, exist_ok=True)
    cards = []
    for n in range(1, 11):
        fname = f"{n:02d}.jpg"
        path = out / fname
        cached = RORSCHACH_CACHE / f"card_{n:02d}.jpg" if RORSCHACH_CACHE else None
        if cached and cached.exists() and cached.stat().st_size > 20000:
            path.write_bytes(cached.read_bytes())
        elif not path.exists() or path.stat().st_size < 20000:
            info = json.loads(fetch(COMMONS_API.format(n=f"{n:02d}")))
            ii = next(iter(info["query"]["pages"].values()))["imageinfo"][0]
            path.write_bytes(fetch(ii.get("thumburl") or ii["url"], wait=30, min_size=20000))
            time.sleep(5)
        cards.append({
            "id": f"card{n}", "n": n, "roman": ROMAN[n - 1], "image": f"/tests/rorschach/{fname}",
            "popular_responses": [{"source": s, "text": t} for s, t in RORSCHACH_POPULAR[n]],
            "match_terms": RORSCHACH_MATCH[n],
        })

    write_json("rorschach.json", {
        "id": "rorschach",
        "instructions": "Look at each inkblot and write what it might be. There are no right or wrong answers - "
        "describe whatever you see. You can mention more than one thing.",
        "cards": cards,
        "popular_definition": "Popular responses are percepts given by a large share of test-takers. In Exner's "
                              "system, a 'popular' response is one given by at least one third of the North American "
                              "normative sample; popularity and originality are basic dimensions of the analysis.",
        "matching_note": "Your answer counts as a popular response when it names a percept listed for that card. "
                         "Plain-English equivalents (for example 'people' for 'humans') are counted. The app does "
                         "not code location, determinants or form quality, which require a trained examiner.",
        "sources": [
            {"what": "Plates (public domain) and popular-response table", "cite": "Wikipedia, 'Rorschach test' - "
             "table citing Burstein & Loucks (1989), Piotrowski (1987) and Dana (2000). Note: the table lists "
             "identical populars for cards IV and VI.", "url": "https://en.wikipedia.org/wiki/Rorschach_test"},
            {"what": "Original plates", "cite": "Rorschach, H. (1921/1927). Psychodiagnostik - Psychodiagnostic Plates.",
             "url": "https://commons.wikimedia.org/wiki/Category:Rorschach_inkblots"},
        ],
    })


# --------------------------------------------------------------------------------------
# Shared helpers for Open Psychometrics datasets
# --------------------------------------------------------------------------------------

OP_RAW = "https://openpsychometrics.org/_rawdata/"


def op_dataset(zip_name: str) -> dict[str, str]:
    """Return {filename: text} for every file in an Open Psychometrics zip."""
    z = zipfile.ZipFile(io.BytesIO(fetch(OP_RAW + zip_name, min_size=10000)))
    return {Path(n).name: z.read(n).decode("utf-8", "replace") for n in z.namelist() if not n.endswith("/")}


def read_rows(text: str) -> list[dict]:
    delim = "\t" if "\t" in text.splitlines()[0] else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def percentile_table(scores: list[int], lo: int, hi: int) -> dict[str, float]:
    n = len(scores)
    out = {}
    for s in range(lo, hi + 1):
        below = sum(1 for x in scores if x < s)
        equal = sum(1 for x in scores if x == s)
        out[str(s)] = round(100 * (below + 0.5 * equal) / n, 1)
    return out


def norm_block(scores: list[int], lo: int, hi: int) -> dict:
    return {"n": len(scores), "mean": round(statistics.mean(scores), 2), "sd": round(statistics.stdev(scores), 2),
            "median": statistics.median(scores), "percentile_by_score": percentile_table(scores, lo, hi)}


def letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", html.unescape(s).lower())


# --------------------------------------------------------------------------------------
# 5. Holland Code (RIASEC) - public-domain Interest Item Pool items, O*NET definitions,
#    norms from the Open Psychometrics RIASEC dataset (145,828 responses).
# --------------------------------------------------------------------------------------

ONET_INTERESTS_URL = "https://www.onetonline.org/find/descriptor/browse/1.B.1"
RIASEC_NAMES = {"R": "Realistic", "I": "Investigative", "A": "Artistic", "S": "Social", "E": "Enterprising",
                "C": "Conventional"}


def build_riasec() -> None:
    print("RIASEC (Holland Code)")
    files = op_dataset("RIASEC_data12Dec2018.zip")
    codebook = files["codebook.txt"]
    items = [{"id": code.lower(), "code": code, "type": code[0], "text": text.strip()}
             for code, text in re.findall(r"^([RIASEC][1-8])\t(.+)$", codebook, re.M)]
    assert len(items) == 48, len(items)
    assert "1=Dislike, 3=Neutral, 5=Enjoy" in codebook

    rows = read_rows(files["data.csv"])
    codes = [i["code"] for i in items]
    complete = [r for r in rows if all(r.get(c) in ("1", "2", "3", "4", "5") for c in codes)]
    norms = {t: norm_block([sum(int(r[f"{t}{k}"]) for k in range(1, 9)) for r in complete], 8, 40)
             for t in RIASEC_NAMES}

    # Official O*NET definitions (US Department of Labor, public domain)
    page = fetch(ONET_INTERESTS_URL).decode("utf-8", "replace")
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).replace("/ ", "/")
    definitions = {}
    for t, name in RIASEC_NAMES.items():
        m = re.search(rf"\b{name} (Work involves .+?\.) ({name} occupations are often associated with .+?\.)", text)
        assert m, f"O*NET definition for {name} not found"
        definitions[t] = {"name": name, "work": m.group(1), "occupations": m.group(2)}

    write_json("riasec.json", {
        "id": "riasec",
        "instructions": "Rate how much you would like to perform each task. Don't worry about whether you have "
        "the training or how much money it would pay - just think about whether you would enjoy it.",
        "scale": [{"value": 1, "label": "Dislike"}, {"value": 2, "label": "Slightly dislike"},
                  {"value": 3, "label": "Neutral"}, {"value": 4, "label": "Slightly enjoy"},
                  {"value": 5, "label": "Enjoy"}],
        "scale_note": "The dataset labelled only 1 = Dislike, 3 = Neutral, 5 = Enjoy; points 2 and 4 are app labels.",
        "items": items,
        "types": definitions,
        "norms": norms,
        "sources": [
            {"what": "Items (public domain)", "cite": "Interest Item Pool - Liao, H.-Y., Armstrong, P. I., & Rounds, J. "
             "(2008). Development and initial validation of public domain Basic Interest Markers. Journal of "
             "Vocational Behavior, 73, 159-183. As used in the Open Psychometrics RIASEC test.",
             "url": OP_RAW},
            {"what": "Norms (percentiles)", "cite": f"Open Psychometrics RIASEC dataset, {len(complete):,} complete "
             "responses collected online 2015-2018 (self-selected sample).", "url": OP_RAW},
            {"what": "Interest area definitions (public domain)", "cite": "O*NET OnLine, Interests (1.B.1), U.S. "
             "Department of Labor / Holland's RIASEC model.", "url": ONET_INTERESTS_URL},
        ],
    })


# --------------------------------------------------------------------------------------
# 6. Rosenberg Self-Esteem Scale - scoring per the University of Maryland (Rosenberg's home
#    department); norms from the Open Psychometrics RSE dataset (47,974 responses).
# --------------------------------------------------------------------------------------

UMD_RSE_URL = "https://socy.umd.edu/about-us/using-rosenberg-self-esteem-scale"


def build_rse() -> None:
    print("Rosenberg Self-Esteem Scale")
    files = op_dataset("RSE.zip")
    codebook = files["codebook.txt"]
    items = [{"id": f"rse{n}", "n": int(n), "text": t.strip()} for n, t in re.findall(r"^Q(\d+)\. (.+?)\s*$", codebook, re.M)]
    assert len(items) == 10, len(items)

    page = fetch(UMD_RSE_URL).decode("utf-8", "replace")
    umd = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    assert "For items 1,2,4,6,7: Strongly Agree=3, Agree=2, Disagree=1, and Strongly Disagree=0" in umd
    assert "For items 3,5,8,9,10" in umd and "The scale ranges from 0-30" in umd
    assert "Rosenberg Self-Esteem Scale is now in the public domain" in page
    # UMD shows the items as an image ("Rosenberg SE Scale.jpg"); transcribed here and checked
    # against the dataset wording. ** in the image marks the reversed items.
    umd_items = [
        "I feel that I'm a person of worth, at least on an equal plane with others.",
        "I feel that I have a number of good qualities.",
        "All in all, I am inclined to feel that I am a failure.",
        "I am able to do things as well as most other people.",
        "I feel I do not have much to be proud of.",
        "I take a positive attitude toward myself.",
        "On the whole, I am satisfied with myself.",
        "I wish I could have more respect for myself.",
        "I certainly feel useless at times.",
        "At times I think I am no good at all.",
    ]
    for it, official in zip(items, umd_items):
        assert letters(it["text"]).replace("iam", "im") == letters(official).replace("iam", "im"), (it, official)
        it["text"] = official
    reversed_items = {3, 5, 8, 9, 10}
    for it in items:
        it["key"] = -1 if it["n"] in reversed_items else 1
    print("  verified RSE items and scoring against UMD")

    # Dataset codes 1=SD .. 4=SA; UMD scoring is 0-3
    rows = read_rows(files["data.csv"])
    complete = [r for r in rows if all(r.get(f"Q{i}") in ("1", "2", "3", "4") for i in range(1, 11))]

    def score(r: dict) -> int:
        return sum((int(r[f"Q{i}"]) - 1) if i not in reversed_items else (4 - int(r[f"Q{i}"])) for i in range(1, 11))

    write_json("rse.json", {
        "id": "self-esteem",
        "instructions": "Below is a list of statements dealing with your general feelings about yourself. "
        "Indicate how strongly you agree or disagree with each statement.",
        "scale": [{"value": 0, "label": "Strongly disagree"}, {"value": 1, "label": "Disagree"},
                  {"value": 2, "label": "Agree"}, {"value": 3, "label": "Strongly agree"}],
        "items": items,
        "scoring": "Items 1, 2, 4, 6, 7: Strongly Agree=3 ... Strongly Disagree=0. Items 3, 5, 8, 9, 10 are reversed. "
                   "Total 0-30; higher = higher self-esteem.",
        "about": "The scale asks about your general feelings about yourself. Studies have found both a single-factor "
                 "and a two-factor (self-confidence and self-deprecation) structure.",
        "norms": norm_block([score(r) for r in complete], 0, 30),
        # The positively and negatively worded halves (UMD: studies found a self-confidence and a
        # self-deprecation factor). Both scored so that higher = more positive self-view, range 0-15.
        "subscale_norms": {
            "positive": norm_block([sum(int(r[f"Q{i}"]) - 1 for i in (1, 2, 4, 6, 7)) for r in complete], 0, 15),
            "negative": norm_block([sum(4 - int(r[f"Q{i}"]) for i in (3, 5, 8, 9, 10)) for r in complete], 0, 15),
        },
        "sources": [
            {"what": "Scale and scoring (public domain)", "cite": "Rosenberg, M. (1965). Society and the Adolescent "
             "Self-Image. Princeton University Press. Items, scoring and public-domain notice from the University "
             "of Maryland Department of Sociology.", "url": UMD_RSE_URL},
            {"what": "Norms (percentiles)", "cite": f"Open Psychometrics RSE dataset, {len(complete):,} complete "
             "responses collected online (self-selected sample).", "url": OP_RAW},
        ],
    })


# --------------------------------------------------------------------------------------
# 7. Experiences in Close Relationships (ECR) - Brennan, Clark & Shaver (1998). Items and keys
#    from R. Chris Fraley's page; definitions from Fraley's attachment overview; norms from the
#    Open Psychometrics ECR dataset (51,492 responses, 5-point version).
# --------------------------------------------------------------------------------------

FRALEY_ECR_URL = "https://labs.psychology.illinois.edu/~rcfraley/measures/brennan.html"
FRALEY_OVERVIEW_URL = "https://labs.psychology.illinois.edu/~rcfraley/attachment.htm"


def build_ecr() -> None:
    print("Experiences in Close Relationships")
    files = op_dataset("ECR-data-1March2018.zip")
    cb = files["codebook.html"]
    items = [{"id": f"ecr{n}", "n": int(n), "text": html.unescape(t).strip()}
             for n, t in re.findall(r"<td>Q(\d+)</td>\s*<td>INTEGER</td>\s*<td>\"(.+?)\" rated", cb, re.S)]
    assert len(items) == 36, len(items)

    page = fetch(FRALEY_ECR_URL).decode("latin-1")
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    for it in items:
        m = re.search(rf"\b{it['n']}\. \.\d\d (.+?)(?= \d+\. \.\d\d | Return|$)", text)
        assert m, f"ECR item {it['n']} not on Fraley page"
        listed = m.group(1)
        assert letters(it["text"])[:25] in letters(listed) or letters(listed)[:25] in letters(it["text"]), \
            (it["n"], it["text"], listed)
        it["scale"] = "avoidance" if it["n"] % 2 == 1 else "anxiety"
        it["key"] = -1 if "(R)" in listed else 1
    rev = sorted(i["n"] for i in items if i["key"] == -1)
    assert rev == [3, 15, 19, 22, 25, 27, 29, 31, 33, 35], rev
    print("  verified ECR items, scales and reverse keys against Fraley's page")

    overview = fetch(FRALEY_OVERVIEW_URL).decode("latin-1")
    ov = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", overview)))
    quotes = {
        "anxiety_high": "People who score high on this variable tend to worry whether their partner is available, "
                        "responsive, attentive, etc.",
        "anxiety_low": "People who score on the low end of this variable are more secure in the perceived "
                       "responsiveness of their partners.",
        "avoidance_high": "People on the high end of this dimension prefer not to rely on others or open up to others.",
        "avoidance_low": "People on the low end of this dimension are more comfortable being intimate with others and "
                         "are more secure depending upon and having others depend upon them.",
        "secure": "A prototypical secure adult is low on both of these dimensions.",
        "dismissing": "dismissing individuals (i.e., individuals who are high on the dimension of attachment-related "
                      "avoidance but low on the dimension of attachment-related anxiety)",
    }
    for k, q in quotes.items():
        assert q in ov, f"quote '{k}' not found in Fraley overview"
    print("  verified attachment definitions against Fraley's overview")

    rows = read_rows(files["data.csv"])
    complete = [r for r in rows if all(r.get(f"Q{i}") in ("1", "2", "3", "4", "5") for i in range(1, 37))]

    def mean_score(r: dict, scale: str) -> float:
        vals = [int(r[f"Q{i['n']}"]) if i["key"] == 1 else 6 - int(r[f"Q{i['n']}"]) for i in items if i["scale"] == scale]
        return sum(vals)  # sum of 18 items, range 18-90

    write_json("ecr.json", {
        "id": "attachment",
        "instructions": "The statements below concern how you feel in emotionally intimate relationships. Think "
        "about how you generally experience close romantic relationships, not just what is happening in a current "
        "one, and rate how much you agree with each statement.",
        "scale": [{"value": 1, "label": "Strongly disagree"}, {"value": 2, "label": "Disagree"},
                  {"value": 3, "label": "Neither agree nor disagree"}, {"value": 4, "label": "Agree"},
                  {"value": 5, "label": "Strongly agree"}],
        "items": items,
        "definitions": quotes,
        "norms": {s: norm_block([mean_score(r, s) for r in complete], 18, 90) for s in ("avoidance", "anxiety")},
        "scale_note": "Brennan et al. used a 7-point scale; this version uses the 5-point scale of the norm dataset.",
        "sources": [
            {"what": "Items and scoring", "cite": "Brennan, K. A., Clark, C. L., & Shaver, P. R. (1998). Self-report "
             "measurement of adult romantic attachment: An integrative overview. In Simpson & Rholes (Eds.), "
             "Attachment Theory and Close Relationships (pp. 46-76). Guilford.", "url": FRALEY_ECR_URL},
            {"what": "Dimension definitions", "cite": "Fraley, R. C. A Brief Overview of Adult Attachment Theory and "
             "Research.", "url": FRALEY_OVERVIEW_URL},
            {"what": "Norms (percentiles)", "cite": f"Open Psychometrics ECR dataset, {len(complete):,} complete "
             "responses collected online (self-selected sample).", "url": OP_RAW},
        ],
    })


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--rorschach-cache="):
            RORSCHACH_CACHE = Path(a.split("=", 1)[1])
    targets = args or ["big5", "oejts", "rmet", "rorschach", "riasec", "rse", "ecr"]
    builders = {"big5": build_big_five, "oejts": build_oejts, "rmet": build_rmet, "rorschach": build_rorschach,
                "riasec": build_riasec, "rse": build_rse, "ecr": build_ecr}
    for t in targets:
        builders[t]()
    print("done")
