"""CareCloud Voice AI — Patient Registration FastAPI app."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import appointments, health, patients
from app.config import get_settings
from app.dashboard.router import router as dashboard_router
from app.logging_config import setup_logging
from app.schemas.common import err
from app.voice.router import router as vapi_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    yield


app = FastAPI(
    title="CareCloud Voice Patient Registration",
    version="1.0.0",
    description=(
        "Voice AI patient registration with REST API and dashboard.\n\n"
        "**Architecture:** Vapi (telephony/STT/TTS/LLM) → FastAPI service layer → Neon Postgres.\n"
        "Voice tools and REST share the same validation (`schemas/`) and services.\n\n"
        "See `/dashboard` for live patients/calls and a browser call fallback."
    ),
    lifespan=lifespan,
    contact={"name": "CareCloud Take-Home Submission"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Malformed JSON bodies surface as type errors under "body"
    errors = exc.errors()
    is_json = any(
        e.get("type") in ("json_invalid", "json_decode")
        or (e.get("loc") == ("body",) and "json" in str(e.get("msg", "")).lower())
        for e in errors
    )
    details = [
        {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
        for e in errors
    ]
    status = 400 if is_json else 422
    code = "bad_request" if is_json else "validation_error"
    return JSONResponse(
        status_code=status,
        content=err(code, "Validation failed" if status == 422 else "Malformed request", details),
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(_request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=err("http_error", str(exc.detail)),
    )


@app.exception_handler(Exception)
async def unhandled_handler(_request: Request, exc: Exception):
    import logging

    logging.getLogger(__name__).exception("unhandled", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=err("internal_error", "An unexpected error occurred"),
    )


@app.get("/")
def index():
    settings = get_settings()
    return {
        "data": {
            "service": settings.app_name,
            "links": {
                "health": "/healthz",
                "docs": "/docs",
                "patients": "/patients",
                "dashboard": "/dashboard",
                "appointments_slots": "/appointments/slots",
            },
            "phone_number": settings.vapi_phone_number,
            "public_base_url": settings.public_base_url,
        },
        "error": None,
    }


app.include_router(health.router)
app.include_router(patients.router)
app.include_router(appointments.router)
app.include_router(vapi_router)
app.include_router(dashboard_router)

try:
    app.mount("/static", StaticFiles(directory="app/dashboard/static"), name="static")
except RuntimeError:
    pass
