"""English free-text comment generation — templates + lexical variation.

Structure: [opener] + [driver mention] + [state description] + [closer]
Each slot pool is selected by persona voice and latent state.
Ground-truth labels (sentiment polarity, dominant dimension, mentioned drivers)
are emitted alongside the text.

Mirrors text_ko.py. Assembly differs because English needs sentence-initial
capitalization and comma-separated adverbials.
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

# --- Openers ----------------------------------------------------------------
OPENERS = {
    "pos": ["This week,", "Lately,", "The past few weeks,", "Since last week,"],
    "neu": ["This week,", "Nothing much stood out, but", "Lately,", "Honestly, just"],
    "neg": ["To be honest,", "This week,", "Lately I keep finding that",
            "I hesitate to bring this up, but"],
    "sev": ["I can't keep going like this.", "Honestly, I'm at my limit.",
            "At this point,", "It's exhausting to even write this, but"],
}

# --- Driver mentions --------------------------------------------------------
DRIVER_CLAUSES: Dict[str, List[str]] = {
    "workload": [
        "the work just keeps piling up",
        "there's no sign of the volume letting up",
        "the sheer amount is past what I can handle",
        "I didn't finish even half of what came in",
    ],
    "time_pressure": [
        "the deadlines overlap and there's no room to breathe",
        "the schedules get set far too tight",
        "I'm always working while being chased",
        "I'm shipping things without time to review them properly",
    ],
    "role_ambiguity": [
        "I don't know what I'm actually accountable for",
        "the expectations aren't clear",
        "who makes the call is different every time",
        "the scope of my role keeps shifting",
    ],
    "emotional_labor": [
        "customer conversations drain a lot out of me",
        "dealing with angry people all day is hard",
        "I spend all my energy acting like I'm fine",
        "I keep my own reactions down while handling people",
    ],
    "context_switching": [
        "meetings chop up the day and leave no time to focus",
        "the context switching is far too frequent",
        "something else lands before I finish the first thing",
        "there's no block left where I can go deep",
    ],
    "unpredictability": [
        "priorities flip week to week",
        "I have no idea what things will look like next month",
        "there's no point in planning anything",
        "announcements come down out of nowhere",
    ],
    "lack_of_autonomy": [
        "there's almost nothing I get to decide",
        "even the approach comes down pre-decided",
        "it feels like I'm here only to execute",
    ],
    "lack_of_support_manager": [
        "I barely get a chance to talk to my manager",
        "there's no one to turn to when I'm stuck",
        "my 1:1s keep getting cancelled",
    ],
    "lack_of_support_peer": [
        "it feels like I'm carrying this alone on the team",
        "there isn't really anyone to ask",
        "everyone's buried, so I can't bring myself to ask for help",
    ],
    "lack_of_reward_fairness": [
        "I don't feel recognized for what I put in",
        "my work goes up under someone else's name",
        "the evaluation criteria don't make sense to me",
        "it was clearly my work and it went unmentioned",
    ],
    "lack_of_growth_meaning": [
        "I don't know where this work is going",
        "I get the sense I'm not learning anything",
        "I don't know why I'm here",
    ],
    "lack_of_recovery_opportunity": [
        "I end up checking notifications on weekends too",
        "I booked time off and ended up cancelling it",
        "work doesn't leave my head after I log off",
    ],
}

# --- State descriptions (dominant dimension x intensity) --------------------
STATE_CLAUSES: Dict[str, Dict[str, List[str]]] = {
    "exhaustion": {
        "mid": ["the tiredness doesn't clear", "I don't recover even over the weekend",
                "my stamina isn't what it used to be"],
        "high": ["just getting up in the morning is a struggle",
                 "the word burnout keeps coming to mind",
                 "I sleep and still don't feel rested",
                 "my body seems to be signalling before my head does"],
    },
    "cynicism": {
        "mid": ["I don't care the way I used to", "I've started holding back in meetings",
                "I've learned it's easier to lower my expectations"],
        "high": ["honestly, I've stopped caring", "it stopped mattering whether it goes well",
                 "I'm looking elsewhere", "I think it's better not to expect anything"],
    },
    "reduced_efficacy": {
        "mid": ["I'm not sure I'm doing this well", "I can't see any results",
                "I'm losing confidence in my own judgment"],
        "high": ["I question whether I'm useful here",
                 "nothing I do seems to improve anything", "I'm making more mistakes"],
    },
}

POSITIVE_STATE = [
    "this sprint had a good rhythm",
    "the team helped me a lot",
    "I finally got to focus properly",
    "the schedule had room and I could breathe",
    "I got feedback and the direction became clear",
    "the work sat well in my hands",
    "collaboration went smoothly",
    "I was able to actually take my breaks",
]

NEUTRAL_STATE = [
    "it was neither good nor bad",
    "it went about the same as usual",
    "things are ticking along",
    "it passed uneventfully",
    "not much has changed",
]

# Sentence-initial adverbials — same clause, different surface form
INTENSIFIERS = {
    "mid": ["", "", "Lately, ", "Recently, ", "Increasingly, "],
    "high": ["", "Honestly, ", "Frankly, ", "These days, ", "More and more, "],
}

# --- Closers by voice -------------------------------------------------------
CLOSERS = {
    "stoic": ["I just need to get through this week.", "It's manageable for now.",
              "It's on me to cover more of it.", "It's not a big enough issue to raise."],
    "resentful": ["I've lost count of how many times I've written this.",
                  "I don't expect anything to change.",
                  "Writing it down has never changed anything.",
                  "Leaving this here so at least someone knows."],
    "depleted": ["I'd just like a bit of rest.", "Hoping next week is better.",
                 "There's nothing left to draw from right now."],
    "confused": ["I don't even know who to ask.", "I think this needs sorting out once.",
                 "I'd like to know whether this is normal."],
    "flat": ["Nothing in particular to add.", "That's how it is.", "That's all."],
    "cautious": ["Cautiously, I think it's getting better.", "Better than last month.",
                 "I hope this holds."],
    "steady": ["Overall it's fine.", "No problems at this pace.", "No particular requests."],
    "neutral": ["That's all.", "Sharing for reference."],
}

DRIVER_CONNECT = ["", "And ", "On top of that, ", "Above all, "]

# A hopeful closer contradicts a severe comment — substitute from this pool.
SEV_FALLBACK_CLOSERS = ["This isn't sustainable.", "I need help here.",
                        "I'd like to talk this through.", "I can't carry this alone."]

# Don't stack an adverbial onto a clause that already opens with one
_ADV_PREFIXES = ("honestly", "frankly")


def _cap(clause: str) -> str:
    return clause[0].upper() + clause[1:] if clause else clause


def _sentence(prefix: str, clause: str) -> str:
    """Prefix already carries its own comma and trailing space; otherwise capitalize."""
    return (prefix + clause if prefix else _cap(clause)) + "."


def _intensify(rng: random.Random, clause: str, level: str) -> str:
    if clause.lower().startswith(_ADV_PREFIXES):
        return _sentence("", clause)
    return _sentence(rng.choice(INTENSIFIERS[level]), clause)


def _closer(rng: random.Random, voice: str, bucket: str) -> str:
    if bucket == "sev" and voice in ("cautious", "steady"):
        return rng.choice(SEV_FALLBACK_CLOSERS)
    return rng.choice(CLOSERS.get(voice, CLOSERS["neutral"]))


def _valence_bucket(valence: float, composite: float) -> str:
    if composite >= 0.72 or valence <= -0.60:
        return "sev"
    if valence <= -0.15:
        return "neg"
    if valence >= 0.45:
        return "pos"
    return "neu"


def generate_comment(rng: random.Random, voice: str, valence: float, composite: float,
                     dims: Dict[str, float], top_drivers: List[str]) -> Tuple[str, Dict]:
    """One comment plus its ground-truth labels."""
    bucket = _valence_bucket(valence, composite)
    dominant = max(dims.items(), key=lambda kv: kv[1])[0]
    dom_val = dims[dominant]

    parts: List[str] = []
    mentioned: List[str] = []

    if bucket == "pos":
        parts.append(rng.choice(OPENERS["pos"]) + " " + rng.choice(POSITIVE_STATE) + ".")
        if rng.random() < 0.3 and top_drivers:
            k = top_drivers[0]
            if k in DRIVER_CLAUSES:
                parts.append("That said, " + rng.choice(DRIVER_CLAUSES[k]) + ".")
                mentioned.append(k)
        parts.append(_closer(rng, voice, bucket))
    elif bucket == "neu":
        parts.append(rng.choice(OPENERS["neu"]) + " " + rng.choice(NEUTRAL_STATE) + ".")
        if top_drivers and rng.random() < 0.55:
            k = top_drivers[0]
            if k in DRIVER_CLAUSES:
                parts.append(_sentence("", rng.choice(DRIVER_CLAUSES[k])))
                mentioned.append(k)
        if rng.random() < 0.6:
            parts.append(_closer(rng, voice, bucket))
    else:
        opener = rng.choice(OPENERS[bucket])
        n_drivers = 1 if bucket == "neg" else rng.choice([1, 2, 2])
        picked = [k for k in top_drivers if k in DRIVER_CLAUSES][:n_drivers]
        if picked:
            head = rng.choice(DRIVER_CLAUSES[picked[0]])
            if opener.endswith("."):
                parts.append(opener)
                parts.append(_sentence("", head))
            else:
                parts.append(opener + " " + head + ".")
            mentioned.append(picked[0])
            for k in picked[1:]:
                parts.append(_sentence(rng.choice(DRIVER_CONNECT[1:]),
                                       rng.choice(DRIVER_CLAUSES[k])))
                mentioned.append(k)
        else:
            parts.append(opener if opener.endswith(".") else opener + " it's hard right now.")

        level = "high" if dom_val >= 0.6 else "mid"
        parts.append(_intensify(rng, rng.choice(STATE_CLAUSES[dominant][level]), level))
        # If a second dimension is also elevated, one more sentence follows
        second = sorted(dims.items(), key=lambda kv: kv[1], reverse=True)[1]
        if second[1] >= 0.45 and rng.random() < 0.4:
            lv2 = "high" if second[1] >= 0.6 else "mid"
            parts.append(_sentence("", rng.choice(STATE_CLAUSES[second[0]][lv2])))
        parts.append(_closer(rng, voice, bucket))

    text = " ".join(p.strip() for p in parts if p.strip())
    label = {
        "sentiment_bucket": bucket,
        "dominant_dimension": dominant,
        "mentioned_drivers": ",".join(mentioned),
        "voice": voice,
    }
    return text, label
