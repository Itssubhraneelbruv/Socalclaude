"""Claude reads a subject's data and writes the call brief.

Produces the two things ElevenLabs needs at dial time: the exact opening line the
agent speaks, and a briefing appended to its system prompt so it can hold a
grounded conversation instead of a generic one.

    python brief.py jimmy
    python brief.py jiwon
    python brief.py jkwon
"""

import json
import os

import anthropic

from employees import load

MODEL = "claude-opus-5"

# Trades latency for depth. "low" is ~2x faster; "high" writes a noticeably better
# opening line. Button-click latency is roughly 15-25s at medium.
EFFORT = "medium"

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One line for the dashboard, under 90 chars. What the data shows.",
        },
        "first_message": {
            "type": "string",
            "description": (
                "The exact words the agent speaks when the person picks up. Two "
                "sentences maximum. Warm, human, gets to the point. Must not recite "
                "numbers and must not sound like a form letter."
            ),
        },
        "context": {
            "type": "string",
            "description": (
                "A briefing appended to the agent's system prompt. Tell it what this "
                "person's period actually looked like, which two or three specifics are "
                "worth raising if the conversation goes there, and what to avoid. "
                "Write it as instructions to the agent, not as prose for the employee. "
                "Under 250 words."
            ),
        },
        "talking_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-4 short points the agent can fall back on, employee-facing phrasing.",
        },
    },
    "required": ["headline", "first_message", "context", "talking_points"],
    "additionalProperties": False,
}

# Constraints that hold for every subject. The per-subject `evidence` block in
# employees.py carries what is specific to that dataset's shape.
SYSTEM = """\
You brief a voice agent that is about to phone {name} and offer them a recovery \
day off. You are writing for the agent, not for {name} - except for first_message, \
which is spoken aloud verbatim.

The subject is {name}, {role}. The data covers {span}. It is synthetic.

Constraints that hold regardless of what the data shows:

- Write for the employee, never about them for a manager. Nothing you produce
  should read as surveillance or as performance evidence. If they ask who sees
  this, the honest answer is: it is theirs, it exists to offer them time off, and
  it is not part of any review.
- These signals index strain and recovery, not health. Never output a diagnosis or
  clinical label - not burnout, not depression, not anxiety, no medical opinion.
- Never present synthetic data as established fact about a real person.
- The person's own account of their week outranks the data. If they say the reading
  is wrong, believe them.
- Structural causes beat personal ones. Where the data points at workload,
  scheduling, scope, or the physical environment, name that rather than implying
  the person should cope better.
- The call has to land somewhere concrete: a specific day off, or a clear no.

What this particular dataset can and cannot support:

{evidence}

Sound like a person who read the data and cares, not like a system generating a \
notification."""


def build_brief(employee_id: str, api_key: str | None = None) -> dict:
    """Ask Claude for the call brief. Returns the validated schema above."""
    emp, context = load(employee_id)
    client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,  # thinking is on by default on Opus 5 and shares this budget
        system=SYSTEM.format(
            name=emp["name"], role=emp["role"], span=emp["span"], evidence=emp["evidence"]
        ),
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": BRIEF_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Here is {emp['name']}'s data. Write the brief for the call.\n\n"
                    f"<data>\n{context}\n</data>"
                ),
            }
        ],
    )

    # output_config.format guarantees the text block is valid JSON matching the schema.
    text = next(b.text for b in response.content if b.type == "text")
    brief = json.loads(text)
    brief["employee_id"] = emp["id"]
    brief["employee_name"] = emp["name"]
    return brief


if __name__ == "__main__":
    import sys

    from env import load_env

    load_env()
    eid = sys.argv[1] if len(sys.argv) > 1 else "jimmy"

    b = build_brief(eid)
    print(f"\n=== {b['employee_name']} ===\n")
    print(f"headline\n  {b['headline']}\n")
    print(f"first_message\n  {b['first_message']}\n")
    print(f"context\n  {b['context']}\n")
    print("talking_points")
    for p in b["talking_points"]:
        print(f"  - {p}")
