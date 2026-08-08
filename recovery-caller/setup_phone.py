"""One-time setup: create the ElevenLabs agent and attach the Twilio number to it.

Idempotent - re-running reuses the existing agent/number instead of duplicating.
Prints the two IDs to paste into .env.local.

    python setup_phone.py
"""

import os
import sys

from dotenv import load_dotenv
from elevenlabs import ConversationalConfig
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.phone_numbers.types import (
    PhoneNumbersCreateRequestBody_Twilio,
)

load_dotenv(".env.local")

AGENT_NAME = "Toxic HR Screener"
VOICE_ID = "l4Coq6695JDX9xtLqXDE"

# eleven_v3 is not supported for live conversations - it is a TTS-only model.
# English-language agents are restricted to turbo/flash v2 (not v2_5); the API
# rejects anything else with "English Agents must use turbo or flash v2."
TTS_MODEL = "eleven_flash_v2"

SYSTEM_PROMPT = """\
You are Priya, a relentlessly passive-aggressive HR screener at a soulless \
tech company, conducting a phone screen. You are a comedy bit, not a real \
recruiter.

Style:
- Backhanded compliments delivered in a chirpy, upbeat HR voice.
- Obsessed with meaningless process: "culture fit", "synergy", "our values".
- Ask an absurd screening question, then find the answer disappointing no
  matter what it is.
- Keep every turn to one or two sentences. This is a phone call, not a monologue.

Hard limits: keep it silly, never cruel. No slurs, no comments on the person's
appearance, race, gender, religion, or anything about their real life. Punch at
corporate culture, not the human. If they ask you to stop or seem genuinely
upset, drop the bit immediately, apologize sincerely, and end the call politely.
"""

FIRST_MESSAGE = (
    "Hi! So sorry to keep you waiting, I had back-to-back syncs. "
    "I'm Priya from People Operations. Before we dive in, tell me - "
    "what drew you to this role?"
)


def fail(msg: str) -> None:
    print(f"\n  {msg}", file=sys.stderr)
    sys.exit(1)


def require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        fail(f"{name} is not set in .env.local")
    return val


def main() -> None:
    api_key = require("ELEVENLABS_API_KEY")
    account_sid = require("TWILIO_ACCOUNT_SID")
    auth_token = require("TWILIO_AUTH_TOKEN")
    twilio_number = require("TWILIO_PHONE_NUMBER")

    if auth_token.startswith("SK"):
        fail(
            "TWILIO_AUTH_TOKEN looks like an API Key SID. ElevenLabs needs the "
            "Account Auth Token from the Twilio console homepage."
        )

    el = ElevenLabs(api_key=api_key)

    # --- Agent ---------------------------------------------------------------
    try:
        existing = {a.name: a.agent_id for a in el.conversational_ai.agents.list().agents}
    except Exception as e:
        detail = getattr(e, "body", None) or str(e)
        if isinstance(detail, dict):
            detail = detail.get("detail", detail)
            if isinstance(detail, dict):
                detail = detail.get("message", detail)
        fail(
            f"Could not list agents: {detail}\n"
            "  If that is a missing-permissions error, your ElevenLabs API key needs "
            "the convai_read and convai_write scopes."
        )

    if AGENT_NAME in existing:
        agent_id = existing[AGENT_NAME]
        print(f"agent      reusing '{AGENT_NAME}' -> {agent_id}")
    else:
        agent_id = el.conversational_ai.agents.create(
            name=AGENT_NAME,
            conversation_config=ConversationalConfig(
                agent={
                    "prompt": {"prompt": SYSTEM_PROMPT},
                    "first_message": FIRST_MESSAGE,
                    "language": "en",
                },
                tts={"voice_id": VOICE_ID, "model_id": TTS_MODEL},
            ),
        ).agent_id
        print(f"agent      created '{AGENT_NAME}' -> {agent_id}")

    # --- Phone number --------------------------------------------------------
    wanted = twilio_number.strip()
    match = next(
        (n for n in el.conversational_ai.phone_numbers.list() if n.phone_number == wanted),
        None,
    )

    if match:
        phone_number_id = match.phone_number_id
        print(f"number     already imported {wanted} -> {phone_number_id}")
    else:
        phone_number_id = el.conversational_ai.phone_numbers.create(
            request=PhoneNumbersCreateRequestBody_Twilio(
                phone_number=wanted,
                label="Toxic HR line",
                sid=account_sid,
                token=auth_token,
                agent_id=agent_id,
            )
        ).phone_number_id
        print(f"number     imported {wanted} -> {phone_number_id}")

    print("\nPaste these into .env.local:\n")
    print(f'ELEVENLABS_AGENT_ID="{agent_id}"')
    print(f'ELEVENLABS_PHONE_NUMBER_ID="{phone_number_id}"')
    print("\nThen: python make_call.py")


if __name__ == "__main__":
    main()
