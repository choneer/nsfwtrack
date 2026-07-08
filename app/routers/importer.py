from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.database import get_db
from app.services.importer import import_csv, import_json

router = APIRouter(
    prefix="/api/import",
    tags=["import"],
    dependencies=[Depends(require_api_auth)],
)


@router.post("/csv")
async def import_csv_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV required")
    return import_csv(db, await file.read())


@router.post("/json")
async def import_json_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON required")
    return import_json(db, await file.read())
