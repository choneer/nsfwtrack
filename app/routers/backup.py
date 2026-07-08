from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.database import get_db
from app.services.backup import restore_backup_data
from app.services.exporter import (
    export_backup_json,
    export_items_csv,
    timestamp_for_filename,
)

router = APIRouter(
    prefix="/api/backup",
    tags=["backup"],
    dependencies=[Depends(require_api_auth)],
)


def _attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get("/export/json")
def export_json_endpoint(db: Session = Depends(get_db)) -> Response:
    filename = f"nsfwtrack-backup-{timestamp_for_filename()}.json"
    return Response(
        content=export_backup_json(db),
        media_type="application/json",
        headers=_attachment_headers(filename),
    )


@router.get("/export/csv")
def export_csv_endpoint(db: Session = Depends(get_db)) -> Response:
    filename = f"nsfwtrack-items-{timestamp_for_filename()}.csv"
    return Response(
        content=export_items_csv(db),
        media_type="text/csv; charset=utf-8",
        headers=_attachment_headers(filename),
    )


@router.post("/restore/json")
async def restore_json_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON backup required",
        )
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Backup root must be an object")
        result = restore_backup_data(db, payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"ok": True, "result": result}
