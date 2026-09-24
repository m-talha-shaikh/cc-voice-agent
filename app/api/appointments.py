"""Appointment REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.appointment import AppointmentCreate
from app.schemas.common import err, ok
from app.services.appointment import AppointmentService

router = APIRouter(tags=["appointments"])


@router.get("/appointments/slots")
def list_slots(
    preferred_day: str | None = None,
    time_of_day: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    slots = AppointmentService(db).list_available(
        preferred_day=preferred_day, time_of_day=time_of_day, limit=limit
    )
    return ok(
        [
            {
                "id": str(s.id),
                "starts_at": s.starts_at.isoformat(),
                "ends_at": s.ends_at.isoformat(),
                "provider_name": s.provider_name,
                "is_available": s.is_available,
            }
            for s in slots
        ]
    )


@router.post("/appointments", status_code=201)
def book_appointment(body: dict, db: Session = Depends(get_db)):
    try:
        payload = AppointmentCreate.model_validate(body)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=err("validation_error", "Validation failed", details),
        )
    appt, error = AppointmentService(db).book(
        patient_id=payload.patient_id,
        slot_id=payload.slot_id,
        reason=payload.reason,
    )
    if error:
        code = 404 if "not found" in error else 409
        return JSONResponse(status_code=code, content=err("booking_error", error))
    return JSONResponse(
        status_code=201,
        content=ok(
            {
                "id": str(appt.id),
                "patient_id": str(appt.patient_id),
                "slot_id": str(appt.slot_id),
                "reason": appt.reason,
                "status": appt.status.value,
                "created_at": appt.created_at.isoformat(),
            }
        ),
    )
