"""
pytest fixtures — uses DATABASE_URL (Neon or local Postgres).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure settings load before app import
os.environ.setdefault("CLINIC_TIMEZONE", "America/New_York")

from app.config import get_settings, sqlalchemy_url  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(scope="session")
def engine(settings):
    eng = create_engine(sqlalchemy_url(settings.database_url), pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    return eng


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_patient():
    return {
        "first_name": "Alice",
        "last_name": "Johnson",
        "date_of_birth": "04/12/1992",
        "sex": "Female",
        "phone_number": "(512) 555-0142",
        "email": "alice.j@example.com",
        "address_line_1": "42 Oak Ave",
        "city": "Austin",
        "state": "texas",
        "zip_code": "78701",
    }
