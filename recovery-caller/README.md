# recovery-caller

Turns the dashboard's **Assign Day Off** button into an actual phone call.

```
click  ->  load subject data  ->  Claude writes the call brief  ->  ElevenLabs dials
                                  (opening line + agent briefing)     via Twilio
```

Claude never just says "take a day off". It reads the subject's data and writes the
specific opening line plus a briefing that goes into the agent's system prompt, so
the agent can talk about *this* person's period rather than reciting a template.

## Files

| File | Does |
|---|---|
| `employees.py` | The three subjects and a loader per dataset shape |
| `brief.py` | The Claude step — structured output, one call |
| `server.py` | FastAPI: serves the dashboard, exposes the pipeline |
| `setup_recovery_agent.py` | One-time: creates the ElevenLabs agent |
| `setup_phone.py` | One-time: imports the Twilio number into ElevenLabs |
| `env.py` | Finds `.env.local` from any working directory |
| `make_call.py` | Standalone dialer, no dashboard |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env.local        # fill in the keys
python setup_phone.py             # imports the Twilio number  -> paste ID back
python setup_recovery_agent.py    # creates the agent          -> paste ID back
```

Then:

```bash
uvicorn server:app --reload --port 8000
open http://localhost:8000
```

Click **Assign Day Off**. A log panel appears bottom-right showing each stage live.

Brief only, no phone call:

```bash
python brief.py jimmy      # or jiwon / jkwon
curl -X POST http://localhost:8000/api/assign-day-off \
  -H "content-type: application/json" -d '{"dry_run":true}'
```

## Subjects

| id | Source | Span | Shape |
|---|---|---|---|
| `jimmy` | `data/jimmy_week.json` | 1 week | wearable + room sensors |
| `jiwon` | `overachiever_burnout_chat_dataset.json` | 12 weeks | work chat + weekly features |
| `jkwon` | `p1-overachiever-work-chat.json` | 14 weeks | work chat, ends in leave |

The button always calls about one subject — `DEFAULT_EMPLOYEE` in `server.py`.
Change that one string to demo a different dataset.

`jiwon` is Korean-primary; `employees.py` prefers the `text_en` translations and
strips Hangul from mixed strings, so `"Engineering Manager (지원의 매니저)"` survives
as `"Engineering Manager"` rather than being dropped.

## Endpoints

| Endpoint | Notes |
|---|---|
| `GET /` | The dashboard |
| `GET /api/assign-day-off/stream` | SSE, one event per stage — what the button uses |
| `POST /api/assign-day-off` | Same pipeline, single response. `{"dry_run":true}` skips the call |
| `GET /api/employees` | The registry |

The button uses SSE because Claude takes ~15–25s and emits nothing in between; the
server sends a heartbeat each second so the log visibly ticks instead of hanging.

## Three things that will bite you

**Agent overrides must be enabled at creation.** `setup_recovery_agent.py` sets
`platform_settings.overrides`. Without it ElevenLabs **silently ignores** the
per-call override and every call opens with the same generic greeting — no error.

**A prompt override replaces the prompt, it does not append.** `_agent_prompt()` in
`server.py` prepends the base persona, so the guardrails survive. Drop that and the
agent loses its constraints for that call.

**English agents need `eleven_flash_v2`, not `v2_5`.** Anything else is rejected with
*"English Agents must use turbo or flash v2."* `eleven_v3` is TTS-only and cannot be
used for live conversation at all.

## Data handling

Each subject in `employees.py` carries an `evidence` block stating what its data can
and cannot support; it goes into Claude's system prompt verbatim. The constraints
come from the dataset READMEs, and they are load-bearing rather than decorative:

- Participant-facing framing. Never phrased as something a manager reads.
- No diagnoses or clinical labels. "Recovery deficit" and "sustained strain" are the
  register; "burnout" is not, and one week cannot establish it either way.
- Within-person comparison only — there is no population baseline here.
- The person's own account outranks the data.
- Data is synthetic. Never presented as fact about a real person.

`jimmy_week.json` is 6 MB because of its 10,080-row `minutes` array. The loaders drop
it; only the ~10 KB summary layers reach a prompt.

For `jiwon`, `ground_truth.intervention_opportunities` records the finding the whole
call design rests on: at week 8 a day-off offer framed as *performance-adjacent* was
declined; at week 12 the same offer framed as *explicitly non-performance* was
accepted. Framing decided the outcome, so the agent leads with it.
