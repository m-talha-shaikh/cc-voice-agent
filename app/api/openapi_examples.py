"""OpenAPI response examples for reviewer-friendly /docs."""

from __future__ import annotations

PATIENT_EXAMPLE = {
    "patient_id": "c6798b61-6f25-426b-9480-c798e50c4480",
    "first_name": "Jane",
    "last_name": "Doe",
    "date_of_birth": "1990-03-03",
    "sex": "Female",
    "phone_number": "4155550100",
    "email": "jane.doe@example.com",
    "address_line_1": "100 Market St",
    "address_line_2": "Apt 4B",
    "city": "San Francisco",
    "state": "CA",
    "zip_code": "94105",
    "insurance_provider": None,
    "insurance_member_id": None,
    "preferred_language": "English",
    "emergency_contact_name": None,
    "emergency_contact_phone": None,
    "created_via": "api",
    "created_at": "2026-09-24T08:00:00Z",
    "updated_at": "2026-09-24T08:00:00Z",
    "deleted_at": None,
}

ENVELOPE_OK = {
    "description": "Success envelope",
    "content": {
        "application/json": {
            "example": {"data": PATIENT_EXAMPLE, "error": None},
        }
    },
}

ENVELOPE_LIST = {
    "description": "List with pagination meta",
    "content": {
        "application/json": {
            "example": {
                "data": [PATIENT_EXAMPLE],
                "error": None,
                "meta": {"total": 1, "limit": 50, "offset": 0},
            }
        }
    },
}

ENVELOPE_422 = {
    "description": "Validation error envelope",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": [
                        {"field": "phone_number", "message": "phone_number: must be 10 digits, got 3"}
                    ],
                },
            }
        }
    },
}

ENVELOPE_404 = {
    "description": "Not found envelope",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "error": {"code": "not_found", "message": "Patient not found", "details": []},
            }
        }
    },
}
