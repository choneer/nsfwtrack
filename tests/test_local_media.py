from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Collection, Creator, Item, Tag
from app.services import local_media
from app.services.backup_validator import validate_backup_payload
from app.services.settings import save_app_settings


INVALID_MEDIA_PATHS = [
    "https://example.invalid/cover.jpg",
    "//example.invalid/cover.jpg",
    "data:image/png;base64,AAAA",
    "/covers/cover.jpg",
    "/media/../cover.jpg",
    "/media/covers\\cover.jpg",
    "/media/covers%2Fcover.jpg",
    "/media/cover.svg",
    "/media/cover.jpg?source=remote",
]


def _png_bytes(red: int = 0) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(bytes((0, red, 0, 0)))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


GIF_BYTES = b"GIF89a\x01\x00\x01\x00;"


@pytest.mark.parametrize("path", INVALID_MEDIA_PATHS)
def test_item_api_rejects_non_local_cover_paths_without_writing(
    auth_client: TestClient,
    path: str,
) -> None:
    response = auth_client.post(
        "/api/items",
        json={"title": "Rejected Cover", "cover_path": path},
    )

    assert response.status_code == 422
    assert auth_client.get("/api/items").json()["total"] == 0


@pytest.mark.parametrize("path", INVALID_MEDIA_PATHS)
def test_creator_api_rejects_non_local_avatar_paths_without_writing(
    auth_client: TestClient,
    path: str,
) -> None:
    response = auth_client.post(
        "/api/creators",
        json={"name": "Rejected Avatar", "avatar_path": path},
    )

    assert response.status_code == 422
    assert auth_client.get("/api/creators").json() == []


def test_page_forms_reject_external_media_paths(auth_client: TestClient) -> None:
    item_response = auth_client.post(
        "/items",
        data={"title": "Page Cover", "cover_path": "https://example.invalid/a.jpg"},
        follow_redirects=True,
    )
    creator_response = auth_client.post(
        "/creators",
        data={
            "name": "Page Avatar",
            "type_value": "other",
            "avatar_path": "//example.invalid/a.jpg",
        },
        follow_redirects=True,
    )

    assert item_response.status_code == 200
    assert creator_response.status_code == 200
    with SessionLocal() as db:
        assert db.query(Item).count() == 0
        assert db.query(Creator).count() == 0


