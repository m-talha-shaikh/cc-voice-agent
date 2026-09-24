"""Unit tests for validators / normalizers."""

from datetime import date, timedelta

import pytest

from app.schemas.patient import (
    normalize_dob,
    normalize_name,
    normalize_phone,
    normalize_sex,
    normalize_state,
    normalize_zip,
)
from app.db.models import SexEnum


def test_phone_formats():
    assert normalize_phone("(415) 555-0123") == "4155550123"
    assert normalize_phone("415.555.0123") == "4155550123"
    assert normalize_phone("+1 415 555 0123") == "4155550123"


def test_phone_too_short():
    with pytest.raises(ValueError, match="must be 10 digits"):
        normalize_phone("415")


def test_state_aliases():
    assert normalize_state("california") == "CA"
    assert normalize_state("Calif.") == "CA"
    assert normalize_state("ny") == "NY"


def test_sex_aliases():
    assert normalize_sex("man") == SexEnum.male
    assert normalize_sex("F") == SexEnum.female
    assert normalize_sex("prefer not to say") == SexEnum.decline


def test_dob_future():
    future = (date.today() + timedelta(days=3)).strftime("%m/%d/%Y")
    with pytest.raises(ValueError, match="future"):
        normalize_dob(future)


def test_dob_formats():
    assert normalize_dob("03/03/1990") == date(1990, 3, 3)
    assert normalize_dob("1990-03-03") == date(1990, 3, 3)


def test_zip():
    assert normalize_zip("94105") == "94105"
    assert normalize_zip("94105-1234") == "94105-1234"
    with pytest.raises(ValueError):
        normalize_zip("9410")


def test_names():
    assert normalize_name("mary ann", "first_name") == "Mary Ann"
    assert normalize_name("o'brien", "last_name") == "O'Brien"
    assert normalize_name("smith-jones", "last_name") == "Smith-Jones"
