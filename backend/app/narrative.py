"""Final write-up = deterministic portrait (app/portrait.py) + optional AI polish.

The conclusions are written in code from verified data. With the user's consent, the AI may only REWORD each
paragraph for style. A rewrite is accepted only if it is faithful:
  - every number and every quotation ("...") from the original is still there, unchanged, and no new numbers;
  - no new names (capitalised words) and no clinical/absolute terms;
  - almost no new content words, and no new words that put feelings or actions in the person's mouth;
  - similar length.
Otherwise the original paragraph is kept. The same applies to the AI-suggested title.
"""

import asyncio
import logging
import re

from . import config, llm

log = logging.getLogger(__name__)

POLISH_PROMPT = """You are the narrator of Hive, a psychology-test app. Lightly edit the paragraph you are given so it reads more vividly, warmly and smoothly, addressed to the reader as "you".

Rules:
- Tokens like [QA] or [NB] stand for exact quotations and numbers. Copy every token exactly once, unchanged.
- Keep every name and every fact. Do not add any new information: no new traits, feelings, behaviours, sensations, settings, advice, interpretations or claims about what the reader thinks, feels, wants or did.
- This is a light-touch edit: keep most of the original wording and change only rhythm, transitions and a few word choices. Keep roughly the same length.
- Output only the edited paragraph, plain text, no markdown."""

RISKY = ["diagnos", "disorder", "autis", "adhd", "depress", "bipolar", "schizo", "psychopath", "narciss", "patholog",
         "clinical", "therapy", "medication", "illness", "trauma", "genius", "always", "never", "guarantee",
         "definitely", "certainly"]
# New words that would put thoughts, feelings or actions in the reader's mouth
ATTRIBUTION = ["feel", "felt", "believ", "mention", "imagin", "want", "crave", "fear", "worri", "worry", "hesitat",
               "struggl", "love", "hate", "think", "thought", "wonder", "dream", "hope", "carefu", "deliber",
               "decid", "chose", "prefer", "enjoy", "like", "nervous", "anxious", "confiden", "proud", "ashamed"]
STOP = {"about", "which", "their", "there", "these", "those", "other", "people", "often", "while", "where", "every",
        "would", "could", "should", "being", "having", "might", "through", "across", "still", "really"}


def _numbers(text: str) -> list[str]:
    return sorted(re.findall(r"\d[\d,.]*\d|\d", text))


def _quotes(text: str) -> list[str]:
    return re.findall(r"“([^”]+)”", text)


def _stems(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in STOP}


def faithful(original: str, rewrite: str) -> list[str]:
    problems = []
    if not 0.75 <= len(rewrite) / max(len(original), 1) <= 1.7:
        problems.append("length")
    if _numbers(rewrite) != _numbers(original):
        problems.append("numbers changed")
    for qt in _quotes(original):
        if f"“{qt}”" not in rewrite and f"\"{qt}\"" not in rewrite:
            problems.append(f"quote changed: {qt[:40]}")
    orig_words = set(re.findall(r"[a-z0-9]+", original.lower()))
    rew_words = set(re.findall(r"[a-z0-9]+", rewrite.lower()))
    for m in re.finditer(r"(?<!^)(?<![.!?:]\s)(?<![“\"])([A-Z][a-zA-Z0-9]+)", original):
        if m.group(1).lower() not in rew_words:
            problems.append(f"dropped name {m.group(1)}")
    for m in re.finditer(r"(?<!^)(?<![.!?:]\s)(?<![“\"])\b([A-Z][a-zA-Z0-9]+)", rewrite):
        if m.group(1).lower() not in orig_words:
            problems.append(f"new name {m.group(1)}")
    low, olow = rewrite.lower(), original.lower()
    for t in RISKY:
        if t in low and t not in olow:
            problems.append(f"term {t}")
    new = _stems(rewrite) - _stems(original)
    if len(new) > max(5, 0.25 * len(_stems(rewrite))):
        problems.append(f"too many new words ({len(new)})")
    bad = [w for w in new if any(w.startswith(a[:6]) or a.startswith(w) for a in ATTRIBUTION)]
    if bad:
        problems.append(f"attributes thoughts/feelings: {sorted(bad)}")
    return problems


