from __future__ import annotations

import os
import stat
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.services import local_media


MediaSeverity = Literal["problem", "warning"]


@dataclass(frozen=True)
class MediaHealthFinding:
    code: str
    severity: MediaSeverity
    object_type: str
    object_id: str
    detail: str = ""


@dataclass(frozen=True)
class _MediaReference:
    object_type: str
    object_id: str
    value: str


def _finding(
    code: str,
    object_type: str,
    object_id: str,
    *,
    detail: str = "",
    severity: MediaSeverity = "problem",
) -> MediaHealthFinding:
    return MediaHealthFinding(
        code=code,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        detail=detail,
    )


def _short(value: str, *, limit: int = 180) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."


def _load_media_references(db: Session) -> list[_MediaReference]:
    try:
        rows = db.execute(
            text(
                """
                SELECT 'item_cover' AS object_type, id AS object_id, cover_path AS value
                FROM items
                WHERE cover_path IS NOT NULL
                UNION ALL
                SELECT 'creator_avatar' AS object_type, id AS object_id, avatar_path AS value
                FROM creators
                WHERE avatar_path IS NOT NULL
                ORDER BY object_type ASC, object_id ASC
                """
            )
        ).mappings()
        return [
            _MediaReference(
                object_type=str(row["object_type"]),
                object_id=str(row["object_id"]),
                value=str(row["value"]),
            )
            for row in rows
        ]
    except OperationalError:
        # Older audit fixtures may predate the local-media columns.
        return []


