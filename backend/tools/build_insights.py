"""
Build app/test_data/insights.json: research-backed interpretive statements used to write richer,
more "human" conclusions. Every statement is a verbatim quote, checked as an exact substring of its
source text. Nothing is paraphrased or invented here.

Sources: English Wikipedia articles (CC BY-SA 4.0) that summarise the cited research literature.

Run from backend/:
    HIVE_BUILD_CONTACT=you@example.com ../venv/Scripts/python tools/build_insights.py
    # or, with previously downloaded plain-text extracts (<Title>.txt) and rorschach.wiki:
    ../venv/Scripts/python tools/build_insights.py --cache=DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_test_data as b  # noqa: E402  (shared fetch/write helpers)

WIKI = "https://en.wikipedia.org/wiki/"
ARTICLES = {
    "big5": "Big Five personality traits",
    "mbti": "Myers–Briggs Type Indicator",
    "holland": "Holland Codes",
    "selfesteem": "Self-esteem",
    "attachment": "Attachment in adults",
    "tom": "Theory of mind",
    "rorschach": "Rorschach test",
}
# Non-Wikipedia sources (fetched as plain text; cached as <key>.txt when --cache is used)
EXTRA_SOURCES = {
    "rorschach_org": {"title": "Rorschach.org FAQ (Mark W. Matthews, PhD)", "url": "https://www.rorschach.org/faq.html",
                      "license": "Rorschach.org, CC BY-NC-SA 3.0 (quoted with attribution)"},
    "rorschach_org_home": {"title": "Rorschach.org", "url": "https://www.rorschach.org/",
                           "license": "Rorschach.org, CC BY-NC-SA 3.0 (quoted with attribution)"},
    "dauphin2024": {"title": "Dauphin et al. (2024), Journal of Personality Assessment - abstract",
                    "url": "https://doi.org/10.1080/00223891.2024.2303433",
                    "license": "Open access, CC BY-NC-ND 4.0 (abstract quoted)",
                    "fetch": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:10.1080/00223891.2024.2303433&format=json&resultType=core"},
}


def q(source: str, text: str) -> dict:
    return {"source": source, "text": text}


SPEC = {
    "big-five": {
        "E": {
            "higher": [q("big5", "Extraverts enjoy interacting with people, and are often perceived as energetic."),
                       q("big5", "They tend to be enthusiastic and action-oriented.")],
            "lower": [q("big5", "Introverts need less stimulation and more time alone than extraverts."),
                      q("big5", "They tend to seem quiet, low-key, deliberate, and less involved in the social world.")],
            "average": [q("big5", "Generally, people are a combination of extraversion and introversion")],
        },
        "A": {
            "higher": [q("big5", "Agreeable individuals value getting along with others."),
                       q("big5", "They are generally considerate, kind, generous, trusting and trustworthy, helpful, and "
                                 "willing to compromise their interests with others.")],
            "lower": [q("big5", "Disagreeable people are often competitive or challenging")],
            "average": [],
        },
        "C": {
            "higher": [q("big5", "Conscientiousness is a tendency to be self-disciplined, act dutifully, and strive for "
                                 "achievement against measures or outside expectations."),
                       q("big5", "High conscientiousness indicates a preference for planned rather than spontaneous "
                                 "behaviour.")],
            "lower": [q("big5", "Low conscientiousness is associated with flexibility and spontaneity")],
            "average": [],
        },
        "ES": {  # Emotional Stability = the low end of Neuroticism
            "higher": [q("big5", "less neurotic individuals are less easily upset and are less emotionally reactive."),
                       q("big5", "They tend to be calm, emotionally stable, and free from persistent negative feelings.")],
            "lower": [q("big5", "emotionally volatile, emotionally reactive and vulnerable to stress")],
            "average": [],
        },
        "O": {
            "higher": [q("big5", "People who are open to experience are intellectually curious, open to emotion, "
                                 "sensitive to beauty, and willing to try new things."),
                       q("big5", "They tend to be, when compared to closed people, more creative and more aware of their "
                                 "feelings.")],
            "lower": [q("big5", "those with low openness want to be fulfilled by persevering and are characterised as "
                                "pragmatic and data-driven")],
            "average": [],
        },
        "general": [q("big5", "These traits are not black and white; each one is a spectrum, with personality varying "
                              "continuously across each of these dimensions")],
    },
    "jungian-type": {
        "E": [q("mbti", "Extraversion means literally outward-turning and introversion, inward-turning.")],
        "I": [q("mbti", "Extraversion means literally outward-turning and introversion, inward-turning.")],
        "S": [q("mbti", "people who prefer sensing are more likely to trust information that is in the present, "
                        "tangible, and concrete."), q("mbti", "They tend to distrust hunches.")],
        "N": [q("mbti", "Those who prefer intuition tend to trust information that is associated with other "
                        "information, either remembered or discovered from context.")],
        "T": [q("mbti", "Those who prefer thinking tend to decide things from a more detached standpoint.")],
        "F": [q("mbti", "Those who prefer feeling tend to come to decisions by associating or empathizing with the "
                        "situation.")],
        "J": [q("mbti", "judging types like to \"have matters settled\"")],
        "P": [q("mbti", "perceptive types prefer to \"keep decisions open\"")],
        "general": [q("mbti", "the MBTI attempts to measure of preference, not ability or skill")],
        # Big Five links for each letter (McCrae & Costa, 1989, as summarised in the MBTI article)
        "big5_link": [q("mbti", "I and P have negative correlations with extraversion and conscientiousness, "
                                "respectively, while F and N have positive correlations with agreeableness and "
                                "openness, respectively.")],
        "dimensions_note": [q("mbti", "the instrument measures four relatively independent dimensions.")],
        "extra": {
            "E": [q("big5", "Extraverts enjoy interacting with people, and are often perceived as energetic.")],
            "I": [q("big5", "Introverts need less stimulation and more time alone than extraverts.")],
            "T": [q("mbti", "People who prefer thinking do not necessarily, in the everyday sense, \"think better\" "
                            "than their feeling counterparts")],
            "F": [q("mbti", "those who prefer feeling do not necessarily have \"better\" emotional reactions than "
                            "their thinking counterparts.")],
            "J": [q("mbti", "Myers and Briggs added a dimension to Jung's typological model")],
            "P": [q("mbti", "Myers and Briggs added a dimension to Jung's typological model")],
            "S": [q("mbti", "Jung identified two pairs of psychological functions")],
            "N": [q("mbti", "Jung identified two pairs of psychological functions")],
        },
    },
    "self-esteem": {
        "higher": [q("selfesteem", "are able to act according to what they think to be the best choice, trusting their "
                                   "own judgment, and not feeling guilty when others do not like their choice"),
                   q("selfesteem", "fully trust their capacity to solve problems, not hesitating after failures and "
                                   "difficulties; they ask others for help when they need it"),
                   q("selfesteem", "are able to enjoy a great variety of activities"),
                   q("selfesteem", "consider themselves equal in dignity to others, rather than inferior or superior, "
                                   "while accepting differences in certain talents, personal prestige, or financial "
                                   "standing"),
                   q("selfesteem", "can work toward finding solutions and voice discontent without belittling "
                                   "themselves or others when challenges arise")],
        "average": [q("selfesteem", "Self-esteem tends to increase during adolescence and young adulthood, reaching a "
                                    "peak in middle age.")],
        "lower": [q("selfesteem", "Individuals with low self-esteem tend to be critical of themselves."),
                  q("selfesteem", "However, this does not mean it cannot be changed.")],
        "general": [q("selfesteem", "In terms of personality, emotionally stable, extroverted, and conscientious "
                                    "individuals experience higher self-esteem.")],
        "development": [q("selfesteem", "Experiences in a person's life are a major source of how self-esteem "
                                        "develops."),
                        q("selfesteem", "These predictors have shown that self-esteem has trait-like qualities by "
                                        "remaining stable over time like personality and intelligence.")],
    },
    "attachment": {
        "secure": [q("attachment", "People that have a secure attachment style are often associated with high "
                                   "self-esteem, and have an easier time forming healthy relationships with others."),
                   q("attachment", "Those with a secure attachment style often manage conflict without feeling "
                                   "overwhelmed and are not bothered by the concepts of closeness and independence.")],
        "anxious-preoccupied": [q("attachment", "These individuals seek intimacy but fear that others do not want to be "
                                                "with them."),
                                q("attachment", "Even in stable relationships, many anxious attachment individuals "
                                                "worry about the state of the relationship.")],
        "dismissive-avoidant": [q("attachment", "Individuals with a dismissive-avoidant attachment style typically "
                                                "suppress their emotions, and prioritize their personal independence.")],
        "fearful-avoidant": [q("attachment", "They seek close relationships, but are scared of them, and so experience "
                                             "a personal battle within themselves."),
                             q("attachment", "Many people with this attachment style may stay in the dating stage of "
                                             "romantic relationships as it takes longer to trust others.")],
        "general": [q("attachment", "Around 70–80% of people experience no significant changes in attachment styles "
                                    "over time."),
                    q("attachment", "suggest working models are not rigid personality traits")],
        "more": {
            "secure": [q("attachment", "Many adults who have a secure attachment style have an easier time trusting in "
                                       "themselves and their relationships."),
                       q("attachment", "Adults who have a secure attachment style usually express greater satisfaction "
                                       "with their relationships.")],
            "anxious-preoccupied": [q("attachment", "Individuals with anxious attachment seek approval by others "
                                                    "regarding the security of the relationship.")],
            "dismissive-avoidant": [q("attachment", "Many have a hard time opening up to romantic partners, and when "
                                                    "things feel real, they pull away."),
                                    q("attachment", "The characteristics of individuals who are dismissive-avoidant "
                                                    "include emotional distance, independence over closeness")],
            "fearful-avoidant": [q("attachment", "These individuals sometimes seek closeness, but other times crave "
                                                 "distance due to fear of abandonment.")],
        },
        "outcomes": [q("attachment", "Secure attachment styles may lead to more constructive communication and more "
                                     "intimate self-disclosures, which in turn increase relationship satisfaction.")],
    },
    "rmet": {
        "general": [q("tom", "theory of mind (often abbreviated to ToM) is the capacity to understand other individuals "
                             "by ascribing mental states to them."),
                    q("tom", "Possessing a functional theory of mind is crucial for success in everyday human social "
                             "interactions."),
                    q("tom", "People use a theory of mind when analyzing, judging, and inferring other people's "
                             "behaviors.")],
        "caveat": [q("tom", "Measures such as the Reading the Mind in the Eyes test (RME) have been widely used and "
                            "accepted by experts as measures of ToM but systematic reviews of research have shown a "
                            "lack of validity data.")],
    },
    "rorschach": {
        "about": [q("rorschach_org", "In the strictest sense, the Rorschach Inkblot Test is a test or assessment of "
                                     "perception."),
                  q("rorschach_org", "How does someone view and organize the world around them?"),
                  q("rorschach", "\"Popularity\" and \"originality\" of responses can also be considered as basic "
                                 "dimensions in the analysis."),
                  q("rorschach", "different cultures will exhibit different \"common\" objects")],
        "caveat": [q("rorschach_org_home", "A self-evaluation online is by no means appropriate.")],
        "research": [q("dauphin2024", "higher levels of Complexity are also associated with scanning more regions of "
                                      "the blot overall, albeit at a slower rate.")],
        "I": [q("rorschach", "Being the first card, it can provide clues about how subjects tackle a new and stressful "
                             "task.")],
        "II": [q("rorschach", "The red details of card II are often seen as blood, and are the most distinctive "
                              "features.")],
        "III": [q("rorschach", "Card III is typically perceived to contain two humans involved in some interaction, and "
                               "may provide information about how the subject relates with other people")],
        "IV": [q("rorschach", "is generally perceived as a big and sometimes threatening figure; compounded with the "
                              "common impression of the subject being in an inferior position (\"looking up\") to it, "
                              "this serves to elicit a sense of authority.")],
        "V": [q("rorschach", "Card V is an easily elaborated card that is not usually perceived as threatening, and "
                             "typically instigates a \"change of pace\" in the test, after the previous more challenging "
                             "cards.")],
        "VI": [q("rorschach", "Texture is the dominant characteristic of card VI, which often elicits association "
                              "related to interpersonal closeness")],
        "VII": [q("rorschach", "Card VII can be associated with femininity (the human figures commonly seen in it being "
                               "described as women or children)")],
        "VIII": [q("rorschach", "People often express relief about card VIII, which lets them relax and respond "
                                "effectively.")],
        "IX": [q("rorschach", "Characteristic of card IX is indistinct form and diffuse, muted chromatic features, "
                              "creating a general vagueness.")],
        "X": [q("rorschach", "Being the last card, it may provide an opportunity for the subject to \"sign out\" by "
                             "indicating what they feel their situation is like, or what they desire to know.")],
    },
}

HOLLAND_LETTER = {"Realistic": "R", "Investigative": "I", "Artistic": "A", "Social": "S", "Enterprising": "E",
                  "Conventional": "C"}


def normalise(t: str) -> str:
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", t)


def clean_wikitext(w: str) -> str:
    w = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", w, flags=re.S)
    w = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", w)
    return w.replace("'''", "").replace("''", "")


def load_sources(cache: Path | None) -> dict[str, str]:
    texts = {}
    for key, title in ARTICLES.items():
        if cache and (cache / f"{title.replace(' ', '_')}.txt").exists():
            texts[key] = (cache / f"{title.replace(' ', '_')}.txt").read_text(encoding="utf-8")
        else:
            url = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&redirects=1"
                   f"&format=json&formatversion=2&titles={quote(title)}")
            texts[key] = json.loads(b.fetch(url))["query"]["pages"][0]["extract"]
    # Card comments live in a table, which plain-text extracts drop: use the wikitext
    if cache and (cache / "rorschach.wiki").exists():
        raw = (cache / "rorschach.wiki").read_text(encoding="utf-8")
    else:
        raw = json.loads(b.fetch(b.RORSCHACH_WIKI))["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    texts["rorschach"] += "\n" + clean_wikitext(raw)

    for key, meta in EXTRA_SOURCES.items():
        cached = cache / f"{key}.txt" if cache else None
        if cached and cached.exists():
            texts[key] = cached.read_text(encoding="utf-8")
        elif key == "dauphin2024":
            texts[key] = json.loads(b.fetch(meta["fetch"]))["resultList"]["result"][0]["abstractText"]
        else:
            page = b.fetch(meta["url"]).decode("utf-8", "replace")
            texts[key] = b.strip_tags(re.sub(r"<script.*?</script>", " ", page, flags=re.S))
    return {k: normalise(v) for k, v in texts.items()}


def verify(node, texts: dict[str, str], path: str = "") -> int:
    count = 0
    if isinstance(node, dict) and "source" in node and "text" in node:
        assert normalise(node["text"]) in texts[node["source"]], f"NOT FOUND [{path}] {node['text'][:80]}"
        return 1
    if isinstance(node, dict):
        for k, v in node.items():
            count += verify(v, texts, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            count += verify(v, texts, f"{path}[{i}]")
    return count


def holland(texts_raw: str) -> dict:
    out = {}
    nick = dict(re.findall(r"(Realistic|Investigative|Artistic|Social|Enterprising|Conventional) \((\w+)\)", texts_raw))
    sections = re.split(r"^=== ([RIASEC]): (\w+) \((\w+)\) ===$", texts_raw, flags=re.M)
    # sections = [pre, letter, name, nickname, body, letter, name, nickname, body, ...]
    for i in range(1, len(sections), 4):
        letter, name, nickname, body = sections[i:i + 4]
        body = body.split("\n==")[0]
        definition = re.search(r"Holland defines the .+?\.\"|Holland defines the .+?\.”|Holland defines the .+?\"",
                               body)
        careers = []
        for line in body.splitlines():
            m = re.fullmatch(r"([A-Z][^()]{1,90}?)(?: \(with ([^)]+)\))?", line.strip())
            if m and not line.startswith("Holland"):
                others = [HOLLAND_LETTER[w] for w in re.findall(r"[A-Z][a-z]+", m.group(2) or "") if w in HOLLAND_LETTER]
                careers.append({"title": m.group(1).strip(), "letters": [letter] + others})
        out[letter] = {"name": name, "nickname": nickname or nick.get(name),
                       "definition": definition.group(0) if definition else None, "careers": careers}
    assert set(out) == set("RIASEC"), out.keys()
    return out


def main() -> None:
    cache = None
    for a in sys.argv[1:]:
        if a.startswith("--cache="):
            cache = Path(a.split("=", 1)[1])
    texts = load_sources(cache)
    n = verify(SPEC, texts)
    print(f"verified {n} quotes against their sources")

    holland_raw = (cache / "Holland_Codes.txt").read_text(encoding="utf-8") if cache else None
    if holland_raw is None:
        url = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&format=json"
               f"&formatversion=2&titles={quote(ARTICLES['holland'])}")
        holland_raw = json.loads(b.fetch(url))["query"]["pages"][0]["extract"]
    riasec = holland(holland_raw)
    print("holland careers:", {k: len(v["careers"]) for k, v in riasec.items()})

    b.write_json("insights.json", {
        **SPEC,
        "riasec": riasec,
        "sources": {**{k: {"title": t, "url": WIKI + t.replace(" ", "_"),
                           "license": "Wikipedia text, CC BY-SA 4.0 (quoted with attribution)"}
                       for k, t in ARTICLES.items()},
                    **{k: {kk: vv for kk, vv in m.items() if kk != "fetch"} for k, m in EXTRA_SOURCES.items()}},
    })


if __name__ == "__main__":
    main()
