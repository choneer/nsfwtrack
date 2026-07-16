from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["APP_PASSWORD"] = "test-password"
os.environ["SECRET_KEY"] = "test-secret-key"
_TEST_RUNTIME_DIRECTORY = Path(tempfile.mkdtemp(prefix="nsfwtrack-pytest-"))
os.environ["DATABASE_URL"] = (
    f"sqlite:///{_TEST_RUNTIME_DIRECTORY / 'test.db'}"
)
atexit.register(shutil.rmtree, _TEST_RUNTIME_DIRECTORY, ignore_errors=True)

from app.database import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[None, None, None]:
    from app.services import local_media, media_operation_lock

    lock_directory = tmp_path / "app-data"
    lock_directory.mkdir(mode=0o700)
    monkeypatch.setattr(
        media_operation_lock,
        "MEDIA_OPERATION_LOCK_DIRECTORY",
        lock_directory,
    )
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", tmp_path / "media")
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    response = client.post("/api/auth/login", json={"password": "test-password"})
    assert response.status_code == 200
    return client
