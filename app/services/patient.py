"""Patient business logic — shared by REST and voice tools."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Patient
from app.schemas.patient import (
    PatientCreate,
    PatientOut,
    PatientUpdate,
    normalize_dob,
    normalize_phone,
    normalize_sex,
    normalize_state,
    normalize_zip,
    normalize_name,
)


class PatientService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _active(self):
        return select(Patient).where(Patient.deleted_at.is_(None))

    def get(self, patient_id: uuid.UUID) -> Optional[Patient]:
        return self.db.scalar(self._active().where(Patient.patient_id == patient_id))

    def find_by_phone(self, phone: str) -> Optional[Patient]:
        digits = normalize_phone(phone)
        return self.db.scalar(self._active().where(Patient.phone_number == digits))

    def list(
        self,
        *,
        last_name: str | None = None,
        date_of_birth: date | str | None = None,
        phone_number: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Patient], int]:
        q = self._active()
        if last_name:
            q = q.where(func.lower(Patient.last_name) == last_name.strip().lower())
        if date_of_birth is not None:
            dob = normalize_dob(date_of_birth) if not isinstance(date_of_birth, date) else date_of_birth
            q = q.where(Patient.date_of_birth == dob)
        if phone_number:
            q = q.where(Patient.phone_number == normalize_phone(phone_number))
        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = list(
            self.db.scalars(q.order_by(Patient.created_at.desc()).limit(limit).offset(offset))
        )
        return rows, total

    def create(self, payload: PatientCreate) -> Patient:
        data = payload.model_dump()
        sex = data.pop("sex")
        patient = Patient(**data, sex=sex)
        self.db.add(patient)
        self.db.commit()
        self.db.refresh(patient)
        return patient

    def update(self, patient_id: uuid.UUID, payload: PatientUpdate) -> Optional[Patient]:
        patient = self.get(patient_id)
        if not patient:
            return None
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(patient, key, value)
        patient.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(patient)
        return patient

    def soft_delete(self, patient_id: uuid.UUID) -> Optional[Patient]:
        patient = self.get(patient_id)
        if not patient:
            return None
        patient.deleted_at = datetime.now(timezone.utc)
        patient.updated_at = patient.deleted_at
        self.db.commit()
        self.db.refresh(patient)
        return patient

    def validate_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Validate a subset of fields for the voice agent. Returns speakable result."""
        validators = {
            "first_name": lambda v: normalize_name(v, "first_name"),
            "last_name": lambda v: normalize_name(v, "last_name"),
            "date_of_birth": normalize_dob,
            "sex": normalize_sex,
            "phone_number": normalize_phone,
            "state": normalize_state,
            "zip_code": normalize_zip,
            "email": lambda v: PatientCreate.model_validate(
                {
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "date_of_birth": "01/01/1990",
                    "sex": "Female",
                    "phone_number": "4155550123",
                    "address_line_1": "1 Main St",
                    "city": "SF",
                    "state": "CA",
                    "zip_code": "94105",
                    "email": v,
                }
            ).email,
            "emergency_contact_phone": normalize_phone,
        }
        ok: dict[str, Any] = {}
        errors: list[dict[str, str]] = []
        for key, value in fields.items():
            if key not in validators:
                errors.append({"field": key, "message": f"{key}: unknown field"})
                continue
            try:
                normalized = validators[key](value)
                if hasattr(normalized, "value"):
                    ok[key] = normalized.value
                elif isinstance(normalized, date):
                    ok[key] = normalized.isoformat()
                else:
                    ok[key] = normalized
            except (ValueError, ValidationError) as exc:
                msg = str(exc)
                if isinstance(exc, ValidationError):
                    msg = "; ".join(e["msg"] for e in exc.errors())
                errors.append({"field": key, "message": msg})
        return {"valid": len(errors) == 0, "normalized": ok, "errors": errors}

    @staticmethod
    def to_out(patient: Patient) -> dict[str, Any]:
        return PatientOut.model_validate(patient).model_dump(mode="json")
