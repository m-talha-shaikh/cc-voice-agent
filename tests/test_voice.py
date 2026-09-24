"""Vapi adapter tests."""

from __future__ import annotations

import uuid

from app.config import get_settings


def test_tools_unauthorized(client):
    r = client.post("/vapi/tools", json={"message": {"type": "tool-calls", "toolCallList": []}})
    assert r.status_code == 401


def test_check_existing_and_register(client, sample_patient):
    secret = get_settings().vapi_webhook_secret
    headers = {"X-Vapi-Secret": secret}
    phone = "512555" + f"{uuid.uuid4().int % 9000 + 1000}"

    # not found
    r = client.post(
        "/vapi/tools",
        headers=headers,
        json={
            "message": {
                "type": "tool-calls",
                "call": {"id": "call-test-1"},
                "toolCallList": [
                    {
                        "id": "tc1",
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
    assert result["found"] is False

    payload = {
        **sample_patient,
        "phone_number": phone,
        "email": f"v{uuid.uuid4().hex[:8]}@ex.com",
        "state": "TX",
    }
    r = client.post(
        "/vapi/tools",
        headers=headers,
        json={
            "message": {
                "type": "tool-calls",
                "call": {"id": "call-test-1"},
                "toolCallList": [
                    {
                        "id": "tc2",
                        "function": {"name": "register_patient", "arguments": payload},
                    }
                ],
            }
        },
    )
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]["result"]
    assert result["ok"] is True
    assert "patient_id" in result

    # end of call report
    r = client.post(
        "/vapi/webhook",
        headers=headers,
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call-test-1", "startedAt": "2026-09-24T10:00:00Z", "endedAt": "2026-09-24T10:05:00Z"},
                "transcript": "Hello world",
                "summary": "Registered patient",
                "endedReason": "assistant-ended-call",
            }
        },
    )
    assert r.status_code == 200


def test_validate_fields_tool(client):
    secret = get_settings().vapi_webhook_secret
    r = client.post(
        "/vapi/tools",
        headers={"X-Vapi-Secret": secret},
        json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "tc3",
                        "function": {
                            "name": "validate_fields",
                            "arguments": {"fields": {"phone_number": "123", "zip_code": "94105"}},
                        },
                    }
                ],
            }
        },
    )
    assert r.status_code == 200
    result = r.json()["results"][0]["result"]
    assert result["valid"] is False
