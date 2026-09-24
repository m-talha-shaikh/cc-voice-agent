#!/usr/bin/env python3
"""Validate configured API keys without printing secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402


def main() -> int:
    s = get_settings()
    results: list[tuple[str, bool, str]] = []
    headers_ua = {"User-Agent": "carecloud-verify/1.0"}

    with httpx.Client(timeout=25.0, headers=headers_ua) as c:
        # Deepgram
        if s.deepgram_api_key:
            r = c.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {s.deepgram_api_key}"},
            )
            results.append(("Deepgram", r.status_code == 200, f"HTTP {r.status_code}"))
        else:
            results.append(("Deepgram", False, "missing key"))

        # Groq
        if s.groq_api_key:
            r = c.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
            )
            results.append(("Groq", r.status_code == 200, f"HTTP {r.status_code}"))
        else:
            results.append(("Groq", False, "missing key (optional if using vapi-openai)"))

        # Vapi
        r = c.get(
            "https://api.vapi.ai/phone-number",
            headers={"Authorization": f"Bearer {s.vapi_api_key}"},
        )
        ok = r.status_code == 200
        detail = f"HTTP {r.status_code}"
        if ok:
            phones = r.json()
            match = any(p.get("number") == s.vapi_phone_number for p in phones)
            detail += f", phones={len(phones)}, env_number_matched={match}"
        results.append(("Vapi", ok, detail))

    # Neon
    try:
        from sqlalchemy import create_engine, text

        from app.config import sqlalchemy_url

        eng = create_engine(sqlalchemy_url(s.database_url), pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        results.append(("Neon", True, "SELECT 1 ok"))
    except Exception as exc:  # noqa: BLE001
        results.append(("Neon", False, str(exc)[:120]))

    print(json.dumps([{"service": a, "ok": b, "detail": c} for a, b, c in results], indent=2))
    return 0 if all(b for _, b, _ in results if _[0] in ("Vapi", "Neon")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
