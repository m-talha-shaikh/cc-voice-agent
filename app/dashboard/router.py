"""Server-rendered dashboard."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.services.appointment import AppointmentService
from app.services.call import CallService
from app.services.patient import PatientService

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
security = HTTPBasic(auto_error=False)


def maybe_auth(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    settings = get_settings()
    if not settings.dashboard_user or not settings.dashboard_password:
        return
    if credentials is None:
        raise_auth()
    ok_user = secrets.compare_digest(credentials.username, settings.dashboard_user)
    ok_pass = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (ok_user and ok_pass):
        raise_auth()


def raise_auth() -> None:
    from fastapi import HTTPException

    raise HTTPException(
        status_code=401,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Basic"},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(maybe_auth),
):
    settings = get_settings()
    svc = PatientService(db)
    patients, total = svc.list(limit=100, offset=0)
    if q:
        ql = q.strip().lower()
        patients = [
            p
            for p in patients
            if ql in p.first_name.lower()
            or ql in p.last_name.lower()
            or ql in p.phone_number
            or ql in p.date_of_birth.isoformat()
        ]
    calls = CallService(db).list_recent(40)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "patients": patients,
            "calls": calls,
            "total": total,
            "q": q or "",
            "phone": settings.vapi_phone_number or "Not provisioned",
            "api_base": settings.public_base_url.rstrip("/"),
            "vapi_public_key": settings.vapi_public_key,
            "assistant_id": settings.vapi_assistant_id or "",
        },
    )


@router.get("/dashboard/patients/{patient_id}", response_class=HTMLResponse)
def patient_detail(
    patient_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(maybe_auth),
):
    import uuid

    settings = get_settings()
    try:
        pid = uuid.UUID(patient_id)
    except ValueError:
        return Response("Invalid id", status_code=422)
    patient = PatientService(db).get(pid)
    if not patient:
        return Response("Not found", status_code=404)
    calls = CallService(db).list_for_patient(pid)
    appts = AppointmentService(db).list_for_patient(pid)
    return templates.TemplateResponse(
        request,
        "patient.html",
        {
            "patient": patient,
            "calls": calls,
            "appointments": appts,
            "phone": settings.vapi_phone_number,
            "api_base": settings.public_base_url.rstrip("/"),
        },
    )
