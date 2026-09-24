from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import err, ok

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return ok({"status": "ok", "database": "up"})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content=err("unhealthy", f"database check failed: {exc}"),
        )
