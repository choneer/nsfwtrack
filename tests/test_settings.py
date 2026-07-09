from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import AppSetting
from app.services.settings import get_app_settings


def _save_settings(
    client: TestClient,
    *,
    language: str = "zh",
    page_size: str = "20",
    sort: str = "updated_at",
    sort_dir: str = "desc",
    home: str = "workbench",
    follow_redirects: bool = False,
):
    return client.post(
        "/settings",
        data={
            "default_language": language,
            "default_page_size": page_size,
            "default_sort": sort,
            "default_sort_dir": sort_dir,
            "default_home": home,
        },
        follow_redirects=follow_redirects,
    )


def _setting_count() -> int:
    with SessionLocal() as db:
        return db.query(AppSetting).count()


def _create_item(client: TestClient, title: str) -> None:
    response = client.post("/api/items", json={"title": title})
    assert response.status_code == 201


def test_settings_page_requires_login(client: TestClient) -> None:
    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_settings_page_renders_and_saves_valid_values(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/settings")
    assert response.status_code == 200
    assert "设置" in response.text
    assert "默认语言" in response.text

    save_response = _save_settings(
        auth_client,
        language="en",
        page_size="50",
        sort="title",
        sort_dir="asc",
        home="stats",
        follow_redirects=False,
    )

    assert save_response.status_code == 303
    with SessionLocal() as db:
        settings = get_app_settings(db)
    assert settings.default_language == "en"
    assert settings.default_page_size == 50
    assert settings.default_sort == "title"
    assert settings.default_sort_dir == "asc"
    assert settings.default_home == "stats"
    assert _setting_count() == 5


def test_settings_reject_invalid_key_and_value_without_500(
    auth_client: TestClient,
) -> None:
    invalid_key_response = auth_client.post(
        "/settings",
        data={"unknown": "https://example.test"},
        follow_redirects=True,
    )
    invalid_value_response = auth_client.post(
        "/settings",
        data={
            "default_language": "<script>alert(1)</script>",
            "default_page_size": "20",
            "default_sort": "updated_at",
            "default_sort_dir": "desc",
            "default_home": "workbench",
        },
        follow_redirects=True,
    )

    assert invalid_key_response.status_code == 200
    assert "设置项无效" in invalid_key_response.text
    assert invalid_value_response.status_code == 200
    assert "设置值无效" in invalid_value_response.text
    assert _setting_count() == 0


def test_item_list_uses_default_page_size_sort_and_url_override(
    auth_client: TestClient,
) -> None:
    for index in range(12):
        _create_item(auth_client, f"Setting Item {index:02d}")
    _save_settings(
        auth_client,
        page_size="10",
        sort="title",
        sort_dir="asc",
        follow_redirects=False,
    )

    default_response = auth_client.get("/items")
    override_response = auth_client.get("/items?sort=title_desc&page_size=50")

    assert default_response.status_code == 200
    assert "显示 1-10 / 12" in default_response.text
    assert "分页大小: 10" in default_response.text
    assert "当前排序: 标题 A-Z" in default_response.text
    assert "Setting Item 00" in default_response.text
    assert "Setting Item 10" not in default_response.text

    assert override_response.status_code == 200
    assert "分页大小: 50" in override_response.text
    assert "当前排序: 标题 Z-A" in override_response.text
    assert override_response.text.index("Setting Item 11") < override_response.text.index(
        "Setting Item 00"
    )


def test_default_language_fallback_keeps_explicit_language_switch(
    auth_client: TestClient,
) -> None:
    response = _save_settings(auth_client, language="en", follow_redirects=True)
    assert response.status_code == 200
    assert "Settings saved." in response.text
    assert "Default Language" in response.text

    zh_response = auth_client.get(
        "/set-language",
        params={"lang": "zh", "next": "/settings"},
    )

    assert zh_response.status_code == 200
    assert "默认语言" in zh_response.text
    assert "Settings" not in zh_response.text


def test_settings_reset_restores_defaults_with_confirmation(
    auth_client: TestClient,
) -> None:
    _save_settings(
        auth_client,
        page_size="50",
        sort="title",
        sort_dir="asc",
        home="activity",
        follow_redirects=False,
    )

    missing_confirm_response = auth_client.post(
        "/settings/reset",
        follow_redirects=True,
    )
    assert missing_confirm_response.status_code == 200
    assert "缺少手动确认" in missing_confirm_response.text
    assert _setting_count() == 5

    reset_response = auth_client.post(
        "/settings/reset",
        data={"confirm": "1"},
        follow_redirects=True,
    )

    assert reset_response.status_code == 200
    assert "设置已恢复默认值" in reset_response.text
    assert _setting_count() == 0
    with SessionLocal() as db:
        settings = get_app_settings(db)
    assert settings.default_language == "zh"
    assert settings.default_page_size == 20
    assert settings.default_sort == "updated_at"
    assert settings.default_sort_dir == "desc"
    assert settings.default_home == "workbench"


def test_default_home_is_highlighted_on_workbench(
    auth_client: TestClient,
) -> None:
    _save_settings(auth_client, home="stats", follow_redirects=False)

    response = auth_client.get("/")

    assert response.status_code == 200
    assert "当前默认入口" in response.text
    assert "默认入口" in response.text
    assert "is-default" in response.text