def _strip(text: str) -> str:
    # strip markdown emphasis/headings, but keep a lone "*" inside words such as O*NET
    text = re.sub(r"\*\*|__|`|^#+\s*", "", text.replace("\r", "")).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip('"').strip()


def _protect(text: str) -> tuple[str, dict[str, str]]:
    """Replace quotations and numbers with tokens so the model cannot alter them."""
    mapping: dict[str, str] = {}

    def letters(i: int) -> str:  # 0 -> A, 25 -> Z, 26 -> AA (no digits, so numbers can't collide with tokens)
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    def sub(prefix: str):
        def f(m):
            key = f"[{prefix}{letters(sum(1 for k in mapping if k.startswith('[' + prefix)))}]"
            mapping[key] = m.group(0)
            return key
        return f

    text = re.sub(r"\d[\d,.]*\d|\d", sub("N"), text)      # numbers first (also those inside quotes)
    text = re.sub(r"“[^”]+”", sub("Q"), text)       # then whole quotations
    # nested restore order: quotations contain number tokens, so restore Q before N
    return text, dict(sorted(mapping.items(), key=lambda kv: kv[0][1] != "Q"))


def _restore(text: str, mapping: dict[str, str]) -> str | None:
    for key, value in mapping.items():  # Q tokens first: their values may contain N tokens
        expected = 1 if key[1] == "Q" else text.count(key)
        if key[1] == "Q" and text.count(key) != 1:
            return None
        text = text.replace(key, value)
        if key[1] == "N" and expected == 0:
            return None
    if re.search(r"\[[QN][A-Z]+\]", text):
        return None
    return text


async def _polish(paragraph: str) -> tuple[str, bool]:
    masked, mapping = _protect(paragraph)
    out = await llm.chat(POLISH_PROMPT, masked, max_tokens=900, temperature=0.4)
    if out:
        restored = _restore(_strip(out), mapping)
        if restored is None:
            log.info("Polish rejected (tokens changed): %s", out[:120])
            return paragraph, False
        problems = faithful(paragraph, restored)
        if not problems:
            return restored, True
        log.info("Polish rejected (%s): %s", problems, restored[:120])
    return paragraph, False


GREETING_PROMPT = """You write the opening greeting of Hive, a psychology-test app, for a visitor who just finished \
a test. You get FACTS about their visit, taken from the site's analytics.

Write 2 or 3 short, friendly, playful sentences (25 to 70 words) that greet the visitor and weave in 4 to 6 of the \
facts, for example: "Hey, how's it going in Tirupati? Windows 11 on a desktop, no touch screen, and a steady \
4g-class line from National Knowledge Network..." Pick a DIFFERENT selection of facts and a different opening \
each time (Hey / Hello / Namaste / Greetings / Welcome back / Good evening ...). Address the visitor as "you".

Rules: use ONLY the facts. Do not invent weather, food, drinks, mood, tiredness, activities, sounds, scenery or \
anything else not in the facts, and do not describe the visitor's personality. The visitor has just finished a test: do not wish them luck with it and do not mention the result. Plain text only."""

INVENTED_SCENE = ["p.m", "a.m", "pm", "o'clock", "curious", "explorer", "heart of", "rain", "sunny", "sunshine", "weather", "cloud", "storm", "breeze", "monsoon", "snow", "cold", "chilly",
                  "warm", "hot ", "coffee", "chai", "tea", "snack", "dinner", "lunch", "breakfast", "sleep", "tired",
                  "bed", "cozy", "cosy", "relax", "stars", "moon", "sky", "quiet", "silence", "music", "traffic",
                  "noise", "mood", "happy", "sad", "excited", "bored", "busy", "street", "window", "room", "desk "]
