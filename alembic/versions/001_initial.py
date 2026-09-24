"""initial schema: patients, calls, appointments

Revision ID: 001_initial
Revises:
Create Date: 2026-09-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

US_STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "VI", "GU", "AS", "MP",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    sex_enum = postgresql.ENUM(
        "Male", "Female", "Other", "Decline to Answer",
        name="sex_enum",
        create_type=False,
    )
    call_status = postgresql.ENUM(
        "in_progress", "completed", "dropped", "failed",
        name="call_status_enum",
        create_type=False,
    )
    call_outcome = postgresql.ENUM(
        "registered", "updated", "abandoned", "error",
        name="call_outcome_enum",
        create_type=False,
    )
    appt_status = postgresql.ENUM(
        "scheduled", "cancelled", "completed",
        name="appointment_status_enum",
        create_type=False,
    )

    op.execute(
        "CREATE TYPE sex_enum AS ENUM ('Male', 'Female', 'Other', 'Decline to Answer')"
    )
    op.execute(
        "CREATE TYPE call_status_enum AS ENUM ('in_progress', 'completed', 'dropped', 'failed')"
    )
    op.execute(
        "CREATE TYPE call_outcome_enum AS ENUM ('registered', 'updated', 'abandoned', 'error')"
    )
    op.execute(
        "CREATE TYPE appointment_status_enum AS ENUM ('scheduled', 'cancelled', 'completed')"
    )

    op.create_table(
        "patients",
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("first_name", sa.String(50), nullable=False),
        sa.Column("last_name", sa.String(50), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("sex", sex_enum, nullable=False),
        sa.Column("phone_number", sa.String(10), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("address_line_1", sa.String(200), nullable=False),
        sa.Column("address_line_2", sa.String(200), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("zip_code", sa.String(10), nullable=False),
        sa.Column("insurance_provider", sa.String(100), nullable=True),
        sa.Column("insurance_member_id", sa.String(50), nullable=True),
        sa.Column("preferred_language", sa.String(50), nullable=False, server_default=sa.text("'English'")),
        sa.Column("emergency_contact_name", sa.String(100), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(10), nullable=True),
        sa.Column("created_via", sa.String(20), nullable=False, server_default=sa.text("'api'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("first_name ~ '^[A-Za-z][A-Za-z''\\- ]{0,49}$'", name="ck_patients_first_name"),
        sa.CheckConstraint("last_name ~ '^[A-Za-z][A-Za-z''\\- ]{0,49}$'", name="ck_patients_last_name"),
        sa.CheckConstraint(
            "date_of_birth <= CURRENT_DATE AND date_of_birth >= DATE '1900-01-01'",
            name="ck_patients_dob",
        ),
        sa.CheckConstraint("phone_number ~ '^[2-9][0-9]{2}[2-9][0-9]{6}$'", name="ck_patients_phone"),
        sa.CheckConstraint(
            "email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
            name="ck_patients_email",
        ),
        sa.CheckConstraint("char_length(city) BETWEEN 1 AND 100", name="ck_patients_city"),
        sa.CheckConstraint(
            "state = ANY (ARRAY[" + ",".join(f"'{s}'" for s in US_STATES) + "])",
            name="ck_patients_state",
        ),
        sa.CheckConstraint("zip_code ~ '^\\d{5}(-\\d{4})?$'", name="ck_patients_zip"),
        sa.CheckConstraint(
            "insurance_member_id IS NULL OR insurance_member_id ~ '^[A-Za-z0-9\\-]+$'",
            name="ck_patients_insurance_member",
        ),
        sa.CheckConstraint(
            "emergency_contact_phone IS NULL OR emergency_contact_phone ~ '^[2-9][0-9]{2}[2-9][0-9]{6}$'",
            name="ck_patients_ec_phone",
        ),
    )
    op.create_index("ix_patients_last_name_lower", "patients", [sa.text("lower(last_name)")])
    op.create_index("ix_patients_dob", "patients", ["date_of_birth"])
    op.create_index("ix_patients_phone", "patients", ["phone_number"])
    op.execute(
        "CREATE INDEX ix_patients_active ON patients (patient_id) WHERE deleted_at IS NULL"
    )

    # updated_at trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_patients_updated_at
        BEFORE UPDATE ON patients
        FOR EACH ROW EXECUTE PROCEDURE set_updated_at();
        """
    )

    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("vapi_call_id", sa.String(100), nullable=False, unique=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.patient_id"), nullable=True),
        sa.Column("caller_number", sa.String(20), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("status", call_status, nullable=False, server_default=sa.text("'in_progress'")),
        sa.Column("ended_reason", sa.String(100), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("messages", postgresql.JSONB(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("collected_payload", postgresql.JSONB(), nullable=True),
        sa.Column("outcome", call_outcome, nullable=True),
    )

    op.create_table(
        "appointment_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False, server_default="Dr. Patel"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_slots_starts", "appointment_slots", ["starts_at"])

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.patient_id"), nullable=False),
        sa.Column("slot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointment_slots.id"), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("status", appt_status, nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("slot_id", name="uq_appointments_slot"),
    )


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_index("ix_slots_starts", table_name="appointment_slots")
    op.drop_table("appointment_slots")
    op.drop_table("calls")
    op.execute("DROP TRIGGER IF EXISTS trg_patients_updated_at ON patients")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at")
    op.execute("DROP INDEX IF EXISTS ix_patients_active")
    op.drop_index("ix_patients_phone", table_name="patients")
    op.drop_index("ix_patients_dob", table_name="patients")
    op.drop_index("ix_patients_last_name_lower", table_name="patients")
    op.drop_table("patients")
    op.execute("DROP TYPE IF EXISTS appointment_status_enum")
    op.execute("DROP TYPE IF EXISTS call_outcome_enum")
    op.execute("DROP TYPE IF EXISTS call_status_enum")
    op.execute("DROP TYPE IF EXISTS sex_enum")
