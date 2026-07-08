from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.database import get_db
from app.services.stats import created_timeline, stats_summary_payload

router = APIRouter(
    prefix="/api/stats",
    tags=["stats"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("/summary")
def stats_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    return stats_summary_payload(db)


@router.get("/timeline")
def stats_timeline(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return created_timeline(db)
