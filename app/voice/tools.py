"""Vapi tool-call handlers — speakable JSON results, never HTTP 500 to the agent."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models import CallOutcome
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services.appointment import AppointmentService
from app.services.call import CallService
from app.services.patient import PatientService
from app.voice.readback import patient_readback, speak_slot

log = logging.getLogger(__name__)


def mask_phone(phone: str | None) -> str:
    if not phone or len(phone) < 4:
        return "***"
    return f"***-***-{phone[-4:]}"


def dispatch_tool(
    db: Session,
    name: str,
    args: dict[str, Any],
    *,
    call_id: str | None = None,
) -> Any:
    started = time.perf_counter()
    outcome = "unknown"
    try:
        result = _run(db, name, args, call_id=call_id)
        outcome = "ok" if (isinstance(result, dict) and result.get("ok", True) is not False) or (
            isinstance(result, dict) and result.get("valid", True) is not False and "ok" not in result
        ) else "rejected"
        if isinstance(result, dict) and result.get("found") is False and name == "check_existing_patient":
            outcome = "ok"
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception("tool_error name=%s", name)
        outcome = "error"
        return {
            "ok": False,
            "speakable": (
                "I'm having trouble with that right now. "
                "Let me try again in a moment, or we can continue shortly."
            ),
            "error": str(exc)[:200],
        }
    finally:
        latency = int((time.perf_counter() - started) * 1000)
        log.info(
            "tool_call name=%s phone=%s",
            name,
            mask_phone(str(args.get("phone_number", ""))),
            extra={
                "tool": name,
                "call_id": call_id,
                "latency_ms": latency,
                "outcome": outcome,
            },
        )


def _run(db: Session, name: str, args: dict[str, Any], *, call_id: str | None) -> Any:
    patients = PatientService(db)
    appointments = AppointmentService(db)
    calls = CallService(db)

    if name == "check_existing_patient":
        phone = args.get("phone_number")
        if not phone:
            return {"found": False, "speakable": "I need a phone number to look that up."}
        try:
            patient = patients.find_by_phone(phone)
        except ValueError as exc:
            return {"found": False, "speakable": str(exc), "error": str(exc)}
        if not patient:
            return {
                "found": False,
                "speakable": "I don't see an existing record for that number.",
            }
        return {
            "found": True,
            "patient_id": str(patient.patient_id),
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "speakable": (
                f"It looks like we already have a record for {patient.first_name} "
                f"{patient.last_name}. Would you like to update your information instead?"
            ),
        }

    if name == "validate_fields":
        fields = args.get("fields") or args
        # If nested under fields key use that; else treat args as fields (minus meta)
        if "fields" in args and isinstance(args["fields"], dict):
            fields = args["fields"]
        else:
            fields = {k: v for k, v in args.items() if k != "fields"}
        result = patients.validate_fields(fields)
        if result["valid"]:
            result["speakable"] = "That checks out."
        else:
            msgs = "; ".join(e["message"] for e in result["errors"])
            result["speakable"] = f"I need a quick correction: {msgs}"
        return result

    if name == "register_patient":
        data = dict(args)
        data["created_via"] = "voice"
        try:
            payload = PatientCreate.model_validate(data)
        except ValidationError as exc:
            details = [
                {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ]
            speak = "; ".join(d["message"] for d in details[:3])
            return {
                "ok": False,
                "errors": details,
                "speakable": f"I couldn't save yet — {speak}",
            }
        try:
            patient = patients.create(payload)
        except Exception as exc:  # noqa: BLE001
            log.exception("register_patient db failure")
            return {
                "ok": False,
                "retryable": True,
                "speakable": (
                    "I'm having trouble saving your information right now. "
                    "Please hold on while I try once more."
                ),
                "error": str(exc)[:200],
            }
        if call_id:
            calls.link_patient(
                call_id,
                patient.patient_id,
                CallOutcome.registered,
                collected=PatientService.to_out(patient),
            )
        log.info(
            "patient_registered patient_id=%s",
            patient.patient_id,
            extra={"call_id": call_id},
        )
        return {
            "ok": True,
            "patient_id": str(patient.patient_id),
            "first_name": patient.first_name,
            "speakable": f"You're all set, {patient.first_name}.",
        }

    if name == "update_patient":
        pid = args.get("patient_id")
        fields = {k: v for k, v in args.items() if k != "patient_id"}
        try:
            patient_uuid = uuid.UUID(str(pid))
        except (ValueError, TypeError):
            return {"ok": False, "speakable": "I don't have a valid patient id to update."}
        try:
            payload = PatientUpdate.model_validate(fields)
        except ValidationError as exc:
            details = [
                {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ]
            return {
                "ok": False,
                "errors": details,
                "speakable": "; ".join(d["message"] for d in details[:3]),
            }
        try:
            patient = patients.update(patient_uuid, payload)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "retryable": True,
                "speakable": (
                    "I'm having trouble saving your information right now. "
                    "Please hold on while I try once more."
                ),
                "error": str(exc)[:200],
            }
        if not patient:
            return {"ok": False, "speakable": "I couldn't find that patient record."}
        if call_id:
            calls.link_patient(
                call_id,
                patient.patient_id,
                CallOutcome.updated,
                collected=PatientService.to_out(patient),
            )
        return {
            "ok": True,
            "patient_id": str(patient.patient_id),
            "speakable": f"I've updated your information, {patient.first_name}.",
        }

    if name == "format_readback":
        fields = args.get("fields") or args
        if "fields" in args and isinstance(args["fields"], dict):
            fields = args["fields"]
        speakable = patient_readback(fields)
        return {"speakable": speakable, "ok": True}

    if name == "get_available_slots":
        from app.config import get_settings

        slots = appointments.list_available(
            preferred_day=args.get("preferred_day"),
            time_of_day=args.get("time_of_day"),
            limit=3,
        )
        if not slots:
            return {
                "slots": [],
                "speakable": "I don't have open slots matching that preference right now.",
            }
        tz = get_settings().clinic_timezone
        spoken = []
        out = []
        for i, s in enumerate(slots, 1):
            label = speak_slot(s.starts_at, tz)
            spoken.append(f"option {i}: {label} with {s.provider_name}")
            out.append(
                {
                    "slot_id": str(s.id),
                    "starts_at": s.starts_at.isoformat(),
                    "provider_name": s.provider_name,
                    "label": label,
                }
            )
        return {
            "slots": out,
            "speakable": "I have " + "; ".join(spoken) + ". Which works for you?",
        }

    if name == "book_appointment":
        try:
            pid = uuid.UUID(str(args.get("patient_id")))
            sid = uuid.UUID(str(args.get("slot_id")))
        except (ValueError, TypeError):
            return {"ok": False, "speakable": "I need a valid patient and slot to book."}
        appt, error = appointments.book(
            patient_id=pid, slot_id=sid, reason=args.get("reason")
        )
        if error:
            return {"ok": False, "speakable": f"I couldn't book that — {error}."}
        return {
            "ok": True,
            "appointment_id": str(appt.id),
            "speakable": "You're booked. We'll see you then.",
        }

    return {
        "ok": False,
        "speakable": f"I don't know how to handle {name}.",
    }
