"""Speakable formatting helpers for voice readback."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

# Full state names for spoken readback
STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico", "VI": "Virgin Islands", "GU": "Guam", "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
}

_ORDINAL = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second",
    23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth",
    26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth",
    29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first",
}


def speak_date(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    month = d.strftime("%B")
    day = _ORDINAL.get(d.day, str(d.day))
    year = _speak_year(d.year)
    return f"{month} {day}, {year}"


def _speak_year(year: int) -> str:
    if year == 2000:
        return "two thousand"
    if 2001 <= year <= 2009:
        return f"two thousand {_ORDINAL.get(year - 2000, str(year - 2000))}"
    if 2010 <= year <= 2099:
        return f"twenty {_speak_two_digit(year % 100)}"
    if 1900 <= year <= 1999:
        return f"nineteen {_speak_two_digit(year % 100)}"
    return str(year)


def _speak_two_digit(n: int) -> str:
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = [
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
        "sixteen", "seventeen", "eighteen", "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    if n < 10:
        return ones[n]
    if n < 20:
        return teens[n - 10]
    t, o = divmod(n, 10)
    return tens[t] if o == 0 else f"{tens[t]}-{ones[o]}"


def speak_phone(digits: str) -> str:
    d = "".join(c for c in digits if c.isdigit())
    if len(d) != 10:
        return digits
    return f"{d[0:3]}-{d[3:6]}-{d[6:10]}"


def speak_zip(zip_code: str) -> str:
    return " ".join(list(zip_code.replace("-", " ")))


def speak_state(code: str) -> str:
    return STATE_NAMES.get(code.upper(), code)


def speak_slot(dt: datetime, tz_name: str = "America/New_York") -> str:
    local = dt.astimezone(ZoneInfo(tz_name))
    # Avoid %-d (platform-specific); strip leading zeros manually
    day = local.day
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%A')}, {local.strftime('%B')} {day} at {hour}:{local.strftime('%M %p')}"


def patient_readback(fields: dict) -> str:
    """Build a natural confirmation paragraph from collected fields."""
    parts = [
        f"I have {fields.get('first_name')} {fields.get('last_name')}",
    ]
    if fields.get("date_of_birth"):
        parts.append(f"born {speak_date(fields['date_of_birth'])}")
    if fields.get("sex"):
        parts.append(f"sex {fields['sex']}")
    if fields.get("phone_number"):
        parts.append(f"phone {speak_phone(str(fields['phone_number']))}")
    addr = fields.get("address_line_1", "")
    if fields.get("address_line_2"):
        addr = f"{addr}, {fields['address_line_2']}"
    if addr:
        city = fields.get("city", "")
        state = speak_state(str(fields.get("state", "")))
        z = speak_zip(str(fields.get("zip_code", "")))
        parts.append(f"address {addr}, {city}, {state}, ZIP {z}")
    if fields.get("email"):
        parts.append(f"email {fields['email']}")
    if fields.get("insurance_provider"):
        parts.append(f"insurance {fields['insurance_provider']}")
    if fields.get("emergency_contact_name"):
        parts.append(
            f"emergency contact {fields['emergency_contact_name']} "
            f"at {speak_phone(str(fields.get('emergency_contact_phone') or ''))}"
        )
    if fields.get("preferred_language"):
        parts.append(f"preferred language {fields['preferred_language']}")
    return ". ".join(parts) + ". Does that all sound correct?"
