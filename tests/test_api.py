"""API integration tests."""

from __future__ import annotations

import uuid


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert body["data"]["database"] == "up"


def test_create_list_get_update_delete(client, sample_patient):
    # unique phone each run
    phone = f"512555{str(uuid.uuid4().int)[-4:]}"
    # ensure NANP: exchange can't start 0/1 — use 555x
    phone = "512555" + f"{uuid.uuid4().int % 9000 + 1000}"
    payload = {**sample_patient, "phone_number": phone, "email": f"t{uuid.uuid4().hex[:8]}@ex.com"}

    r = client.post("/patients", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()["data"]
    pid = created["patient_id"]
    assert created["phone_number"] == phone
    assert created["state"] == "TX"
    assert created["first_name"] == "Alice"

    r = client.get(f"/patients/{pid}")
    assert r.status_code == 200
    assert r.json()["data"]["last_name"] == "Johnson"

    r = client.get("/patients", params={"last_name": "Johnson", "phone_number": phone})
    assert r.status_code == 200
    assert r.json()["meta"]["total"] >= 1

    r = client.put(f"/patients/{pid}", json={"last_name": "Davis"})
    assert r.status_code == 200
    assert r.json()["data"]["last_name"] == "Davis"

    r = client.delete(f"/patients/{pid}")
    assert r.status_code == 200
    assert r.json()["data"]["deleted_at"] is not None

    r = client.get(f"/patients/{pid}")
    assert r.status_code == 404


def test_validation_error_envelope(client):
    r = client.post(
        "/patients",
        json={
            "first_name": "A",
            "last_name": "B",
            "date_of_birth": "01/01/2099",
            "sex": "Female",
            "phone_number": "123",
            "address_line_1": "1 St",
            "city": "X",
            "state": "CA",
            "zip_code": "94105",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["data"] is None
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]


def test_invalid_uuid(client):
    r = client.get("/patients/not-a-uuid")
    assert r.status_code == 422


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "dashboard" in r.json()["data"]["links"]
