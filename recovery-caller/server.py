"""Backend for the burnout dashboard.

Serves the dashboard and wires its "Assign Day Off" button to the full pipeline:

    button click -> load subject data -> Claude writes the brief
                 -> ElevenLabs places the call with that brief injected

Two endpoints do the same work:
  POST /api/assign-day-off         one request, one response (for curl / scripts)
  GET  /api/assign-day-off/stream  same thing over SSE, so the dashboard can show
                                   progress instead of sitting blank for ~20s

    .venv/Scripts/python.exe -m uvicorn server:app --reload --port 8000
    open http://localhost:8000

Requires ELEVENLABS_RECOVERY_AGENT_ID (from setup_recovery_agent.py) and
ELEVENLABS_PHONE_NUMBER_ID (from setup_phone.py) in .env.local.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from elevenlabs.client import ElevenLabs
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from env import load_env

load_env()

# The dashboard button always calls about this one subject. Change to "jiwon" or
# "jkwon" to demo the other datasets; the CLI (brief.py) still takes any of them.
DEFAULT_EMPLOYEE = "jimmy"

from brief import MODEL, build_brief  # noqa: E402  - needs the env loaded first
from employees import EMPLOYEES, REPO, load  # noqa: E402
from setup_recovery_agent import SYSTEM_PROMPT as AGENT_BASE_PROMPT  # noqa: E402

DASHBOARD = REPO / "burnout-dashboard" / "index.html"

app = FastAPI(title="Burnout recovery caller")
app.add_middleware(
    CORSMiddleware,  # so the dashboard also works opened straight from disk
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AssignRequest(BaseModel):
    employee_id: str = DEFAULT_EMPLOYEE
    to_number: str | None = None  # defaults to TARGET_PHONE_NUMBER
    dry_run: bool = False  # generate the brief, skip the call


def _agent_prompt(brief: dict) -> str:
    """Base persona + this call's briefing.

    The prompt override REPLACES the agent's prompt rather than appending to it,
    so the base persona and its guardrails have to be included here.
    """
    return (
        f"{AGENT_BASE_PROMPT}\n\n"
        f"## This call: {brief['employee_name']}\n\n"
        f"{brief['context']}\n\n"
        "Points you can fall back on:\n" + "\n".join(f"- {p}" for p in brief["talking_points"])
    )


def _place_call(brief: dict, to_number: str) -> dict:
    """Dial via ElevenLabs with the brief injected. Raises RuntimeError on failure."""
    agent_id = os.getenv("ELEVENLABS_RECOVERY_AGENT_ID")
    phone_number_id = os.getenv("ELEVENLABS_PHONE_NUMBER_ID")
    missing = [
        n
        for n, v in (
            ("ELEVENLABS_RECOVERY_AGENT_ID", agent_id),
            ("ELEVENLABS_PHONE_NUMBER_ID", phone_number_id),
            ("TARGET_PHONE_NUMBER", to_number),
        )
        if not v
    ]
    if missing:
        raise RuntimeError(f"not set in .env.local: {', '.join(missing)}")

    el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    try:
        result = el.conversational_ai.twilio.outbound_call(
            agent_id=agent_id,
            agent_phone_number_id=phone_number_id,
            to_number=to_number,
            # Overrides only apply because setup_recovery_agent.py enabled them.
            conversation_initiation_client_data={
                "conversation_config_override": {
                    "agent": {
                        "first_message": brief["first_message"],
                        "prompt": {"prompt": _agent_prompt(brief)},
                    }
                },
                "dynamic_variables": {
                    "employee_name": brief["employee_name"],
                    "employee_id": brief["employee_id"],
                },
            },
        )
    except Exception as e:
        detail = getattr(e, "body", None) or str(e)
        raise RuntimeError(f"ElevenLabs rejected the call: {detail}") from None

    if not result.success:
        raise RuntimeError(f"call not placed: {result.message}")

    return {
        "to": to_number,
        "call_sid": result.call_sid,
        "conversation_id": result.conversation_id,
        "transcript_url": (
            f"https://elevenlabs.io/app/conversational-ai/history/{result.conversation_id}"
            if result.conversation_id
            else None
        ),
    }


@app.get("/")
def dashboard():
    if not DASHBOARD.exists():
        raise HTTPException(500, f"dashboard not found at {DASHBOARD}")
    return FileResponse(DASHBOARD)


@app.get("/jimmy_week.json")
def jimmy_data():
    """The dashboard fetches this with a relative path on load."""
    path = EMPLOYEES["jimmy"]["path"]
    if not path.exists():
        raise HTTPException(404, "jimmy_week.json not found - clone the data repo")
    return FileResponse(path, media_type="application/json")


@app.get("/api/employees")
def list_employees():
    return [
        {"id": e["id"], "name": e["name"], "role": e["role"], "span": e["span"]}
        for e in EMPLOYEES.values()
    ]


@app.post("/api/assign-day-off")
def assign_day_off(req: AssignRequest):
    """Claude writes the brief, then ElevenLabs calls with it injected."""
    if req.employee_id not in EMPLOYEES:
        raise HTTPException(400, f"unknown employee_id; known: {sorted(EMPLOYEES)}")
    try:
        brief = build_brief(req.employee_id)
        if req.dry_run:
            return {"brief": brief, "call": None, "dry_run": True}
        call = _place_call(brief, req.to_number or os.getenv("TARGET_PHONE_NUMBER"))
    except KeyError as e:  # missing ANTHROPIC_API_KEY
        raise HTTPException(500, f"missing env var {e}") from None
    except (FileNotFoundError, RuntimeError) as e:
        raise HTTPException(502, str(e)) from None
    return JSONResponse({"brief": brief, "call": call})


@app.get("/api/assign-day-off/stream")
def assign_day_off_stream(
    employee_id: str = DEFAULT_EMPLOYEE,
    to_number: str | None = None,
    dry_run: bool = False,
):
    """Same pipeline, streamed as Server-Sent Events so the UI can show progress.

    Claude takes ~15-25s with no intermediate output of its own, so a heartbeat is
    emitted each second while it runs - that is what keeps the log visibly alive.
    """

    def gen():
        t0 = time.monotonic()

        def ev(step: str, message: str, **extra) -> str:
            payload = {"step": step, "message": message, "t": round(time.monotonic() - t0, 1)}
            return f"data: {json.dumps({**payload, **extra})}\n\n"

        try:
            emp = EMPLOYEES.get(employee_id)
            if emp is None:
                yield ev("error", f"unknown employee {employee_id!r}")
                return

            yield ev("start", f"Recovery day for {emp['name']} - {emp['role']}")

            yield ev("load", f"Reading {emp['path'].name}")
            _, context = load(employee_id)
            yield ev(
                "load_done",
                f"{emp['span']} loaded - {len(context):,} chars (~{len(context) // 4:,} tokens)",
            )

            yield ev("claude", f"{MODEL} reasoning over the data")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(build_brief, employee_id)
                while not future.done():
                    time.sleep(1.0)
                    yield ev("claude_wait", "thinking")
                brief = future.result()

            yield ev("headline", brief["headline"])
            yield ev("opening", brief["first_message"])
            yield ev("brief_done", "Brief ready, guardrails prepended", brief=brief)

            if dry_run:
                yield ev("done", "Dry run - no call placed")
                return

            to = to_number or os.getenv("TARGET_PHONE_NUMBER")
            yield ev("dial", f"Dialling {to} via ElevenLabs + Twilio")
            call = _place_call(brief, to)
            yield ev("done", f"Ringing - call {call['call_sid']}", call=call)

        except Exception as e:  # a stream can't return an HTTP error code mid-flight
            yield ev("error", str(e)[:400])

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
