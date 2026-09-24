#!/usr/bin/env python3
"""Idempotent seed: demo patients + rolling appointment slots (next 14 business days)."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import AppointmentSlot, Patient, SexEnum  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def seed_patients(db) -> None:
    demos = [
        {
            "first_name": "Jane",
            "last_name": "Doe",
            "date_of_birth": date(1990, 3, 3),
            "sex": SexEnum.female,
            "phone_number": "4155550100",
            "email": "jane.doe@example.com",
            "address_line_1": "100 Market St",
            "address_line_2": "Apt 4B",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94105",
            "preferred_language": "English",
            "created_via": "api",
        },
        {
            "first_name": "John",
            "last_name": "Smith",
            "date_of_birth": date(1985, 7, 15),
            "sex": SexEnum.male,
            "phone_number": "6465550199",
            "email": "john.smith@example.com",
            "address_line_1": "200 Broadway",
            "city": "New York",
            "state": "NY",
            "zip_code": "10007",
            "preferred_language": "English",
            "created_via": "api",
        },
    ]
    for row in demos:
        exists = db.scalar(
            select(Patient).where(
                Patient.phone_number == row["phone_number"],
                Patient.deleted_at.is_(None),
            )
        )
        if exists:
            print(f"skip patient {row['first_name']} {row['last_name']}")
            continue
        db.add(Patient(**row))
        print(f"seeded patient {row['first_name']} {row['last_name']}")
    db.commit()


def seed_slots(db) -> None:
    tz = ZoneInfo(get_settings().clinic_timezone)
    today = datetime.now(tz).date()
    hours = [9, 11, 14, 16]
    created = 0
    day = today
    business_days = 0
    while business_days < 14:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        business_days += 1
        for hour in hours:
            starts = datetime.combine(day, time(hour, 0), tzinfo=tz)
            ends = starts + timedelta(minutes=30)
            exists = db.scalar(
                select(AppointmentSlot).where(AppointmentSlot.starts_at == starts)
            )
            if exists:
                continue
            db.add(
                AppointmentSlot(
                    starts_at=starts.astimezone(timezone.utc),
                    ends_at=ends.astimezone(timezone.utc),
                    provider_name="Dr. Patel",
                    is_available=True,
                )
            )
            created += 1
    db.commit()
    print(f"seeded {created} appointment slots")


def main() -> None:
    db = SessionLocal()
    try:
        seed_patients(db)
        seed_slots(db)
        print("seed complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()
