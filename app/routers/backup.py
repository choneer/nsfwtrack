from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.config import get_settings
from app.database import get_db
from app.i18n import get_language, translate
from app.services.backup import BackupError, preview_backup_data, restore_backup_data
from app.services.backup_validator import validate_backup_payload
from app.services.danger import (
    DangerConfirmationError,
    get_danger_policy,
    require_danger_confirmation,
)
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


def _localized_error(request: Request, code: str) -> str:
    return translate(get_language(request), f"backup.error_{code}")


async def _read_backup_upload(request: Request, file: UploadFile | None) -> dict[str, object]:
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_localized_error(request, "missing_file"),
        )
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_localized_error(request, "json_required"),
        )
    max_bytes = get_settings().max_backup_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_localized_error(request, "too_large"),
        )
    try:
        payload = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_localized_error(request, "invalid_json"),
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_localized_error(request, "invalid_backup"),
        )
    return payload


def _handle_backup_error(request: Request, exc: Exception) -> HTTPException:
    if isinstance(exc, BackupError):
        message = _localized_error(request, exc.code)
        if exc.detail:
            message = f"{message} ({exc.detail})"
    else:
        message = _localized_error(request, "restore_failed")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


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


@router.post("/preview/json")
async def preview_json_endpoint(
    request: Request,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    payload = await _read_backup_upload(request, file)
    try:
        preview = preview_backup_data(payload, db)
    except BackupError as exc:
        raise _handle_backup_error(request, exc) from exc
    return {
        "ok": True,
        "preview": preview,
        "report": validate_backup_payload(payload, db).to_dict(),
    }


@router.post("/restore/json")
async def restore_json_endpoint(
    request: Request,
    file: UploadFile | None = File(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    danger_policy = get_danger_policy(db)
    db.rollback()
    try:
        require_danger_confirmation(
            danger_policy,
            confirmation_text=confirmation_text,
            base_confirmation_valid=confirm == "1",
        )
    except DangerConfirmationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate(get_language(request), f"danger.error_{exc.code}"),
        ) from exc
    payload = await _read_backup_upload(request, file)
    try:
        preview_backup_data(payload)
        result = restore_backup_data(db, payload)
    except (BackupError, ValueError) as exc:
        raise _handle_backup_error(request, exc) from exc
    return {"ok": True, "result": result}