def test_valid_local_cover_renders_and_is_served_only_after_login(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    cover = media_root / "covers" / "sample.png"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(_png_bytes())
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    created = auth_client.post(
        "/api/items",
        json={"title": "Local Cover", "cover_path": "/media/covers/sample.png"},
    )
    item_id = created.json()["id"]
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        assert item is not None
        collection = Collection(name="Local Media Collection")
        collection.items.append(item)
        db.add(collection)
        db.commit()
        collection_id = collection.id
    list_response = auth_client.get("/items")
    detail_response = auth_client.get(f"/items/{item_id}")
    collection_response = auth_client.get(f"/collections/{collection_id}")
    file_response = auth_client.get("/media/covers/sample.png")

    assert created.status_code == 201
    assert 'src="/media/covers/sample.png"' in list_response.text
    assert 'src="/media/covers/sample.png"' in detail_response.text
    assert 'src="/media/covers/sample.png"' in collection_response.text
    assert file_response.status_code == 200
    assert file_response.content == _png_bytes()
    auth_client.cookies.clear()
    unauthenticated = auth_client.get(
        "/media/covers/sample.png",
        follow_redirects=False,
    )
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/login"


def test_legacy_external_cover_is_not_rendered(auth_client: TestClient) -> None:
    external_url = "https://example.invalid/legacy.png"
    with SessionLocal() as db:
        item = Item(title="Legacy Cover", cover_path=external_url)
        collection = Collection(name="Legacy Cover Collection")
        collection.items.append(item)
        db.add_all([item, collection])
        db.commit()
        item_id = item.id
        collection_id = collection.id

    list_response = auth_client.get("/items")
    detail_response = auth_client.get(f"/items/{item_id}")
    collection_response = auth_client.get(f"/collections/{collection_id}")

    assert external_url not in list_response.text
    assert external_url not in detail_response.text
    assert external_url not in collection_response.text


@pytest.mark.parametrize(
    ("table_name", "field_name", "row"),
    [
        (
            "items",
            "cover_path",
            {"id": 101, "title": "Backup Item", "cover_path": "https://example.invalid/a.jpg"},
        ),
        (
            "creators",
            "avatar_path",
            {"id": 102, "name": "Backup Creator", "avatar_path": "//example.invalid/a.jpg"},
        ),
    ],
)
def test_backup_preview_and_restore_reject_invalid_media_without_partial_write(
    auth_client: TestClient,
    table_name: str,
    field_name: str,
    row: dict[str, object],
) -> None:
    payload = auth_client.get("/api/backup/export/json").json()
    payload["tables"][table_name].append(row)
    payload["tables"]["tags"].append({"id": 103, "name": "Must Not Restore"})
    report = validate_backup_payload(payload).to_dict()
    upload = {
        "file": (
            "backup.json",
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )
    }

    preview_response = auth_client.post("/api/backup/preview/json", files=upload)
    restore_response = auth_client.post(
        "/api/backup/restore/json",
        data={"confirm": "1"},
        files=upload,
    )

    assert report["status"] == "blocked"
    assert any(
        issue["code"] == "invalid_local_media_path"
        and issue["detail"] == field_name
        for issue in report["issues"]
    )
    assert preview_response.status_code == 400
    assert restore_response.status_code == 400
    with SessionLocal() as db:
        assert db.query(Item).count() == 0
        assert db.query(Creator).count() == 0
        assert db.query(Tag).filter(Tag.name == "Must Not Restore").count() == 0


def test_media_library_and_write_routes_require_login_and_post(
    client: TestClient,
) -> None:
    assert client.get("/media-library", follow_redirects=False).status_code == 303
    for path in (
        "/media-library/upload",
        "/media-library/set-item-cover",
        "/media-library/set-creator-avatar",
        "/items/1/cover/clear",
        "/creators/1/avatar/clear",
    ):
        assert client.post(path, follow_redirects=False).status_code == 303
        assert client.get(path).status_code == 405


def test_media_library_renders_english_safety_and_validation_copy(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", tmp_path / "media")
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library"},
    )

    page = auth_client.get("/media-library")
    rejected = auth_client.post(
        "/media-library/upload",
        files={"files": ("fake.png", b"<html>fake</html>", "image/png")},
        follow_redirects=True,
    )

    assert "Local Media Library" in page.text
    assert "SHA-256 deduplication" in page.text
    assert "Symlinks are not followed" in page.text
    assert "file header is not a valid raster image" in rejected.text


def test_scan_skips_symlinks_and_reports_invalid_or_unsupported_files(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes())
    (media_root / "valid.png").write_bytes(_png_bytes(1))
    (media_root / "corrupt.png").write_bytes(b"<html>not an image</html>")
    (media_root / "ignored.html").write_text("<html></html>")
    (media_root / "outside-link.png").symlink_to(outside)
    (media_root / "inside-link.png").symlink_to(media_root / "valid.png")
    (media_root / "directory-link").symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    scan = local_media.scan_local_media()

    assert [entry.filename for entry in scan.entries] == ["corrupt.png", "valid.png"]
    assert scan.entries[0].available is False
    assert scan.entries[1].available is True
    assert scan.invalid == 1
    assert scan.skipped_symlinks == 3
    assert scan.skipped_unsupported == 1
    for path in ("outside-link.png", "inside-link.png"):
        with pytest.raises(local_media.LocalMediaPathError):
            local_media.resolve_local_media_file(path)
    response = auth_client.get("/media-library")
    assert response.status_code == 200
    assert "损坏或伪装" in response.text
    assert "outside-link.png" not in response.text


def test_scan_accepts_every_approved_raster_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    samples = {
        "image.png": _png_bytes(),
        "image.jpg": b"\xff\xd8\xff\xe0local-jpeg\xff\xd9",
        "image.jpeg": b"\xff\xd8\xff\xe1local-jpeg\xff\xd9",
        "image.gif": GIF_BYTES,
        "image.webp": b"RIFF\x08\x00\x00\x00WEBPVP8X",
        "image.avif": b"\x00\x00\x00\x14ftypavif\x00\x00\x00\x00avif",
    }
    for filename, content in samples.items():
        (media_root / filename).write_bytes(content)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    scan = local_media.scan_local_media()

    assert len(scan.entries) == len(samples)
    assert all(entry.available for entry in scan.entries)
    assert scan.invalid == 0


def test_multi_upload_uses_sha256_deduplication(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    first = _png_bytes()
    response = auth_client.post(
        "/media-library/upload",
        files=[
            ("files", ("first.png", first, "image/png")),
            ("files", ("same.png", first, "image/png")),
            ("files", ("other.gif", GIF_BYTES, "image/gif")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "新增 2，重复 1" in response.text
    scan = local_media.scan_local_media()
    assert len(scan.entries) == 2
    assert all(entry.filename.startswith("library/") for entry in scan.entries)
    assert len({entry.sha256 for entry in scan.entries}) == 2

    second = auth_client.post(
        "/media-library/upload",
        files={"files": ("renamed.png", first, "image/png")},
        follow_redirects=True,
    )
    assert "新增 0，重复 1" in second.text
    assert len(local_media.scan_local_media().entries) == 2


def test_upload_flushes_and_fsyncs_random_temp_before_atomic_publish(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    content = _png_bytes()
    events: list[str] = []
    original_open = local_media._open_temporary_stream
    original_publish = local_media._atomic_publish

    class RecordingStream:
        def __init__(self, raw: object) -> None:
            self.raw = raw

        def write(self, value: bytes) -> int:
            events.append("write")
            return self.raw.write(value)

        def flush(self) -> None:
            events.append("flush")
            self.raw.flush()

        def fileno(self) -> int:
            return self.raw.fileno()

        def close(self) -> None:
            events.append("close")
            self.raw.close()

    def open_recording(file_descriptor: int) -> RecordingStream:
        return RecordingStream(original_open(file_descriptor))

    def sync_recording(stream: object) -> None:
        stream.flush()
        events.append("fsync")
        local_media.os.fsync(stream.fileno())

    def publish_recording(temporary: Path, target: Path) -> None:
        events.append("publish")
        assert temporary.parent == media_root / "library"
        assert temporary.name.startswith(".upload-")
        assert temporary.suffix == ".tmp"
        assert temporary.read_bytes() == content
        assert not target.exists()
        original_publish(temporary, target)

    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(local_media, "_open_temporary_stream", open_recording)
    monkeypatch.setattr(local_media, "_sync_temporary_stream", sync_recording)
    monkeypatch.setattr(local_media, "_atomic_publish", publish_recording)

    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("atomic.png", content, "image/png")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "新增 1，重复 0" in response.text
    assert events == ["write", "flush", "fsync", "close", "publish"]
    assert not list((media_root / "library").glob(".upload-*.tmp"))


def test_interrupted_write_removes_temporary_and_final_files(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    original_open = local_media._open_temporary_stream

    class InterruptedStream:
        def __init__(self, raw: object) -> None:
            self.raw = raw

        def write(self, value: bytes) -> int:
            self.raw.write(value[:8])
            raise OSError("simulated interrupted write")

        def close(self) -> None:
            self.raw.close()

    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(
        local_media,
        "_open_temporary_stream",
        lambda file_descriptor: InterruptedStream(original_open(file_descriptor)),
    )

    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("interrupted.png", _png_bytes(), "image/png")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "媒体目录不可安全写入" in response.text
    assert list((media_root / "library").iterdir()) == []


def test_close_failure_removes_fsynced_temporary_file(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    original_open = local_media._open_temporary_stream

    class CloseFailingStream:
        def __init__(self, raw: object) -> None:
            self.raw = raw

        def write(self, value: bytes) -> int:
            return self.raw.write(value)

        def flush(self) -> None:
            self.raw.flush()

        def fileno(self) -> int:
            return self.raw.fileno()

        def close(self) -> None:
            self.raw.close()
            raise OSError("simulated close failure")

    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(
        local_media,
        "_open_temporary_stream",
        lambda file_descriptor: CloseFailingStream(original_open(file_descriptor)),
    )

    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("close-failure.png", _png_bytes(), "image/png")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "媒体目录不可安全写入" in response.text
    assert list((media_root / "library").iterdir()) == []


def test_batch_mid_write_failure_rolls_back_prior_published_file(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    original_open = local_media._open_temporary_stream
    opened = 0

    class InterruptedStream:
        def __init__(self, raw: object) -> None:
            self.raw = raw

        def write(self, value: bytes) -> int:
            self.raw.write(value[:8])
            raise OSError("simulated second-file interruption")

        def close(self) -> None:
            self.raw.close()

    def fail_second_open(file_descriptor: int) -> object:
        nonlocal opened
        opened += 1
        raw = original_open(file_descriptor)
        return raw if opened == 1 else InterruptedStream(raw)

    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(local_media, "_open_temporary_stream", fail_second_open)

    response = auth_client.post(
        "/media-library/upload",
        files=[
            ("files", ("first.png", _png_bytes(21), "image/png")),
            ("files", ("second.png", _png_bytes(22), "image/png")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "媒体目录不可安全写入" in response.text
    assert opened == 2
    assert list((media_root / "library").iterdir()) == []


def test_failure_after_atomic_publish_removes_new_final_file(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"

    def fail_directory_sync(directory: Path) -> None:
        del directory
        raise local_media.LocalMediaUploadError("storage_unavailable")

    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(local_media, "_fsync_directory", fail_directory_sync)

    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("post-publish.png", _png_bytes(24), "image/png")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "媒体目录不可安全写入" in response.text
    assert list((media_root / "library").iterdir()) == []


def test_raced_existing_final_is_revalidated_and_reported_as_duplicate(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    library = media_root / "library"
    library.mkdir(parents=True)
    content = _png_bytes(23)
    digest = hashlib.sha256(content).hexdigest()
    target = library / f"{digest}.png"
    target.write_bytes(content)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(
        local_media,
        "scan_local_media",
        lambda: local_media.LocalMediaScan((), 0, 0, 0),
    )

    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("raced.png", content, "image/png")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "新增 0，重复 1" in response.text
    assert target.read_bytes() == content
    assert list(library.iterdir()) == [target]


@pytest.mark.parametrize(
    ("filename", "content", "mime", "message"),
    [
        ("fake.png", b"<html>fake</html>", "image/png", "文件头不是有效"),
        ("vector.svg", b"<svg></svg>", "image/svg+xml", "只允许 AVIF"),
        ("fake.jpg", _png_bytes(), "image/jpeg", "文件头不是有效"),
        ("mime.png", _png_bytes(), "text/html", "MIME 类型"),
    ],
)
def test_upload_rejects_disguised_unsupported_and_mime_mismatched_files(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    filename: str,
    content: bytes,
    mime: str,
    message: str,
) -> None:
    media_root = tmp_path / "media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    response = auth_client.post(
        "/media-library/upload",
        files={"files": (filename, content, mime)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert message in response.text
    assert local_media.scan_local_media().entries == ()


def test_upload_enforces_per_file_size_and_batch_count_limits(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(local_media, "MAX_MEDIA_UPLOAD_BYTES", len(_png_bytes()) - 1)
    too_large = auth_client.post(
        "/media-library/upload",
        files={"files": ("large.png", _png_bytes(), "image/png")},
        follow_redirects=True,
    )
    assert "超过单文件大小限制" in too_large.text
    assert not media_root.exists()

    monkeypatch.setattr(local_media, "MAX_MEDIA_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(local_media, "MAX_MEDIA_UPLOAD_FILES", 1)
    too_many = auth_client.post(
        "/media-library/upload",
        files=[
            ("files", ("one.png", _png_bytes(), "image/png")),
            ("files", ("two.png", _png_bytes(2), "image/png")),
        ],
        follow_redirects=True,
    )
    assert "图片数量超过限制" in too_many.text
    assert not media_root.exists()


def test_upload_never_follows_a_preexisting_target_symlink(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    library = media_root / "library"
    library.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside-must-not-change")
    content = _png_bytes()
    target = library / f"{hashlib.sha256(content).hexdigest()}.png"
    target.symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("safe.png", content, "image/png")},
        follow_redirects=True,
    )

    assert "媒体目录不可安全写入" in response.text
    assert outside.read_bytes() == b"outside-must-not-change"
    assert target.is_symlink()


def test_symlinked_media_root_is_not_scanned_or_written(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    media_root = tmp_path / "media"
    media_root.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    page = auth_client.get("/media-library")
    upload = auth_client.post(
        "/media-library/upload",
        files={"files": ("safe.png", _png_bytes(), "image/png")},
        follow_redirects=True,
    )

    assert page.status_code == 200
    assert "媒体目录不可用" in page.text
    assert upload.status_code == 200
    assert "媒体目录不可安全写入" in upload.text
    assert list(outside.iterdir()) == []


def test_set_replace_and_clear_cover_and_avatar_without_deleting_files(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    auth_client.post(
        "/media-library/upload",
        files=[
            ("files", ("first.png", _png_bytes(), "image/png")),
            ("files", ("second.png", _png_bytes(3), "image/png")),
        ],
    )
    paths = [entry.media_path for entry in local_media.scan_local_media().entries]
    item_id = auth_client.post(
        "/api/items", json={"title": "Media Item"}
    ).json()["id"]
    creator_id = auth_client.post(
        "/api/creators", json={"name": "Media Creator", "type": "person"}
    ).json()["id"]

    for media_path in paths:
        cover_response = auth_client.post(
            "/media-library/set-item-cover",
            data={"item_id": item_id, "media_path": media_path},
            follow_redirects=True,
        )
        assert "封面已设置或替换" in cover_response.text
    avatar_response = auth_client.post(
        "/media-library/set-creator-avatar",
        data={"creator_id": creator_id, "media_path": paths[0]},
        follow_redirects=True,
    )
    assert "头像已设置或替换" in avatar_response.text
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == paths[-1]
        assert db.get(Creator, creator_id).avatar_path == paths[0]

    library = auth_client.get("/media-library")
    assert "条目封面：Media Item" in library.text
    assert "创作者头像：Media Creator" in library.text
    assert f'src="{paths[-1]}"' in auth_client.get(f"/items/{item_id}").text
    assert f'src="{paths[0]}"' in auth_client.get(f"/creators/{creator_id}").text

    auth_client.post(f"/items/{item_id}/cover/clear")
    auth_client.post(f"/creators/{creator_id}/avatar/clear")
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == paths[-1]
        assert db.get(Creator, creator_id).avatar_path == paths[0]
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    auth_client.post(
        f"/items/{item_id}/cover/clear",
        data={"confirm": "1"},
    )
    auth_client.post(
        f"/creators/{creator_id}/avatar/clear",
        data={"confirm": "1"},
    )
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == paths[-1]
        assert db.get(Creator, creator_id).avatar_path == paths[0]

    clear_cover = auth_client.post(
        f"/items/{item_id}/cover/clear",
        data={"confirm": "1", "confirmation_text": "CONFIRM"},
        follow_redirects=True,
    )
    clear_avatar = auth_client.post(
        f"/creators/{creator_id}/avatar/clear",
        data={"confirm": "1", "confirmation_text": "CONFIRM"},
        follow_redirects=True,
    )
    assert "媒体文件仍保留" in clear_cover.text
    assert "媒体文件仍保留" in clear_avatar.text
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path is None
        assert db.get(Creator, creator_id).avatar_path is None
    assert all(
        (media_root / path.removeprefix("/media/")).is_file() for path in paths
    )


def test_missing_or_corrupt_assigned_media_degrades_without_500(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "corrupt.png").write_bytes(b"<html>not a png</html>")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        item = Item(title="Broken Cover", cover_path="/media/corrupt.png")
        creator = Creator(
            name="Missing Avatar",
            type="person",
            avatar_path="/media/missing.png",
        )
        db.add_all([item, creator])
        db.commit()
        item_id = item.id
        creator_id = creator.id

    item_page = auth_client.get(f"/items/{item_id}")
    creator_page = auth_client.get(f"/creators/{creator_id}")
    corrupt_file = auth_client.get("/media/corrupt.png")
    missing_file = auth_client.get("/media/missing.png")
    library = auth_client.get("/media-library")

    assert item_page.status_code == 200
    assert creator_page.status_code == 200
    assert 'src="/media/corrupt.png"' not in item_page.text
    assert 'src="/media/missing.png"' not in creator_page.text
    assert corrupt_file.status_code == 404
    assert missing_file.status_code == 404
    assert library.status_code == 200
    assert "图片不可用" in library.text
