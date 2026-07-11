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

    settings = get_settings()

    assert settings.app_password == "unique-password"
    assert settings.secret_key == "unique-secret"
    assert settings.max_backup_upload_mb == 7
    assert settings.max_import_upload_mb == 9
    assert settings.session_cookie_secure is True


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
