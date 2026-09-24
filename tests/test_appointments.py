"""Appointment booking tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.db.models import AppointmentSlot


def test_book_and_double_book(client, db, sample_patient):
    phone = "512555" + f"{uuid.uuid4().int % 9000 + 1000}"
    payload = {**sample_patient, "phone_number": phone, "email": f"a{uuid.uuid4().hex[:8]}@ex.com", "state": "TX"}
    r = client.post("/patients", json=payload)
    assert r.status_code == 201
    pid = r.json()["data"]["patient_id"]

    starts = datetime.now(timezone.utc) + timedelta(days=3)
    slot = AppointmentSlot(
        starts_at=starts,
        ends_at=starts + timedelta(minutes=30),
        provider_name="Dr. Patel",
        is_available=True,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)

    r = client.post(
        "/appointments",
        json={"patient_id": pid, "slot_id": str(slot.id), "reason": "new patient"},
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/appointments",
        json={"patient_id": pid, "slot_id": str(slot.id), "reason": "again"},
    )
    assert r.status_code == 409
