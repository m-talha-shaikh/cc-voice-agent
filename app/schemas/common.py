"""Consistent API response envelope."""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class Meta(BaseModel):
    total: Optional[int] = None
    limit: Optional[int] = None
    offset: Optional[int] = None


class Envelope(BaseModel, Generic[T]):
    data: Optional[T] = None
    error: Optional[ErrorBody] = None
    meta: Optional[Meta] = None


def ok(data: Any = None, meta: Meta | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, **({"meta": meta.model_dump()} if meta else {})}


def err(code: str, message: str, details: list[dict] | None = None) -> dict[str, Any]:
    return {
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        },
    }
