"""The three synthetic subjects, and how to compact each one for a prompt.

The datasets have three different shapes, so each gets its own loader:

  jimmy  data/jimmy_week.json                      1 week,  wearable + room sensors
  jiwon  overachiever_burnout_chat_dataset.json   12 weeks, work chat + weekly features
  jkwon  p1-overachiever-work-chat.json           14 weeks, work chat, ends in leave

Each loader returns compact context only. jimmy_week.json in particular is 6 MB
because of its `minutes` array (10,080 per-minute readings) - that array must never
reach a prompt. See socalclaude/data/README.md.
"""

import functools
import json
import re
from pathlib import Path

def _find_repo() -> Path:
    """Locate the data repo, whether this file sits inside it or beside it.

    Works both from the project root (with the repo cloned into ./socalclaude) and
    from inside the repo itself (recovery-caller/employees.py -> repo root).
    """
    here = Path(__file__).resolve().parent
    for candidate in (here / "socalclaude", here.parent, here):
        if (candidate / "burnout-dashboard").is_dir():
            return candidate
    return here / "socalclaude"  # nothing found; error messages will point at this


REPO = _find_repo()

# Hangul syllables, jamo, and compatibility jamo.
_HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]+")
_EMPTY_BRACKETS = re.compile(r"\(\s*[·,]?\s*\)|\[\s*\]")


def _deko(value):
    """Strip Korean, keeping the English half of mixed strings.

    The jiwon dataset is Korean-primary with per-message English translations. This
    prefers any `*_en` sibling, then removes Hangul from what's left rather than
    dropping the whole value - "Engineering Manager (지원의 매니저)" should survive
    as "Engineering Manager", not vanish.
    """
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            if f"{key}_en" in value:
                continue  # a translated sibling exists; that one wins
            clean = _deko(val)
            if clean not in (None, "", {}, []):
                out[key[:-3] if key.endswith("_en") else key] = clean
        return out
    if isinstance(value, list):
        return [c for c in (_deko(v) for v in value) if c not in (None, "", {}, [])]
    if isinstance(value, str):
        text = _EMPTY_BRACKETS.sub("", _HANGUL.sub("", value))
        text = re.sub(r"\s{2,}", " ", text).strip(" -—·,;:")
        # Punctuation-only leftovers carry no meaning.
        return text if re.search(r"[A-Za-z0-9]", text) else None
    return value


@functools.lru_cache(maxsize=8)
def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_jimmy(path: str) -> dict:
    d = _read(path)
    return {k: d[k] for k in ("metadata", "ieq_targets", "week_summary", "daily") if k in d}


def _load_jiwon(path: str) -> dict:
    d = _deko(_read(path))
    keep = (
        "observation_window",
        "persona",
        "actors",
        "channels",
        "feature_schema",
        "narrative_phases",
        "weekly_features",
        "ground_truth",
        "messages",
    )
    return {k: d[k] for k in keep if k in d}


def _load_jkwon(path: str) -> dict:
    d = _read(path)
    # Already English and only 19 KB - keep everything except the boilerplate header.
    return {k: v for k, v in d.items() if k not in ("schema_version", "generated_at", "dataset")}


