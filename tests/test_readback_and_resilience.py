"""Readback + extra resilience / filter tests."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

from app.config import get_settings
from app.voice.readback import patient_readback, speak_date, speak_phone, speak_zip


def test_speak_helpers():
    assert "nineteen ninety" in speak_date(date(1990, 3, 3))
    assert speak_phone("4155550123") == "415-555-0123"
    assert "9" in speak_zip("94105")
    text = patient_readback(
        {
            "first_name": "Jane",
            "last_name": "Doe",
            "date_of_birth": "1990-03-03",
            "sex": "Female",
            "phone_number": "4155550100",
            "address_line_1": "100 Market St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94105",
        }
    )
    assert "Jane Doe" in text
    assert "California" in text
    assert "sound correct" in text


def test_format_readback_tool(client):
    secret = get_settings().vapi_webhook_secret
    r = client.post(
        "/vapi/tools",
        headers={"X-Vapi-Secret": secret},
        json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "tc-rb",
                        "function": {
                            "name": "format_readback",
                            "arguments": {
                                "fields": {
                                    "first_name": "Jane",
                                    "last_name": "Doe",
                                    "date_of_birth": "1990-03-03",
                                    "sex": "Female",
                                    "phone_number": "4155550100",
                                    "address_line_1": "1 Main",
                                    "city": "Austin",
                                    "state": "TX",
                                    "zip_code": "78701",
                                }
                            },
                        },
                    }
                ],
            }
        },
    )
    assert r.status_code == 200
    assert "Jane Doe" in r.json()["results"][0]["result"]["speakable"]


def test_dob_filter_and_soft_delete_hidden(client, sample_patient):
    phone = "512555" + f"{uuid.uuid4().int % 9000 + 1000}"
    payload = {
        **sample_patient,
        "phone_number": phone,
        "date_of_birth": "04/12/1992",
        "email": f"f{uuid.uuid4().hex[:8]}@ex.com",
        "state": "TX",
    }
    r = client.post("/patients", json=payload)
    assert r.status_code == 201
    pid = r.json()["data"]["patient_id"]

    r = client.get("/patients", params={"date_of_birth": "04/12/1992", "phone_number": phone})
    assert r.status_code == 200
    assert r.json()["meta"]["total"] >= 1

    client.delete(f"/patients/{pid}")
    r = client.get("/patients", params={"phone_number": phone})
    assert r.status_code == 200
    assert all(p["patient_id"] != pid for p in r.json()["data"])


def test_returning_caller_tool_flow(client, sample_patient):
    secret = get_settings().vapi_webhook_secret
    phone = "512555" + f"{uuid.uuid4().int % 9000 + 1000}"
    payload = {
        **sample_patient,
        "phone_number": phone,
        "email": f"r{uuid.uuid4().hex[:8]}@ex.com",
        "state": "TX",
        "created_via": "voice",
    }
    assert client.post("/patients", json=payload).status_code == 201

    r = client.post(
        "/vapi/tools",
        headers={"X-Vapi-Secret": secret},
        json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "tc-dup",
                        "function": {
                            "name": "check_existing_patient",
                            "arguments": {"phone_number": phone},
                        },
                    }
                ],
            }
        },
    )
    assert r.status_code == 200
    result = r.json()["results"][0]["result"]
    assert result["found"] is True
    assert "already have a record" in result["speakable"]


def test_register_db_failure_speakable(client, sample_patient):
    secret = get_settings().vapi_webhook_secret
    phone = "512555" + f"{uuid.uuid4().int % 9000 + 1000}"
    payload = {**sample_patient, "phone_number": phone, "state": "TX"}

    with patch("app.voice.tools.PatientService.create", side_effect=RuntimeError("db down")):
        r = client.post(
            "/vapi/tools",
            headers={"X-Vapi-Secret": secret},
            json={
                "message": {
                    "type": "tool-calls",
                    "call": {"id": "call-fail-1"},
                    "toolCallList": [
                        {
                            "id": "tc-fail",
                            "function": {"name": "register_patient", "arguments": payload},
                        }
                    ],
                }
            },
        )
    assert r.status_code == 200
    result = r.json()["results"][0]["result"]
    assert result["ok"] is False
    assert result.get("retryable") is True
    assert "trouble saving" in result["speakable"].lower()


def test_dropped_call_no_patient_requirement(client, db):
    """Hang mid-call stores call row; does not invent a patient."""
    secret = get_settings().vapi_webhook_secret
    call_id = f"dropped-{uuid.uuid4()}"
    r = client.post(
        "/vapi/webhook",
        headers={"X-Vapi-Secret": secret},
        json={
            "message": {
                "type": "end-of-call-report",
                "endedReason": "customer-ended-call",
                "transcript": "Hi I am... (cut off)",
                "call": {
                    "id": call_id,
                    "startedAt": "2026-09-24T12:00:00Z",
                    "endedAt": "2026-09-24T12:01:00Z",
                },
            }
        },
    )
    assert r.status_code == 200
    from app.db.models import Call
    from sqlalchemy import select

    row = db.scalar(select(Call).where(Call.vapi_call_id == call_id))
    assert row is not None
    assert row.patient_id is None
    assert row.transcript is not None
