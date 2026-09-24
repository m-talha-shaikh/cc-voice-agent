"""Appointment scheduling — mock provider slots."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db.models import Appointment, AppointmentSlot, AppointmentStatus, Patient


class AppointmentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_available(
        self,
        *,
        preferred_day: str | None = None,
        time_of_day: str | None = None,
        limit: int = 3,
    ) -> list[AppointmentSlot]:
        now = datetime.now(timezone.utc)
        q = (
            select(AppointmentSlot)
            .where(
                AppointmentSlot.is_available.is_(True),
                AppointmentSlot.starts_at >= now,
            )
            .order_by(AppointmentSlot.starts_at)
        )
        slots = list(self.db.scalars(q).all())

        tz = ZoneInfo(get_settings().clinic_timezone)
        if preferred_day:
            day = preferred_day.strip().lower()
            weekday_map = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
                "today": datetime.now(tz).weekday(),
                "tomorrow": (datetime.now(tz) + timedelta(days=1)).weekday(),
            }
            if day in weekday_map:
                target = weekday_map[day]
                slots = [s for s in slots if s.starts_at.astimezone(tz).weekday() == target]

        if time_of_day:
            tod = time_of_day.strip().lower()
            filtered = []
            for s in slots:
                hour = s.starts_at.astimezone(tz).hour
                if tod in ("morning", "am") and hour < 12:
                    filtered.append(s)
                elif tod in ("afternoon", "pm") and 12 <= hour < 17:
                    filtered.append(s)
                elif tod == "evening" and hour >= 17:
                    filtered.append(s)
            if filtered:
                slots = filtered

        return slots[:limit]

    def book(
        self,
        *,
        patient_id: uuid.UUID,
        slot_id: uuid.UUID,
        reason: str | None = None,
    ) -> tuple[Optional[Appointment], Optional[str]]:
        patient = self.db.get(Patient, patient_id)
        if not patient or patient.deleted_at is not None:
            return None, "patient not found"

        slot = self.db.get(AppointmentSlot, slot_id)
        if not slot:
            return None, "slot not found"
        if not slot.is_available:
            return None, "that slot is no longer available"

        existing = self.db.scalar(
            select(Appointment).where(Appointment.slot_id == slot_id)
        )
        if existing:
            return None, "that slot was just booked by someone else"

        appt = Appointment(
            patient_id=patient_id,
            slot_id=slot_id,
            reason=reason,
            status=AppointmentStatus.scheduled,
        )
        slot.is_available = False
        self.db.add(appt)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return None, "that slot was just booked by someone else"
        self.db.refresh(appt)
        return appt, None
    def list_for_patient(self, patient_id: uuid.UUID) -> list[Appointment]:
        return list(
            self.db.scalars(
                select(Appointment)
                .options(joinedload(Appointment.slot))
                .where(Appointment.patient_id == patient_id)
                .order_by(Appointment.created_at.desc())
            ).unique()
        )
