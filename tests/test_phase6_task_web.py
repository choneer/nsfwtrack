from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Item, ItemSource, OperationTask
from app.routers.source_search import get_provider_search_service
from app.tasks import PersistentTaskService, TaskState, TaskType
from tests.test_phase5_n5b import PROVIDER_KEY, _service


def _item_source() -> tuple[int, int]:
    with SessionLocal() as db:
        item = Item(title="Task UI item", summary="Old summary")
        db.add(item)
        db.flush()
        source = ItemSource(
            item_id=item.id,
            url="https://metadata.invalid/canonical-marker",
            normalized_url="https://metadata.invalid/canonical-marker",
            title="Source title",
            provider_key=PROVIDER_KEY,
            external_id="video-001",
        )
        db.add(source)
        db.commit()
        return item.id, source.id


@pytest.fixture
def source_service_override() -> Generator[object, None, None]:
    service, adapter = _service()
    app.dependency_overrides[get_provider_search_service] = lambda: service
    try:
        yield adapter
    finally:
        app.dependency_overrides.pop(get_provider_search_service, None)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/tasks"),
        ("get", "/tasks/1"),
        ("post", "/tasks/1/start"),
        ("post", "/tasks/1/pause"),
        ("post", "/tasks/1/resume"),
        ("post", "/tasks/1/cancel"),
        ("post", "/tasks/1/retry"),
        ("post", "/tasks/1/delete-history"),
    ],
)
def test_task_routes_require_authentication(client: TestClient, method: str, path: str) -> None:
    response = getattr(client, method)(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_task_get_pages_are_read_only_and_do_not_expose_external_identity_or_path(
    auth_client: TestClient,
) -> None:
    item_id, source_id = _item_source()
    with SessionLocal() as db:
        service = PersistentTaskService(db, max_concurrency=2)
        task, _ = service.create(
            task_type=TaskType.ASSET_DOWNLOAD,
            intent_key="web:safe-detail",
            initial_state=TaskState.QUEUED,
            item_id=item_id,
            source_id=source_id,
            provider_key=PROVIDER_KEY,
            external_identity="video-001",
            asset_identity="asset-secret-identity",
            relative_target="private/directory/secret-file.png",
        )
        db.commit()
        task_id = task.id
        before = db.query(OperationTask).count()

    listing = auth_client.get("/tasks")
    detail = auth_client.get(f"/tasks/{task_id}")

    assert listing.status_code == detail.status_code == 200
    assert "任务中心" in listing.text
    assert "video-001" not in detail.text
    assert "asset-secret-identity" not in detail.text
    assert "private/directory/secret-file.png" not in detail.text
    assert "https://metadata.invalid" not in detail.text
    with SessionLocal() as db:
        assert db.query(OperationTask).count() == before
        assert db.get(OperationTask, task_id).state == TaskState.QUEUED.value


def test_manual_check_prg_diff_preview_is_no_store_and_confirm_has_no_provider_call(
    auth_client: TestClient,
    source_service_override: object,
) -> None:
    adapter = source_service_override
    item_id, source_id = _item_source()
    checked = auth_client.post(
        f"/items/{item_id}/sources/{source_id}/check",
        follow_redirects=False,
    )
    assert checked.status_code == 303
    task_path = checked.headers["location"]
    assert task_path.startswith("/tasks/")
    detail = auth_client.get(task_path)
    assert detail.status_code == 200
    assert "来源差异" in detail.text
    task_id = int(task_path.rsplit("/", 1)[1])
    preview = auth_client.post(
        f"/tasks/{task_id}/update-preview",
        data={"selected_fields": "item.summary"},
    )
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "no-store"
    assert "更新确认预览" in preview.text
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}


def test_task_center_is_bilingual_and_navigation_is_present(auth_client: TestClient) -> None:
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/tasks"},
    )
    response = auth_client.get("/tasks")
    assert response.status_code == 200
    assert "Task Center" in response.text
    assert 'href="/tasks"' in response.text


def test_production_empty_acquisition_registry_is_normal_no_network_failure(
    auth_client: TestClient,
) -> None:
    item_id, source_id = _item_source()
    response = auth_client.post(
        f"/items/{item_id}/sources/{source_id}/assets/check",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "任务操作被拒绝或失败" in response.text
    with SessionLocal() as db:
        assert db.query(OperationTask).count() == 0
