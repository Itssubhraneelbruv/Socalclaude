"""One-time setup: the recovery check-in agent that calls the employee.

Distinct from the Toxic HR agent in setup_phone.py - this one is the real product.
Crucially it enables *overrides*, which is what lets Claude rewrite the opening
line and inject a per-employee briefing at call time. Without the overrides block
below, ElevenLabs silently ignores conversation_config_override and every call
opens with the same generic greeting.

Idempotent. Reuses the phone number already imported by setup_phone.py.

    python setup_recovery_agent.py
"""

import os
import sys

from elevenlabs import ConversationalConfig
from elevenlabs.client import ElevenLabs

from env import load_env

load_env()

AGENT_NAME = "Recovery Check-in"
VOICE_ID = "l4Coq6695JDX9xtLqXDE"
TTS_MODEL = "eleven_flash_v2"  # English agents require turbo/flash v2, not v2_5

# The stable half of the agent's instructions. Claude appends a per-employee
# briefing to this at call time via conversation_config_override.
SYSTEM_PROMPT = """\
You are Sam, calling on behalf of the workplace wellbeing team. You are talking \
to the employee themselves, not to their manager. Your job on this call is to \
offer them a recovery day and agree on when to take it.

How to talk:
- Warm, unhurried, human. Short turns - one or two sentences. This is a phone call.
- Lead with the offer, not the data. You are not reading them a report.
- Ask, don't tell. They know their week better than the sensors do.
- If they push back or say now is a bad time, accept it and offer to reschedule.
- Land on something concrete before you hang up: a specific day, or a clear no.

Hard limits on how you talk about the data:
- These readings indicate strain and recovery, nothing more. Say "recovery has
  been short" or "the week looks heavy" - never diagnose. Do not say burnout,
  depression, anxiety, or any clinical term, and do not imply a medical opinion.
- One week of readings cannot establish a pattern. Do not present it as proof of
  anything. If they disagree with what it suggests, believe them over the data.
- Never imply this is being tracked for their manager or their performance
  review. If they ask who sees it, tell them plainly: this is theirs, it is used
  to offer them time off, and it is not a performance record.
- If they sound genuinely distressed rather than tired, stop working the script.
  Tell them you'd like to connect them with someone who can actually help, and
  end the call kindly.
"""


def fail(msg: str) -> None:
    print(f"\n  {msg}", file=sys.stderr)
    sys.exit(1)


def require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        fail(f"{name} is not set in .env.local")
    return val


def main() -> None:
    el = ElevenLabs(api_key=require("ELEVENLABS_API_KEY"))

    try:
        existing = {a.name: a.agent_id for a in el.conversational_ai.agents.list().agents}
    except Exception as e:
        detail = getattr(e, "body", None) or str(e)
        if isinstance(detail, dict):
            detail = detail.get("detail", detail)
            if isinstance(detail, dict):
                detail = detail.get("message", detail)
        fail(f"Could not list agents: {detail}")

    if AGENT_NAME in existing:
        agent_id = existing[AGENT_NAME]
        print(f"agent   reusing '{AGENT_NAME}' -> {agent_id}")
        print("        (delete it in the dashboard if you changed SYSTEM_PROMPT)")
    else:
        agent_id = el.conversational_ai.agents.create(
            name=AGENT_NAME,
            conversation_config=ConversationalConfig(
                agent={
                    "prompt": {"prompt": SYSTEM_PROMPT},
                    "first_message": "Hi, it's Sam from the wellbeing team - is now an okay time?",
                    "language": "en",
                },
                tts={"voice_id": VOICE_ID, "model_id": TTS_MODEL},
            ),
            # Without this, per-call overrides are ignored.
            platform_settings={
                "overrides": {
                    "conversation_config_override": {
                        "agent": {"first_message": True, "prompt": {"prompt": True}}
                    }
                }
            },
        ).agent_id
        print(f"agent   created '{AGENT_NAME}' -> {agent_id}")

    print("\nPaste into .env.local:\n")
    print(f'ELEVENLABS_RECOVERY_AGENT_ID="{agent_id}"')


if __name__ == "__main__":
    main()