GREETING_OK_CAPS = {"Hey", "Hi", "Hello", "Namaste", "Greetings", "Welcome", "Good", "Hive", "You", "Your", "It",
                    "It's", "That", "This", "And", "With", "On", "In", "At", "From", "Here", "Looks", "Nice", "Great",
                    "Not", "No", "A", "An", "The", "So", "What", "How", "How's", "Hope", "Evening", "Morning",
                    "Afternoon", "Night", "Thanks", "Happy", "We", "I", "Enjoy", "Enjoying", "Seems", "Sounds",
                    "Quite", "Just", "Let's", "Ready", "Plus", "Also", "Oh", "Wow", "Ah", "Whether", "Since", "Today",
                    "Tonight", "Love", "Fancy", "Cheers", "Ahoy", "Bonjour", "Hola", "You're", "You've", "You\u2019re",
                    "You\u2019ve", "We're", "We\u2019re", "We've", "I'm", "I\u2019m", "Is", "Are", "Did", "Do", "Nice"}


def _greeting_ok(text: str, facts: str) -> list[str]:
    problems = []
    words = len(text.split())
    if not 15 <= words <= 90:
        problems.append(f"length {words}")
    if set(_numbers(text)) - set(_numbers(facts)):
        problems.append("new numbers")
    low, flow = text.lower(), facts.lower()
    for w in INVENTED_SCENE + RISKY:
        w = w.strip()
        if re.search(rf"{re.escape(w)}", low) and not re.search(rf"{re.escape(w)}", flow):
            problems.append(f"invented '{w}'")
    fact_words = set(re.findall(r"[a-z0-9]+", flow))
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9']+)", text):
        w = m.group(1)
        if w not in GREETING_OK_CAPS and w.lower() not in fact_words:
            problems.append(f"name '{w}'")
    if "first visit" in flow and re.search(r"welcome back|\bagain\b|returning|nice to see you back", low):
        problems.append("treats a first visit as a return")
    if "returning visitor" in flow and re.search(r"first (visit|time)", low):
        problems.append("treats a return as a first visit")
    used = sum(1 for v in re.findall(r"[a-z0-9]{4,}", flow) if v in low)
    if used < 4:
        problems.append("too few facts used")
    return problems


async def greeting(profile: dict[str, str]) -> str | None:
    if not profile:
        return None
    facts = "\n".join(f"- {k}: {v}" for k, v in profile.items())
    for _ in range(2):
        out = await llm.chat(GREETING_PROMPT, f"FACTS:\n{facts}", max_tokens=200, temperature=1.0)
        if not out:
            return None
        text = _strip(out)
        problems = _greeting_ok(text, facts)
        if not problems:
            return text
        log.info("Greeting rejected (%s): %s", problems, text[:120])
    return None


async def compose(portrait: dict, profile: dict[str, str], fallback_greeting: str | None, *,
                  use_ai: bool = False) -> dict:
    """Return the structured write-up. Only section bodies and the greeting can be AI-worded."""
    sections = [dict(sec) for sec in portrait["sections"]]
    result = {"title": portrait["title"], "tagline": portrait.get("tagline"), "greeting": fallback_greeting,
              "sections": sections, "source": "template", "model": None, "polished": 0, "ai_greeting": False}
    if not use_ai or not llm.enabled():  # only with the user's explicit consent
        return result

    targets = [i for i, sec in enumerate(sections) if len(sec["body"].split()) >= 20]
    polished, ai_greet = await asyncio.gather(
        asyncio.gather(*(_polish(sections[i]["body"]) for i in targets)),
        greeting(profile),
    )
    count = 0
    for i, (text, ok) in zip(targets, polished):
        sections[i]["body"] = text
        count += ok
    used_ai = bool(count or ai_greet)
    return {**result, "sections": sections, "greeting": ai_greet or fallback_greeting,
            "source": "llm" if used_ai else "template", "model": config.NVIDIA_CHAT_MODEL if used_ai else None,
            "polished": count, "polish_targets": len(targets), "ai_greeting": bool(ai_greet)}
