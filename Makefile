.PHONY: dev test migrate seed setup-vapi lint verify-keys

dev:
	. .venv/bin/activate && PYTHONPATH=. uvicorn app.main:app --reload --port 8000

test:
	. .venv/bin/activate && PYTHONPATH=. pytest -q

migrate:
	. .venv/bin/activate && PYTHONPATH=. alembic upgrade head

seed:
	. .venv/bin/activate && PYTHONPATH=. python scripts/seed.py

setup-vapi:
	. .venv/bin/activate && PYTHONPATH=. python scripts/setup_vapi.py

verify-keys:
	. .venv/bin/activate && PYTHONPATH=. python scripts/verify_keys.py

lint:
	. .venv/bin/activate && ruff check app scripts tests --config ruff.toml
