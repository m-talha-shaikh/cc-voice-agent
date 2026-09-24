"""Call history / end-of-call persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, CallOutcome, CallStatus


class CallService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_from_status(
        self,
        *,
        vapi_call_id: str,
        status: CallStatus,
        caller_number: str | None = None,
        started_at: datetime | None = None,
    ) -> Call:
        call = self.db.scalar(select(Call).where(Call.vapi_call_id == vapi_call_id))
        if not call:
            call = Call(vapi_call_id=vapi_call_id, status=status)
            self.db.add(call)
        call.status = status
        if caller_number:
            call.caller_number = caller_number
        if started_at:
            call.started_at = started_at
        self.db.commit()
        self.db.refresh(call)
        return call

    def finalize_end_of_call(self, payload: dict[str, Any]) -> Call:
        call_obj = payload.get("call") or {}
        vapi_call_id = call_obj.get("id") or payload.get("id") or "unknown"
        call = self.db.scalar(select(Call).where(Call.vapi_call_id == vapi_call_id))
        if not call:
            call = Call(vapi_call_id=vapi_call_id, status=CallStatus.completed)
            self.db.add(call)

        ended_reason = payload.get("endedReason") or call_obj.get("endedReason")
        call.ended_reason = ended_reason
        call.transcript = payload.get("transcript") or call_obj.get("transcript")
        call.summary = (payload.get("summary") or call_obj.get("summary") or "") or None
        call.recording_url = (
            payload.get("recordingUrl")
            or (payload.get("artifact") or {}).get("recordingUrl")
            or call_obj.get("recordingUrl")
        )
        call.messages = payload.get("messages") or call_obj.get("messages")
        call.collected_payload = payload.get("artifact") or payload.get("analysis")

        started = call_obj.get("startedAt") or payload.get("startedAt")
        ended = call_obj.get("endedAt") or payload.get("endedAt")
        if started:
            call.started_at = _parse_dt(started)
        if ended:
            call.ended_at = _parse_dt(ended)
        if call.started_at and call.ended_at:
            call.duration_s = int((call.ended_at - call.started_at).total_seconds())

        # Dropped / abandoned if hangup-like reasons before a successful outcome
        reason_l = str(ended_reason or "").lower()
        if reason_l and any(
            r in reason_l
            for r in (
                "hang",
                "disconnect",
                "drop",
                "timeout",
                "error",
                "customer-ended-call",
                "silence-timed-out",
            )
        ):
            if not call.outcome:
                call.status = CallStatus.dropped
                call.outcome = CallOutcome.abandoned
        else:
            call.status = CallStatus.completed
        # Link patient if tool results stored patient_id somewhere in messages
        patient_id = _extract_patient_id(call.messages) or _extract_patient_id(call.collected_payload)
        if patient_id:
            try:
                call.patient_id = uuid.UUID(str(patient_id))
            except ValueError:
                pass

        self.db.commit()
        self.db.refresh(call)
        return call

    def link_patient(
        self,
        vapi_call_id: str,
        patient_id: uuid.UUID,
        outcome: CallOutcome,
        collected: dict | None = None,
    ) -> None:
        call = self.db.scalar(select(Call).where(Call.vapi_call_id == vapi_call_id))
        if not call:
            call = Call(vapi_call_id=vapi_call_id, status=CallStatus.in_progress)
            self.db.add(call)
        call.patient_id = patient_id
        call.outcome = outcome
        if collected:
            call.collected_payload = collected
        self.db.commit()

    def list_for_patient(self, patient_id: uuid.UUID) -> list[Call]:
        return list(
            self.db.scalars(
                select(Call)
                .where(Call.patient_id == patient_id)
                .order_by(Call.started_at.desc().nullslast())
            )
        )

    def list_recent(self, limit: int = 50) -> list[Call]:
        return list(
            self.db.scalars(
                select(Call).order_by(Call.started_at.desc().nullslast()).limit(limit)
            )
        )


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_patient_id(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        if "patient_id" in obj:
            return str(obj["patient_id"])
        for v in obj.values():
            found = _extract_patient_id(v)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _extract_patient_id(item)
            if found:
                return found
    return None