# `evidence` is the one-paragraph explanation of what this data can and cannot
# support. It goes into Claude's system prompt verbatim, so the constraints travel
# with the data instead of being duplicated in the prompt.
EMPLOYEES = {
    "jimmy": {
        "id": "jimmy",
        "name": "Jimmy",
        "role": "Office worker",
        "path": REPO / "data" / "jimmy_week.json",
        "loader": _load_jimmy,
        "span": "one week (Mon 2026-08-03 to Sun 2026-08-09)",
        "evidence": """\
Wearable physiology plus room environment plus twice-daily self-report, sampled
every minute for ONE WEEK. One person, no population baseline, so every comparison
must be within-person: day vs day, weekday vs weekend. Never compare to a norm.

The single most important field is week_summary.recovery_return - whether the
weekend restored Monday's overnight RMSSD baseline. Lead with it.

One week cannot establish burnout; burnout is a months-long construct. Do not say
it. "Recovery deficit", "insufficient overnight recovery", "elevated strain" are
the correct register. The `coupling` correlations are artifacts of the generator -
never present them as proof the room caused the physiology.

The changeable levers are the environment parameters in ieq_targets (every one is
outside its band, and each maps to a facilities fix) and the after-hours
encroachment pattern. Reciting heart-rate or sleep numbers back at someone is not
a recommendation.""",
    },
    "jiwon": {
        "id": "jiwon",
        "name": "Jiwon",
        "role": "Senior Backend Engineer, Payments Platform",
        "path": REPO / "overachiever_burnout_chat_dataset.json",
        "loader": _load_jiwon,
        "span": "twelve weeks (2026-05-11 to 2026-08-02)",
        "evidence": """\
Twelve weeks of work chat across eight channels, plus weekly behavioural features,
telemetry and self-report. Korean-language source; you are seeing the English
translations. Refer to the subject as Jiwon.

This subject's defining property is disclosure_bias: "I'm fine" is the default
reply and negative states are never verbalised. Objective signals (after-hours
messages, response latency, sleep-window erosion) crossed threshold at week 5;
self-report did not align until week 12 - a five-week detection lag. So do not
treat the self-report as the ground truth, and do not open the call by asking how
they are: you will be told "fine" and that answer is sincere.

Read ground_truth.intervention_opportunities carefully - it is the most useful
thing in the file. Week 8, a manager offer framed as performance-adjacent was
DECLINED. Week 12, the same offer framed as explicitly non-performance was
ACCEPTED. Framing is the variable that decided the outcome. Build the call around
that finding.

Note the confounds: the week-11 drop in demand_load is not recovery (exhaustion
lags load), and the falling self_imposed_ratio is psychological withdrawal here,
not healthy boundary-setting. The invisible_labor_ledger holds ~113 hours of real
work that never entered a performance review - about 60% of the reward imbalance.
Twelve weeks is long enough to describe a trajectory, but still say "sustained
strain", never a clinical label.""",
    },
    "jkwon": {
        "id": "jkwon",
        "name": "J. Kwon",
        "role": "Senior Backend Engineer",
        "path": REPO / "p1-overachiever-work-chat.json",
        "loader": _load_jkwon,
        "span": "fourteen weeks (2026-02-02 to 2026-05-04)",
        "evidence": """\
Fourteen weeks of work chat with weekly metrics, ending at week 14 in a leave of
absence. Same archetype as Jiwon - voluntary overload from an internal standard,
not an external demand - but the collapse is acute rather than gradual.

The file's own guidance is the rule to follow: detect on LEVEL and DIVERGENCE
(measured_strain vs self_reported_strain, mean gap 53 points), never on trend.
Self-report and sentiment are confirmatory at best. There were zero sentiment
alerts before the collapse and the trend model's lead time was zero weeks. The
only text feature that moved beforehand was median_message_words, two weeks out.

The last message - "I don't really know what happened. I was fine on Friday." -
is annotated as sincere: the internal signal genuinely was not available to the
subject. Treat that as the operating assumption. This person cannot self-report
their way to a day off, which is the entire reason for calling.

Also check pto_days_with_activity: nominal time off that was worked through does
not count as recovery. Note that week 14 has already happened in this record, so
frame the call as catching the next one earlier, not as preventing this one.""",
    },
}


def load(employee_id: str) -> tuple[dict, str]:
    """Return (employee record, compact context as a JSON string)."""
    try:
        emp = EMPLOYEES[employee_id]
    except KeyError:
        raise KeyError(f"unknown employee {employee_id!r}; known: {sorted(EMPLOYEES)}") from None
    if not emp["path"].exists():
        raise FileNotFoundError(
            f"{emp['path']} is missing. Clone the data repo:\n"
            "  git clone https://github.com/Itssubhraneelbruv/Socalclaude.git socalclaude"
        )
    context = emp["loader"](str(emp["path"]))
    return emp, json.dumps(context, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    for eid in EMPLOYEES:
        try:
            emp, ctx = load(eid)
            print(f"{eid:8} {len(ctx):>8,} chars  ~{len(ctx)//4:>6,} tokens   {emp['span']}")
        except (FileNotFoundError, KeyError) as e:
            print(f"{eid:8} ERROR: {e}")
