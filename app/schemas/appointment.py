from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    provider_name: str
    is_available: bool


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: uuid.UUID
    slot_id: uuid.UUID
    reason: Optional[str] = Field(default=None, max_length=200)


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    slot_id: uuid.UUID
    reason: Optional[str] = None
    status: str
    created_at: datetime
    slot: Optional[SlotOut] = None
