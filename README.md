# CareCloud Voice AI — Patient Registration

[![ci](https://github.com/m-talha-shaikh/-voice-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/m-talha-shaikh/-voice-agent/actions/workflows/ci.yml)

> **Demo (fill after Render deploy)**  
> **Phone:** `+1 (945) 667-5598`  
> **API:** `https://YOUR-SERVICE.onrender.com`  
> **Dashboard:** `https://YOUR-SERVICE.onrender.com/dashboard`  
> **OpenAPI:** `https://YOUR-SERVICE.onrender.com/docs`

Call the US number (or use **Talk to the agent in your browser** on the dashboard) and register a patient conversationally. Data persists in Neon Postgres and is queryable via REST.

---

## Architecture

```
Caller ──PSTN──▶ Vapi (telephony + STT/TTS + LLM + barge-in)
                   │  HTTPS tool-calls / webhooks + X-Vapi-Secret
                   ▼
        FastAPI (Render)
        ├── api/        REST /patients, /appointments
        ├── voice/      Vapi adapter only
        ├── services/   shared domain logic
        ├── schemas/    single validation source of truth
        ├── db/         SQLAlchemy + Alembic → Neon
        ├── dashboard/  Jinja2 UI + Vapi Web SDK
        └── prompts/    Riley system prompt
```

Separation of concerns: telephony stays in `voice/`; validation in `schemas/`; persistence in `db/`. Voice tools and REST hit the **same** service layer (allowed by the assessment PDF).

Architecture decisions and trade-offs are documented in the **Tech stack justification** and **Edge cases** sections below.

## Tech stack justification

| Layer | Choice | Why |
|-------|--------|-----|
| Telephony | Vapi | Free US inbound number; barge-in; server tools; end-of-call reports |
| STT | Deepgram nova-3 (own key via Vapi) | Accurate on names/spelling; multi language; uses Deepgram credit |
| LLM | Groq `llama-3.3-70b-versatile` | Free, fast tool calling; Vapi OpenAI as fallback |
| Backend | FastAPI + Pydantic v2 | Typed validation + `/docs` for reviewers |
| DB | Neon Postgres + Alembic | Real constraints; free forever; survives redeploys |
| Host | Render free + cron-job.org | Free HTTPS; keep-alive prevents cold starts mid-call |
| Dashboard | Jinja2 on same service | Email asked for a dashboard; one URL |

## Quick test (60 seconds)

```bash
# Health
curl -s https://YOUR-SERVICE.onrender.com/healthz | jq

# List patients (seed includes Jane Doe / John Smith)
curl -s 'https://YOUR-SERVICE.onrender.com/patients?last_name=Doe' | jq

# Create via API
curl -s -X POST https://YOUR-SERVICE.onrender.com/patients \
  -H 'Content-Type: application/json' \
  -d '{
    "first_name":"Sam","last_name":"Taylor","date_of_birth":"05/05/1991",
    "sex":"Other","phone_number":"5125550188","address_line_1":"1 Main St",
    "city":"Austin","state":"TX","zip_code":"78701"
  }' | jq
```

Then dial **+19456675598** or open `/dashboard` and click the browser call button.

## Environment variables

| Name | Required | Description |
|------|----------|-------------|
| `DATABASE_URL` | yes | Neon pooled Postgres URL |
| `VAPI_API_KEY` | yes | Vapi private key |
| `VAPI_PUBLIC_KEY` | yes | Browser call button |
| `VAPI_WEBHOOK_SECRET` | yes | Shared secret you generate; sent as `X-Vapi-Secret` |
| `PUBLIC_BASE_URL` | yes | Render HTTPS URL |
| `DEEPGRAM_API_KEY` | recommended | Own STT key |
| `GROQ_API_KEY` | recommended | Own LLM key |
| `LLM_PROVIDER` | no | `groq` (default) \| `google` \| `vapi-openai` |
| `VAPI_ASSISTANT_ID` / `VAPI_PHONE_NUMBER*` | auto | Written by `scripts/setup_vapi.py` |
| `CLINIC_TIMEZONE` | no | Default `America/New_York` (future DOB checks) |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | no | Optional basic auth |

Copy `.env.example` → `.env`.

## Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill values
make migrate && make seed
make dev               # http://localhost:8000
# For Vapi webhooks locally: put an ngrok HTTPS URL in PUBLIC_BASE_URL, then:
make setup-vapi
make test
```

## Production (Render)

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → select the repo (`render.yaml`).
3. Paste env vars from `.env` (set `PUBLIC_BASE_URL` to the Render URL Render assigns).
4. Wait for `/healthz` to return ok.
5. Locally: update `.env` `PUBLIC_BASE_URL`, run `make setup-vapi` (wires assistant, tools, phone).
6. cron-job.org → create job → URL `https://YOUR-SERVICE.onrender.com/healthz` → every **5 minutes**.

## Data model (high level)

`patients` — PDF demographics + soft delete + CHECK/ENUM constraints + indexes  
`calls` — transcripts, summary, recording URL, outcome  
`appointment_slots` / `appointments` — mock schedule; unique `slot_id` prevents double booking  

Patient rows are written **only after caller confirmation** via `register_patient` / `update_patient`. Mid-call hangs store a `dropped` call row with partial transcript — **no half patient**.

## API

Consistent envelope: `{ "data": ..., "error": null }` / `{ "data": null, "error": { code, message, details } }`.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/patients` | filters: `last_name`, `date_of_birth`, `phone_number`; `limit`/`offset` + `meta.total` |
| GET | `/patients/{id}` | 404 if missing/soft-deleted |
| POST | `/patients` | 201 |
| PUT | `/patients/{id}` | partial update |
| DELETE | `/patients/{id}` | soft delete |
| GET | `/patients/{id}/calls` | bonus |
| GET | `/patients/{id}/appointments` | bonus |
| GET | `/appointments/slots` | bonus |
| POST | `/appointments` | bonus |
| GET | `/healthz` | DB ping |
| POST | `/vapi/tools` | Vapi tool dispatch |
| POST | `/vapi/webhook` | status / end-of-call |

## Prompt engineering

`app/prompts/system_prompt.md` defines Riley: phone-first → duplicate check → required fields in natural groups → exact optional-field offer wording → full readback → confirm → save → endCall. Handles spelling, corrections, start-over, Spanish switch, appointment offer, and honest AI disclosure. Tools return short `speakable` JSON so the model recovers out loud on errors.

## Edge cases & resilience

| Scenario | Behavior |
|----------|----------|
| Invalid DOB / phone / state / ZIP | `validate_fields` → specific re-prompt |
| Connection drops mid-call | webhook marks `dropped`; no patient row without confirm+save |
| DB write fails | tool returns speakable error; agent retries once |
| Tool/server down | Vapi `request-failed` message configured |
| Caller interrupts | Vapi barge-in enabled |
| "Start over" | prompt clears and restarts |
| Returning caller | `check_existing_patient` offers update |

## Observability

Structured JSON logs to stdout (Render logs): request IDs, tool latency, final collected payload, end-of-call summaries. Full transcripts/recordings stored on `calls` when Vapi provides them.

## Known limitations / trade-offs

- Free Vapi numbers are **US inbound only** — non-US reviewers use the dashboard browser call.
- Render free tier sleeps without traffic — mitigated by cron-job.org every 5 minutes.
- Not HIPAA; demo/fake data only.
- Appointment slots are mock clinic data.
- Groq free-tier rate limits; fallback is Vapi-hosted OpenAI (uses Vapi credit).

## Next steps

- Add outbound SMS confirmation
- Stronger auth on mutating API routes
- Multi-clinic / multi-assistant config

## Tests

```bash
make test   # unit + API + voice adapter + appointments against Postgres
```

CI runs lint + tests on every push (Postgres service container).
