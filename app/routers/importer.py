from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.database import get_db
from app.services.importer import (
    CSV_TEMPLATE_FILENAME,
    JSON_TEMPLATE_FILENAME,
    ImportDataError,
    csv_template_content,
    import_csv,
    import_json,
    json_template_content,
    read_import_upload,
)

router = APIRouter(
    prefix="/api/import",
    tags=["import"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("/template/csv")
def csv_template_endpoint() -> Response:
    return Response(
        content=csv_template_content(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{CSV_TEMPLATE_FILENAME}"'
        },
    )


@router.get("/template/json")
def json_template_endpoint() -> Response:
    return Response(
        content=json_template_content(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{JSON_TEMPLATE_FILENAME}"'
        },
    )


@router.post("/csv")
async def import_csv_endpoint(
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_file")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported_file_type",
        )
    try:
        return import_csv(db, await read_import_upload(file))
    except ImportDataError as exc:
        status_code = (
            status.HTTP_413_CONTENT_TOO_LARGE
            if exc.code == "file_too_large"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=exc.code) from exc


@router.post("/json")
async def import_json_endpoint(
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_file")
    if not (file.filename or "").lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported_file_type",
        )
    try:
        return import_json(db, await read_import_upload(file))
    except ImportDataError as exc:
        status_code = (
            status.HTTP_413_CONTENT_TOO_LARGE
            if exc.code == "file_too_large"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=exc.code) from exc
