"""REST API for patients."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.openapi_examples import ENVELOPE_404, ENVELOPE_422, ENVELOPE_LIST, ENVELOPE_OK
from app.db.session import get_db
from app.schemas.common import Meta, err, ok
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services.call import CallService
from app.services.patient import PatientService

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get(
    "",
    responses={200: ENVELOPE_LIST, 400: ENVELOPE_422},
    summary="List patients",
    description=(
        "List active (non-deleted) patients. Filters are ANDed. "
        "Phone numbers accepted in any common U.S. format."
    ),
)
def list_patients(
    last_name: Optional[str] = Query(default=None, description="Case-insensitive exact match"),
    date_of_birth: Optional[str] = Query(default=None, description="MM/DD/YYYY or ISO"),
    phone_number: Optional[str] = Query(default=None, description="Any U.S. phone format"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        rows, total = PatientService(db).list(
            last_name=last_name,
            date_of_birth=date_of_birth,
            phone_number=phone_number,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=err("bad_request", str(exc), [{"field": None, "message": str(exc)}]),
        )
    return ok(
        [PatientService.to_out(p) for p in rows],
        meta=Meta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/{patient_id}",
    responses={200: ENVELOPE_OK, 404: ENVELOPE_404, 422: ENVELOPE_422},
    summary="Get patient by UUID",
)
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content=err(
                "validation_error",
                "Invalid patient_id UUID",
                [{"field": "patient_id", "message": "must be a valid UUID"}],
            ),
        )
    patient = PatientService(db).get(pid)
    if not patient:
        return JSONResponse(status_code=404, content=err("not_found", "Patient not found"))
    return ok(PatientService.to_out(patient))


@router.post(
    "",
    status_code=201,
    responses={201: ENVELOPE_OK, 422: ENVELOPE_422},
    summary="Create patient",
)
def create_patient(body: dict, db: Session = Depends(get_db)):
    try:
        payload = PatientCreate.model_validate(body)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=err("validation_error", "Validation failed", details),
        )
    patient = PatientService(db).create(payload)
    return JSONResponse(status_code=201, content=ok(PatientService.to_out(patient)))


@router.put(
    "/{patient_id}",
    responses={200: ENVELOPE_OK, 404: ENVELOPE_404, 422: ENVELOPE_422},
    summary="Partial update patient",
)
def update_patient(patient_id: str, body: dict, db: Session = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content=err(
                "validation_error",
                "Invalid patient_id UUID",
                [{"field": "patient_id", "message": "must be a valid UUID"}],
            ),
        )
    for forbidden in ("patient_id", "created_at", "deleted_at"):
        body.pop(forbidden, None)
    try:
        payload = PatientUpdate.model_validate(body)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=err("validation_error", "Validation failed", details),
        )
    patient = PatientService(db).update(pid, payload)
    if not patient:
        return JSONResponse(status_code=404, content=err("not_found", "Patient not found"))
    return ok(PatientService.to_out(patient))


@router.delete(
    "/{patient_id}",
    responses={200: ENVELOPE_OK, 404: ENVELOPE_404},
    summary="Soft-delete patient",
)
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content=err(
                "validation_error",
                "Invalid patient_id UUID",
                [{"field": "patient_id", "message": "must be a valid UUID"}],
            ),
        )
    patient = PatientService(db).soft_delete(pid)
    if not patient:
        return JSONResponse(status_code=404, content=err("not_found", "Patient not found"))
    return ok(PatientService.to_out(patient))


@router.get("/{patient_id}/calls", summary="Call history for patient (bonus)")
def patient_calls(patient_id: str, db: Session = Depends(get_db)):
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content=err("validation_error", "Invalid patient_id UUID"),
        )
    if not PatientService(db).get(pid):
        return JSONResponse(status_code=404, content=err("not_found", "Patient not found"))
    calls = CallService(db).list_for_patient(pid)
    data = [
        {
            "id": str(c.id),
            "vapi_call_id": c.vapi_call_id,
            "status": c.status.value if c.status else None,
            "outcome": c.outcome.value if c.outcome else None,
            "duration_s": c.duration_s,
            "transcript": c.transcript,
            "summary": c.summary,
            "recording_url": c.recording_url,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        }
        for c in calls
    ]
    return ok(data)


@router.get("/{patient_id}/appointments", summary="Appointments for patient (bonus)")
def patient_appointments(patient_id: str, db: Session = Depends(get_db)):
    from app.services.appointment import AppointmentService

    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content=err("validation_error", "Invalid patient_id UUID"),
        )
    if not PatientService(db).get(pid):
        return JSONResponse(status_code=404, content=err("not_found", "Patient not found"))
    appts = AppointmentService(db).list_for_patient(pid)
    data = []
    for a in appts:
        item = {
            "id": str(a.id),
            "patient_id": str(a.patient_id),
            "slot_id": str(a.slot_id),
            "reason": a.reason,
            "status": a.status.value,
            "created_at": a.created_at.isoformat(),
        }
        if a.slot:
            item["slot"] = {
                "id": str(a.slot.id),
                "starts_at": a.slot.starts_at.isoformat(),
                "ends_at": a.slot.ends_at.isoformat(),
                "provider_name": a.slot.provider_name,
            }
        data.append(item)
    return ok(data)
