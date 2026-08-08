"""Place the outbound call. ElevenLabs drives the conversation over your Twilio number.

    python make_call.py                # calls TARGET_PHONE_NUMBER from .env.local
    python make_call.py +13105551234   # calls a specific number

Run setup_phone.py first to get the agent and phone-number IDs.
"""

import os
import sys

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv(".env.local")


def fail(msg: str) -> None:
    print(f"\n  {msg}", file=sys.stderr)
    sys.exit(1)


def require(name: str, hint: str = "") -> str:
    val = os.getenv(name)
    if not val:
        fail(f"{name} is not set in .env.local. {hint}".rstrip())
    return val


def main() -> None:
    api_key = require("ELEVENLABS_API_KEY")
    agent_id = require("ELEVENLABS_AGENT_ID", "Run setup_phone.py first.")
    phone_number_id = require("ELEVENLABS_PHONE_NUMBER_ID", "Run setup_phone.py first.")

    to_number = sys.argv[1] if len(sys.argv) > 1 else require("TARGET_PHONE_NUMBER")
    if not to_number.startswith("+"):
        fail(f"'{to_number}' must be E.164 format, e.g. +13105551234")

    el = ElevenLabs(api_key=api_key)

    print(f"dialing {to_number} ...")
    res = el.conversational_ai.twilio.outbound_call(
        agent_id=agent_id,
        agent_phone_number_id=phone_number_id,
        to_number=to_number,
    )

    if not res.success:
        fail(f"Call rejected: {res.message}")

    print(f"connected      call_sid: {res.call_sid}")
    if res.conversation_id:
        print(f"conversation   {res.conversation_id}")
        print("\nTranscript will appear at:")
        print(f"https://elevenlabs.io/app/conversational-ai/history/{res.conversation_id}")


if __name__ == "__main__":
    main()
