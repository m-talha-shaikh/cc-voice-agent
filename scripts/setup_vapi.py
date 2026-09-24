#!/usr/bin/env python3
"""Idempotent Vapi setup: credentials, tools, assistant, phone assignment."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402

API = "https://api.vapi.ai"
PROMPT_PATH = ROOT / "app" / "prompts" / "system_prompt.md"


def client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=API,
        headers={
            "Authorization": f"Bearer {s.vapi_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "carecloud-voice-setup/1.0",
        },
        timeout=60.0,
    )


def upsert_env(updates: dict[str, str]) -> None:
    env_path = ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    keys_seen = set()
    out = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                keys_seen.add(k)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in keys_seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n")


def register_credentials(c: httpx.Client) -> None:
    s = get_settings()
    # Best-effort: Vapi credential endpoints vary; also document dashboard fallback
    payloads = []
    if s.deepgram_api_key:
        payloads.append({"provider": "deepgram", "apiKey": s.deepgram_api_key})
    if s.groq_api_key:
        payloads.append({"provider": "groq", "apiKey": s.groq_api_key})
    if s.google_api_key:
        payloads.append({"provider": "google", "apiKey": s.google_api_key})
    for p in payloads:
        r = c.post("/credential", json=p)
        if r.status_code in (200, 201):
            print(f"credential {p['provider']}: ok")
        else:
            # try list/update path
            print(f"credential {p['provider']}: {r.status_code} {r.text[:120]} (continuing)")


def tool_defs(server_url: str, secret: str) -> list[dict]:
    server = {
        "url": server_url,
        "secret": secret,
        "timeoutSeconds": 20,
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "check_existing_patient",
                "description": "Look up an existing patient by U.S. phone number for duplicate detection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "10-digit U.S. phone number",
                        }
                    },
                    "required": ["phone_number"],
                },
            },
            "server": server,
            "async": False,
        },
        {
            "type": "function",
            "function": {
                "name": "validate_fields",
                "description": "Validate one or more demographic fields immediately (DOB, phone, state, ZIP, email, names, sex).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "object",
                            "description": "Map of field name to raw spoken value",
                        }
                    },
                    "required": ["fields"],
                },
            },
            "server": server,
            "async": False,
        },
        {
            "type": "function",
            "function": {
                "name": "register_patient",
                "description": "Create a patient AFTER the caller confirms the full readback. Required: first_name, last_name, date_of_birth, sex, phone_number, address_line_1, city, state, zip_code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "date_of_birth": {"type": "string", "description": "MM/DD/YYYY or ISO"},
                        "sex": {"type": "string"},
                        "phone_number": {"type": "string"},
                        "email": {"type": "string"},
                        "address_line_1": {"type": "string"},
                        "address_line_2": {"type": "string"},
                        "city": {"type": "string"},
                        "state": {"type": "string"},
                        "zip_code": {"type": "string"},
                        "insurance_provider": {"type": "string"},
                        "insurance_member_id": {"type": "string"},
                        "preferred_language": {"type": "string"},
                        "emergency_contact_name": {"type": "string"},
                        "emergency_contact_phone": {"type": "string"},
                    },
                    "required": [
                        "first_name",
                        "last_name",
                        "date_of_birth",
                        "sex",
                        "phone_number",
                        "address_line_1",
                        "city",
                        "state",
                        "zip_code",
                    ],
                },
            },
            "server": server,
            "async": False,
            "messages": [
                {
                    "type": "request-start",
                    "content": "One moment while I save your information.",
                },
                {
                    "type": "request-failed",
                    "content": "I'm having a little trouble saving that. Let me try again.",
                },
            ],
        },
        {
            "type": "function",
            "function": {
                "name": "update_patient",
                "description": "Update an existing patient after confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string"},
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "date_of_birth": {"type": "string"},
                        "sex": {"type": "string"},
                        "phone_number": {"type": "string"},
                        "email": {"type": "string"},
                        "address_line_1": {"type": "string"},
                        "address_line_2": {"type": "string"},
                        "city": {"type": "string"},
                        "state": {"type": "string"},
                        "zip_code": {"type": "string"},
                        "insurance_provider": {"type": "string"},
                        "insurance_member_id": {"type": "string"},
                        "preferred_language": {"type": "string"},
                        "emergency_contact_name": {"type": "string"},
                        "emergency_contact_phone": {"type": "string"},
                    },
                    "required": ["patient_id"],
                },
            },
            "server": server,
            "async": False,
        },
        {
            "type": "function",
            "function": {
                "name": "format_readback",
                "description": "Build a natural spoken confirmation of collected fields before saving.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "object",
                            "description": "Collected demographic fields",
                        }
                    },
                    "required": ["fields"],
                },
            },
            "server": server,
            "async": False,
        },
        {
            "type": "function",
            "function": {
                "name": "get_available_slots",
                "description": "Return up to 3 available first-appointment slots.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "preferred_day": {"type": "string"},
                        "time_of_day": {"type": "string", "description": "morning, afternoon, or evening"},
                    },
                },
            },
            "server": server,
            "async": False,
        },
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Book a slot for a patient.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string"},
                        "slot_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["patient_id", "slot_id"],
                },
            },
            "server": server,
            "async": False,
        },
    ]


def build_assistant_payload(s) -> dict:
    now = datetime.now(ZoneInfo(s.clinic_timezone)).strftime("%A, %B %d, %Y")
    prompt = PROMPT_PATH.read_text().replace("{{now}}", now)
    base = s.public_base_url.rstrip("/")
    tools_url = f"{base}/vapi/tools"
    webhook_url = f"{base}/vapi/webhook"
    tools = tool_defs(tools_url, s.vapi_webhook_secret)

    if s.llm_provider == "groq" and s.groq_api_key:
        model = {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": prompt}],
            "tools": tools,
            "temperature": 0.4,
        }
    elif s.llm_provider == "google" and s.google_api_key:
        model = {
            "provider": "google",
            "model": "gemini-2.0-flash",
            "messages": [{"role": "system", "content": prompt}],
            "tools": tools,
            "temperature": 0.4,
        }
    else:
        model = {
            "provider": "openai",
            "model": "gpt-4.1",
            "messages": [{"role": "system", "content": prompt}],
            "tools": tools,
            "temperature": 0.4,
        }

    transcriber: dict = {
        "provider": "deepgram",
        "model": "nova-3",
        "language": "multi",
        "keyterm": [
            "CareCloud",
            "date of birth",
            "ZIP code",
            "insurance",
            "O'Brien",
            "McDonald",
        ],
    }
    if s.deepgram_api_key:
        # Vapi uses org credentials when registered; key can also be omitted
        pass

    return {
        "name": "Riley",
        "model": model,
        "voice": {
            "provider": "vapi",
            "voiceId": "Elliot",
        },
        "transcriber": transcriber,
        "firstMessage": (
            "Hi, thanks for calling CareCloud Clinic. This is Riley, an AI intake coordinator. "
            "I can help you register as a new patient. Could I start with your ten-digit phone number?"
        ),
        "silenceTimeoutSeconds": 45,
        "maxDurationSeconds": 900,
        "backgroundSound": "off",
        "serverUrl": webhook_url,
        "serverUrlSecret": s.vapi_webhook_secret,
        "endCallFunctionEnabled": True,
        "recordingEnabled": True,
        "hipaaEnabled": False,
        "clientMessages": [],
        "serverMessages": [
            "status-update",
            "end-of-call-report",
            "hang",
        ],
    }


def main() -> None:
    s = get_settings()
    if "onrender.com" in s.public_base_url and "your-" in s.public_base_url:
        print("WARNING: PUBLIC_BASE_URL looks like a placeholder. Update it before live calls.")

    with client() as c:
        register_credentials(c)
        payload = build_assistant_payload(s)

        assistant_id = s.vapi_assistant_id
        if assistant_id:
            r = c.patch(f"/assistant/{assistant_id}", json=payload)
            if r.status_code >= 400:
                print("patch assistant failed, creating new:", r.status_code, r.text[:300])
                r = c.post("/assistant", json=payload)
                r.raise_for_status()
                assistant_id = r.json()["id"]
            else:
                assistant_id = r.json().get("id", assistant_id)
                print("updated assistant", assistant_id)
        else:
            r = c.post("/assistant", json=payload)
            r.raise_for_status()
            assistant_id = r.json()["id"]
            print("created assistant", assistant_id)

        phone_id = s.vapi_phone_number_id
        phone_number = s.vapi_phone_number
        if not phone_id:
            phones = c.get("/phone-number").json()
            if phones:
                phone_id = phones[0]["id"]
                phone_number = phones[0].get("number")
            else:
                r = c.post(
                    "/phone-number",
                    json={"provider": "vapi", "numberDesiredAreaCode": "415"},
                )
                if r.status_code >= 400:
                    print("phone create failed:", r.status_code, r.text[:300])
                else:
                    phone_id = r.json()["id"]
                    phone_number = r.json().get("number")

        if phone_id:
            r = c.patch(
                f"/phone-number/{phone_id}",
                json={"assistantId": assistant_id},
            )
            print("assign phone:", r.status_code, phone_number)
            if r.status_code >= 400:
                print(r.text[:300])

        upsert_env(
            {
                "VAPI_ASSISTANT_ID": assistant_id or "",
                "VAPI_PHONE_NUMBER_ID": phone_id or "",
                "VAPI_PHONE_NUMBER": phone_number or "",
            }
        )
        print(json.dumps({
            "VAPI_ASSISTANT_ID": assistant_id,
            "VAPI_PHONE_NUMBER_ID": phone_id,
            "VAPI_PHONE_NUMBER": phone_number,
            "tools_url": f"{s.public_base_url.rstrip('/')}/vapi/tools",
            "webhook_url": f"{s.public_base_url.rstrip('/')}/vapi/webhook",
        }, indent=2))


if __name__ == "__main__":
    main()
