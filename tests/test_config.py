from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("name", ["APP_PASSWORD", "SECRET_KEY"])
def test_required_credentials_reject_empty_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    monkeypatch.setenv("APP_PASSWORD", "valid-password")
    monkeypatch.setenv("SECRET_KEY", "valid-secret")
    monkeypatch.setenv(name, "   ")

    with pytest.raises(RuntimeError, match=f"^{name} must be set"):
        get_settings()


@pytest.mark.parametrize(
    ("name", "placeholder"),
    [
        ("APP_PASSWORD", "your_secure_password_here"),
        ("SECRET_KEY", "change_this_to_a_random_secret_key"),
    ],
)
def test_shipped_placeholders_are_rejected_without_echoing_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    placeholder: str,
) -> None:
    monkeypatch.setenv("APP_PASSWORD", "valid-password")
    monkeypatch.setenv("SECRET_KEY", "valid-secret")
    monkeypatch.setenv(name, placeholder)

    with pytest.raises(RuntimeError) as exc_info:
        get_settings()

    assert name in str(exc_info.value)
    assert placeholder not in str(exc_info.value)


def test_valid_settings_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PASSWORD", "unique-password")
    monkeypatch.setenv("SECRET_KEY", "unique-secret")
    monkeypatch.setenv("MAX_BACKUP_UPLOAD_MB", "7")
    monkeypatch.setenv("MAX_IMPORT_UPLOAD_MB", "9")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "yes")
    monkeypatch.setenv("TASK_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("DOWNLOAD_MAX_BYTES", "2097152")
    monkeypatch.setenv("DOWNLOAD_CHUNK_BYTES", "8192")
    monkeypatch.setenv("DOWNLOAD_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("DOWNLOAD_TEMP_RETENTION_HOURS", "12")
    monkeypatch.setenv("TASK_HISTORY_RETENTION_DAYS", "90")

    settings = get_settings()

    assert settings.app_password == "unique-password"
    assert settings.secret_key == "unique-secret"
    assert settings.max_backup_upload_mb == 7
    assert settings.max_import_upload_mb == 9
    assert settings.session_cookie_secure is True
    assert settings.task_max_concurrency == 3
    assert settings.download_max_bytes == 2_097_152
    assert settings.download_chunk_bytes == 8_192
    assert settings.download_timeout_seconds == 45
    assert settings.download_temp_retention_hours == 12
    assert settings.task_history_retention_days == 90


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MAX_BACKUP_UPLOAD_MB", "zero", "positive integer"),
        ("MAX_BACKUP_UPLOAD_MB", "0", "positive integer"),
        ("MAX_IMPORT_UPLOAD_MB", "-1", "positive integer"),
        ("SESSION_COOKIE_SECURE", "sometimes", "boolean"),
    ],
)
def test_malformed_upload_and_cookie_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv("APP_PASSWORD", "valid-password")
    monkeypatch.setenv("SECRET_KEY", "valid-secret")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=message):
        get_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TASK_MAX_CONCURRENCY", "33"),
        ("DOWNLOAD_MAX_BYTES", "100"),
        ("DOWNLOAD_CHUNK_BYTES", "4095"),
        ("DOWNLOAD_TIMEOUT_SECONDS", "3601"),
        ("DOWNLOAD_TEMP_RETENTION_HOURS", "721"),
        ("TASK_HISTORY_RETENTION_DAYS", "3651"),
    ],
)
def test_phase6_runtime_limits_are_strictly_bounded(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv("APP_PASSWORD", "valid-password")
    monkeypatch.setenv("SECRET_KEY", "valid-secret")
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="must be between"):
        get_settings()
