"""Vapi HTTP adapter — tool-calls + webhooks."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import CallStatus
from app.db.session import get_db
from app.schemas.common import err
from app.services.call import CallService
from app.voice.tools import dispatch_tool

router = APIRouter(prefix="/vapi", tags=["vapi"])
log = logging.getLogger(__name__)


def _check_secret(x_vapi_secret: str | None) -> JSONResponse | None:
    expected = get_settings().vapi_webhook_secret
    if not x_vapi_secret or x_vapi_secret != expected:
        return JSONResponse(status_code=401, content=err("unauthorized", "Invalid Vapi secret"))
    return None


@router.post("/tools")
async def vapi_tools(
    request: Request,
    db: Session = Depends(get_db),
    x_vapi_secret: str | None = Header(default=None, alias="X-Vapi-Secret"),
):
    denied = _check_secret(x_vapi_secret)
    if denied:
        return denied

    body: dict[str, Any] = await request.json()
    message = body.get("message") or body
    call = (message.get("call") or body.get("call") or {})
    call_id = call.get("id")

    # Vapi sends toolWithToolCallList or toolCalls depending on version
    tool_calls = []
    if "toolWithToolCallList" in message:
        for item in message["toolWithToolCallList"]:
            tool = item.get("tool") or {}
            tc = item.get("toolCall") or item.get("toolCallId") or {}
            tool_calls.append(
                {
                    "id": (tc.get("id") if isinstance(tc, dict) else item.get("toolCallId")),
                    "name": tool.get("name") or (tc.get("function") or {}).get("name"),
                    "arguments": (tc.get("function") or {}).get("arguments")
                    or item.get("parameters")
                    or {},
                }
            )
    elif "toolCalls" in message:
        for tc in message["toolCalls"]:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                import json

                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                {"id": tc.get("id"), "name": fn.get("name"), "arguments": args}
            )
    elif message.get("type") == "tool-calls":
        for tc in message.get("toolCallList") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or tc.get("parameters") or {}
            if isinstance(args, str):
                import json

                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                {
                    "id": tc.get("id") or tc.get("toolCallId"),
                    "name": fn.get("name") or tc.get("name"),
                    "arguments": args,
                }
            )

    results = []
    for tc in tool_calls:
        name = tc.get("name") or "unknown"
        args = tc.get("arguments") or {}
        if isinstance(args, str):
            import json

            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        result = dispatch_tool(db, name, args, call_id=call_id)
        results.append({"toolCallId": tc.get("id"), "result": result})

    return {"results": results}


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_vapi_secret: str | None = Header(default=None, alias="X-Vapi-Secret"),
):
    denied = _check_secret(x_vapi_secret)
    if denied:
        return denied

    body: dict[str, Any] = await request.json()
    message = body.get("message") or body
    msg_type = message.get("type") or body.get("type")
    call = message.get("call") or body.get("call") or {}
    call_id = call.get("id")
    caller = (call.get("customer") or {}).get("number") or call.get("phoneNumber")

    log.info("vapi_webhook type=%s", msg_type, extra={"call_id": call_id})

    if msg_type == "status-update":
        status_raw = (message.get("status") or "").lower()
        status = CallStatus.in_progress
        if status_raw in ("ended", "completed"):
            status = CallStatus.completed
        elif status_raw in ("failed",):
            status = CallStatus.failed
        if call_id:
            CallService(db).upsert_from_status(
                vapi_call_id=call_id,
                status=status,
                caller_number=caller,
            )
    elif msg_type in ("end-of-call-report", "hang"):
        # Persist transcript/summary; never create a half-finished patient here
        if msg_type == "end-of-call-report":
            call_row = CallService(db).finalize_end_of_call(message)
            log.info(
                "end_of_call outcome=%s",
                call_row.outcome,
                extra={"call_id": call_id},
            )
        elif call_id:
            CallService(db).upsert_from_status(
                vapi_call_id=call_id,
                status=CallStatus.dropped,
                caller_number=caller,
            )

    return {"ok": True}
