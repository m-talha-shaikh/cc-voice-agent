"""Patient validation — single source of truth for API and voice tools."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Optional

import pytz
from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.config import get_settings
from app.db.models import SexEnum, US_STATE_CODES

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\- ]{0,49}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
MEMBER_RE = re.compile(r"^[A-Za-z0-9\-]+$")
PHONE_DIGITS_RE = re.compile(r"\D+")

STATE_ALIASES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "calif": "CA", "calif.": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "florida.": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
    "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "washington dc": "DC", "washington d.c.": "DC", "puerto rico": "PR",
}

SEX_ALIASES: dict[str, SexEnum] = {
    "male": SexEnum.male, "m": SexEnum.male, "man": SexEnum.male, "boy": SexEnum.male,
    "female": SexEnum.female, "f": SexEnum.female, "woman": SexEnum.female, "girl": SexEnum.female,
    "other": SexEnum.other, "nonbinary": SexEnum.other, "non-binary": SexEnum.other,
    "decline to answer": SexEnum.decline, "decline": SexEnum.decline,
    "prefer not to say": SexEnum.decline, "prefer not to answer": SexEnum.decline,
}


def strip_control(value: str) -> str:
    return "".join(ch for ch in value if ch == "\t" or (ord(ch) >= 32 and ord(ch) != 127)).strip()


def normalize_phone(value: Any) -> str:
    if value is None:
        raise ValueError("phone_number: is required")
    raw = strip_control(str(value))
    digits = PHONE_DIGITS_RE.sub("", raw)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"phone_number: must be 10 digits, got {len(digits)}")
    if digits[0] in "01" or digits[3] in "01":
        raise ValueError("phone_number: invalid U.S. area code or exchange (cannot start with 0 or 1)")
    return digits


def normalize_state(value: Any) -> str:
    if value is None:
        raise ValueError("state: is required")
    raw = strip_control(str(value))
    upper = raw.upper()
    if upper in US_STATE_CODES:
        return upper
    mapped = STATE_ALIASES.get(raw.lower())
    if mapped:
        return mapped
    raise ValueError(f"state: must be a valid 2-letter U.S. state code, got '{raw}'")


def normalize_sex(value: Any) -> SexEnum:
    if value is None:
        raise ValueError("sex: is required")
    if isinstance(value, SexEnum):
        return value
    raw = strip_control(str(value))
    for member in SexEnum:
        if raw.lower() == member.value.lower():
            return member
    mapped = SEX_ALIASES.get(raw.lower())
    if mapped:
        return mapped
    raise ValueError(
        "sex: must be one of Male, Female, Other, Decline to Answer"
    )


def normalize_dob(value: Any) -> date:
    if value is None:
        raise ValueError("date_of_birth: is required")
    if isinstance(value, date) and not isinstance(value, datetime):
        dob = value
    else:
        raw = strip_control(str(value))
        # Prefer MM/DD/YYYY
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d %Y", "%B %d, %Y"):
            try:
                dob = datetime.strptime(raw, fmt).date()
                break
            except ValueError:
                dob = None  # type: ignore
        else:
            try:
                dob = date_parser.parse(raw, fuzzy=True).date()
            except (ValueError, OverflowError, TypeError) as exc:
                raise ValueError(
                    f"date_of_birth: could not parse '{raw}' (use MM/DD/YYYY)"
                ) from exc

    tz = pytz.timezone(get_settings().clinic_timezone)
    today = datetime.now(tz).date()
    if dob > today:
        raise ValueError("date_of_birth: cannot be in the future")
    if dob < date(1900, 1, 1):
        raise ValueError("date_of_birth: must be on or after 1900-01-01")
    return dob


def normalize_name(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(f"{field}: is required")
    raw = strip_control(str(value))
    if not raw:
        raise ValueError(f"{field}: is required")
    # Title-case while preserving O'Brien / McDonald / Smith-Jones patterns
    parts = []
    for chunk in raw.split(" "):
        if not chunk:
            continue
        if "-" in chunk:
            parts.append("-".join(_title_piece(p) for p in chunk.split("-")))
        elif "'" in chunk:
            parts.append("'".join(_title_piece(p) for p in chunk.split("'")))
        else:
            parts.append(_title_piece(chunk))
    result = " ".join(parts)
    if not NAME_RE.match(result):
        raise ValueError(
            f"{field}: 1–50 chars, letters, hyphens, apostrophes and spaces only"
        )
    return result


def _title_piece(piece: str) -> str:
    if not piece:
        return piece
    lower = piece.lower()
    if lower.startswith("mc") and len(lower) > 2:
        return "Mc" + lower[2:].capitalize()
    return piece.capitalize()


def normalize_zip(value: Any) -> str:
    if value is None:
        raise ValueError("zip_code: is required")
    raw = strip_control(str(value)).replace(" ", "")
    if not ZIP_RE.match(raw):
        raise ValueError("zip_code: must be 5-digit or ZIP+4 (12345 or 12345-6789)")
    return raw


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: str
    last_name: str
    date_of_birth: date | str
    sex: SexEnum | str
    phone_number: str
    address_line_1: str = Field(..., min_length=1, max_length=200)
    city: str = Field(..., min_length=1, max_length=100)
    state: str
    zip_code: str
    email: Optional[EmailStr | str] = None
    address_line_2: Optional[str] = Field(default=None, max_length=200)
    insurance_provider: Optional[str] = Field(default=None, max_length=100)
    insurance_member_id: Optional[str] = Field(default=None, max_length=50)
    preferred_language: str = Field(default="English", max_length=50)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=100)
    emergency_contact_phone: Optional[str] = None
    created_via: str = Field(default="api", pattern="^(api|voice)$")

    @field_validator("first_name", mode="before")
    @classmethod
    def _fn(cls, v: Any) -> str:
        return normalize_name(v, "first_name")

    @field_validator("last_name", mode="before")
    @classmethod
    def _ln(cls, v: Any) -> str:
        return normalize_name(v, "last_name")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, v: Any) -> date:
        return normalize_dob(v)

    @field_validator("sex", mode="before")
    @classmethod
    def _sex(cls, v: Any) -> SexEnum:
        return normalize_sex(v)

    @field_validator("phone_number", mode="before")
    @classmethod
    def _phone(cls, v: Any) -> str:
        return normalize_phone(v)

    @field_validator("state", mode="before")
    @classmethod
    def _state(cls, v: Any) -> str:
        return normalize_state(v)

    @field_validator("zip_code", mode="before")
    @classmethod
    def _zip(cls, v: Any) -> str:
        return normalize_zip(v)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return strip_control(str(v)).lower()

    @field_validator("address_line_1", "address_line_2", "city", "insurance_provider",
                     "emergency_contact_name", "preferred_language", mode="before")
    @classmethod
    def _strip_str(cls, v: Any) -> Any:
        if v is None:
            return None
        s = strip_control(str(v))
        return s if s else None

    @field_validator("insurance_member_id", mode="before")
    @classmethod
    def _member(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        s = strip_control(str(v))
        if not MEMBER_RE.match(s):
            raise ValueError("insurance_member_id: alphanumeric and hyphens only")
        return s

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def _ec_phone(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return normalize_phone(v)

    @model_validator(mode="after")
    def _city_required(self) -> PatientCreate:
        if not self.city:
            raise ValueError("city: is required")
        if not self.address_line_1:
            raise ValueError("address_line_1: is required")
        return self


class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date | str] = None
    sex: Optional[SexEnum | str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr | str] = None
    address_line_1: Optional[str] = Field(default=None, min_length=1, max_length=200)
    address_line_2: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, min_length=1, max_length=100)
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = Field(default=None, max_length=100)
    insurance_member_id: Optional[str] = Field(default=None, max_length=50)
    preferred_language: Optional[str] = Field(default=None, max_length=50)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=100)
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", mode="before")
    @classmethod
    def _fn(cls, v: Any) -> Any:
        return normalize_name(v, "first_name") if v is not None else None

    @field_validator("last_name", mode="before")
    @classmethod
    def _ln(cls, v: Any) -> Any:
        return normalize_name(v, "last_name") if v is not None else None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, v: Any) -> Any:
        return normalize_dob(v) if v is not None else None

    @field_validator("sex", mode="before")
    @classmethod
    def _sex(cls, v: Any) -> Any:
        return normalize_sex(v) if v is not None else None

    @field_validator("phone_number", mode="before")
    @classmethod
    def _phone(cls, v: Any) -> Any:
        return normalize_phone(v) if v is not None else None

    @field_validator("state", mode="before")
    @classmethod
    def _state(cls, v: Any) -> Any:
        return normalize_state(v) if v is not None else None

    @field_validator("zip_code", mode="before")
    @classmethod
    def _zip(cls, v: Any) -> Any:
        return normalize_zip(v) if v is not None else None

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return strip_control(str(v)).lower()

    @field_validator("insurance_member_id", mode="before")
    @classmethod
    def _member(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        s = strip_control(str(v))
        if not MEMBER_RE.match(s):
            raise ValueError("insurance_member_id: alphanumeric and hyphens only")
        return s

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def _ec_phone(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return normalize_phone(v)

    @field_validator(
        "address_line_1", "address_line_2", "city", "insurance_provider",
        "emergency_contact_name", "preferred_language", mode="before"
    )
    @classmethod
    def _strip(cls, v: Any) -> Any:
        if v is None:
            return None
        s = strip_control(str(v))
        return s if s else None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    sex: SexEnum
    phone_number: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_via: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class FieldValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: dict[str, Any]
