"""SQLAlchemy models — patients, calls, appointments."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SexEnum(str, enum.Enum):
    male = "Male"
    female = "Female"
    other = "Other"
    decline = "Decline to Answer"


class CallStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    dropped = "dropped"
    failed = "failed"


class CallOutcome(str, enum.Enum):
    registered = "registered"
    updated = "updated"
    abandoned = "abandoned"
    error = "error"


class AppointmentStatus(str, enum.Enum):
    scheduled = "scheduled"
    cancelled = "cancelled"
    completed = "completed"


# 50 states + DC + common territories
US_STATE_CODES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
)


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[SexEnum] = mapped_column(
        Enum(
            SexEnum,
            name="sex_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    address_line_1: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line_2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    insurance_member_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    preferred_language: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'English'")
    )
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_via: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'api'")
    )  # api | voice
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    calls: Mapped[list[Call]] = relationship(back_populates="patient")
    appointments: Mapped[list[Appointment]] = relationship(back_populates="patient")

    __table_args__ = (
        CheckConstraint(
            "first_name ~ '^[A-Za-z][A-Za-z''\\- ]{0,49}$'",
            name="ck_patients_first_name",
        ),
        CheckConstraint(
            "last_name ~ '^[A-Za-z][A-Za-z''\\- ]{0,49}$'",
            name="ck_patients_last_name",
        ),
        CheckConstraint(
            "date_of_birth <= CURRENT_DATE AND date_of_birth >= DATE '1900-01-01'",
            name="ck_patients_dob",
        ),
        CheckConstraint(
            "phone_number ~ '^[2-9][0-9]{2}[2-9][0-9]{6}$'",
            name="ck_patients_phone",
        ),
        CheckConstraint(
            "email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
            name="ck_patients_email",
        ),
        CheckConstraint(
            "char_length(city) BETWEEN 1 AND 100",
            name="ck_patients_city",
        ),
        CheckConstraint(
            "state = ANY (ARRAY[" + ",".join(f"'{s}'" for s in US_STATE_CODES) + "])",
            name="ck_patients_state",
        ),
        CheckConstraint(
            "zip_code ~ '^\\d{5}(-\\d{4})?$'",
            name="ck_patients_zip",
        ),
        CheckConstraint(
            "insurance_member_id IS NULL OR insurance_member_id ~ '^[A-Za-z0-9\\-]+$'",
            name="ck_patients_insurance_member",
        ),
        CheckConstraint(
            "emergency_contact_phone IS NULL OR emergency_contact_phone ~ '^[2-9][0-9]{2}[2-9][0-9]{6}$'",
            name="ck_patients_ec_phone",
        ),
        Index("ix_patients_last_name_lower", func.lower(last_name)),
        Index("ix_patients_dob", "date_of_birth"),
        Index("ix_patients_phone", "phone_number"),
        Index(
            "ix_patients_active",
            "patient_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vapi_call_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=True
    )
    caller_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=text("'in_progress'"),
    )
    ended_reason: Mapped[Optional[str]] = mapped_column(String(100))
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    messages: Mapped[Optional[dict]] = mapped_column(JSONB)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    recording_url: Mapped[Optional[str]] = mapped_column(Text)
    collected_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    outcome: Mapped[Optional[CallOutcome]] = mapped_column(
        Enum(CallOutcome, name="call_outcome_enum", values_callable=lambda x: [e.value for e in x]),
    )

    patient: Mapped[Optional[Patient]] = relationship(back_populates="calls")


class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="Dr. Patel")
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    appointment: Mapped[Optional[Appointment]] = relationship(back_populates="slot", uselist=False)

    __table_args__ = (Index("ix_slots_starts", "starts_at"),)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=False
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_slots.id"), nullable=False, unique=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            name="appointment_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        server_default=text("'scheduled'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    patient: Mapped[Patient] = relationship(back_populates="appointments")
    slot: Mapped[AppointmentSlot] = relationship(back_populates="appointment")

    __table_args__ = (UniqueConstraint("slot_id", name="uq_appointments_slot"),)