def _looks_like_escape(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned.startswith(local_media.LOCAL_MEDIA_PREFIX):
        return False
    relative = cleaned.removeprefix(local_media.LOCAL_MEDIA_PREFIX)
    return any(segment == ".." for segment in relative.replace("\\", "/").split("/"))


def _normalize_references(
    references: list[_MediaReference],
) -> tuple[list[tuple[_MediaReference, str]], list[MediaHealthFinding]]:
    valid: list[tuple[_MediaReference, str]] = []
    findings: list[MediaHealthFinding] = []
    for reference in references:
        if _looks_like_escape(reference.value):
            findings.append(
                _finding(
                    "media_reference_path_escape",
                    reference.object_type,
                    reference.object_id,
                    detail=_short(reference.value),
                )
            )
            continue
        try:
            normalized = local_media.normalize_local_media_path(reference.value)
        except local_media.LocalMediaPathError:
            normalized = None
        if normalized is None:
            findings.append(
                _finding(
                    "media_reference_invalid_path",
                    reference.object_type,
                    reference.object_id,
                    detail=_short(reference.value),
                )
            )
            continue
        valid.append((reference, normalized))
    return valid, findings


def _root_state(root: Path, *, has_references: bool) -> str | None:
    try:
        root_stat = root.lstat()
    except FileNotFoundError:
        return "missing" if has_references else None
    except OSError:
        return "unreadable"
    if stat.S_ISLNK(root_stat.st_mode):
        return "symlink"
    if not stat.S_ISDIR(root_stat.st_mode):
        return "not_directory"
    try:
        with os.scandir(root):
            pass
    except OSError:
        return "unreadable"
    return "ready"


def _classify_unscanned_reference(root: Path, media_path: str) -> str:
    candidate = root
    segments = media_path.removeprefix(local_media.LOCAL_MEDIA_PREFIX).split("/")
    for index, segment in enumerate(segments):
        candidate = candidate / segment
        try:
            candidate_stat = candidate.lstat()
        except FileNotFoundError:
            return "media_reference_missing"
        except OSError:
            return "media_reference_damaged"
        if stat.S_ISLNK(candidate_stat.st_mode):
            return "media_reference_symlink"
        if index < len(segments) - 1 and not stat.S_ISDIR(candidate_stat.st_mode):
            return "media_reference_damaged"
        if index == len(segments) - 1 and not stat.S_ISREG(candidate_stat.st_mode):
            return "media_reference_damaged"
    return "media_reference_damaged"


def _find_upload_residues(root: Path) -> list[tuple[str, int]]:
    residues: list[tuple[str, int]] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif (
                    entry.is_file(follow_symlinks=False)
                    and local_media.is_upload_residue_filename(entry.name)
                ):
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    residues.append((relative, entry.stat(follow_symlinks=False).st_size))
            except (OSError, ValueError):
                continue
    residues.sort(key=lambda row: row[0].casefold())
    return residues


def audit_local_media(db: Session) -> list[MediaHealthFinding]:
    references = _load_media_references(db)
    valid_references, findings = _normalize_references(references)
    root = local_media.LOCAL_MEDIA_ROOT
    root_state = _root_state(root, has_references=bool(valid_references))
    if root_state is None:
        return findings
    if root_state != "ready":
        findings.insert(
            0,
            _finding(
                "media_root_unavailable",
                "media_root",
                "media-root",
                detail=root_state,
            ),
        )
        reference_code = {
            "missing": "media_reference_missing",
            "symlink": "media_reference_symlink",
        }.get(root_state, "media_reference_damaged")
        findings.extend(
            _finding(
                reference_code,
                reference.object_type,
                reference.object_id,
                detail=_short(media_path),
            )
            for reference, media_path in valid_references
        )
        return findings

    try:
        scan = local_media.scan_local_media()
        recovery_scan = local_media.scan_local_media(include_cleanup_anchors=True)
    except (local_media.LocalMediaPathError, OSError):
        findings.insert(
            0,
            _finding(
                "media_root_unavailable",
                "media_root",
                "media-root",
                detail="scan_failed",
            ),
        )
        findings.extend(
            _finding(
                _classify_unscanned_reference(root, media_path),
                reference.object_type,
                reference.object_id,
                detail=_short(media_path),
            )
            for reference, media_path in valid_references
        )
        return findings

    entries_by_path = {entry.media_path: entry for entry in recovery_scan.entries}
    references_by_path: dict[str, list[_MediaReference]] = defaultdict(list)
    for reference, media_path in valid_references:
        references_by_path[media_path].append(reference)
    for reference, media_path in valid_references:
        entry = entries_by_path.get(media_path)
        if entry is not None:
            if not entry.available:
                findings.append(
                    _finding(
                        "media_reference_damaged",
                        reference.object_type,
                        reference.object_id,
                        detail=_short(media_path),
                    )
                )
            continue
        findings.append(
            _finding(
                _classify_unscanned_reference(root, media_path),
                reference.object_type,
                reference.object_id,
                detail=_short(media_path),
            )
        )

    for entry in recovery_scan.entries:
        if not entry.is_cleanup_anchor:
            continue
        reference_count = len(references_by_path.get(entry.media_path, ()))
        if not entry.available:
            code = "media_cleanup_anchor_damaged"
            severity: MediaSeverity = "problem"
        elif reference_count:
            code = "media_cleanup_anchor_referenced"
            severity = "warning"
        else:
            code = "media_cleanup_anchor_unreferenced"
            severity = "warning"
        findings.append(
            _finding(
                code,
                "media_cleanup_anchor",
                entry.media_path,
                detail=f"references={reference_count} path={_short(entry.media_path)}",
                severity=severity,
            )
        )

    for relative_path, size in _find_upload_residues(root):
        findings.append(
            _finding(
                "media_upload_residue",
                "media_file",
                relative_path,
                detail=f"size={size}",
                severity="warning",
            )
        )

    for entry in scan.entries:
        if entry.available or not entry.sha256 or entry.is_cleanup_anchor:
            continue
        reference_count = len(references_by_path.get(entry.media_path, ()))
        findings.append(
            _finding(
                "media_damaged_file",
                "media_file",
                entry.media_path,
                detail=(
                    f"sha256={entry.sha256} size={entry.size} "
                    f"references={reference_count}"
                ),
            )
        )

    paths_by_hash: dict[str, list[str]] = defaultdict(list)
    for entry in scan.entries:
        if entry.available and entry.sha256:
            paths_by_hash[entry.sha256].append(entry.media_path)
    for digest in sorted(paths_by_hash):
        paths = sorted(paths_by_hash[digest], key=str.casefold)
        if len(paths) > 1:
            findings.append(
                _finding(
                    "media_duplicate_content",
                    "media_content",
                    digest,
                    detail=_short(f"count={len(paths)} paths={','.join(paths)}"),
                    severity="warning",
                )
            )

    if scan.skipped_symlinks:
        findings.append(
            _finding(
                "media_scan_skipped_symlinks",
                "media_scan",
                "scan",
                detail=f"count={scan.skipped_symlinks}",
                severity="warning",
            )
        )
    if scan.skipped_unsupported:
        findings.append(
            _finding(
                "media_scan_skipped_unsupported",
                "media_scan",
                "scan",
                detail=f"count={scan.skipped_unsupported}",
                severity="warning",
            )
        )
    return findings
