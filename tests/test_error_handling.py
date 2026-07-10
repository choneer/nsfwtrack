from __future__ import annotations

import logging
import re
from collections.abc import Generator

import pytest
from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.main import create_app
from app.models import Tag
from app.request_context import REQUEST_ID_HEADER, is_valid_request_id

EXPECTED_SECRET = "not-for-user-output"
SQL_SECRET = "SELECT password FROM users WHERE token='private-token'"
PATH_SECRET = "/home/nsfwtrack/private.env"
AUTH_SECRET = "Bearer authorization-secret"
COOKIE_SECRET = "session=cookie-secret"
PASSWORD_SECRET = "password=form-secret"
UPLOAD_SECRET = b"private-upload-content"


@pytest.fixture
def error_client() -> Generator[TestClient, None, None]:
    test_app = create_app()

    @test_app.get("/testing-errors/http/{status_code}")
    def page_http_error(status_code: int) -> None:
        headers = {"Allow": "POST"} if status_code == 405 else None
        raise HTTPException(
            status_code=status_code,
            detail="Expected page error",
            headers=headers,
        )

    @test_app.get("/api/testing-errors/http/{status_code}")
    def api_http_error(status_code: int) -> None:
        raise HTTPException(status_code=status_code, detail="Expected API error")

    @test_app.get("/api/testing-errors/sensitive-http")
    def sensitive_http_error() -> None:
        raise HTTPException(
            status_code=400,
            detail=f"{SQL_SECRET} {PATH_SECRET} {PASSWORD_SECRET}",
        )

    @test_app.get("/testing-errors/failure")
    def page_failure() -> None:
        raise RuntimeError(f"{EXPECTED_SECRET} {SQL_SECRET} {PATH_SECRET}")

    @test_app.get("/api/testing-errors/failure")
    def api_failure() -> None:
        raise RuntimeError(f"{EXPECTED_SECRET} {SQL_SECRET} {PATH_SECRET}")

    @test_app.get("/api/testing-errors/validated")
    def validated(value: int = Query(ge=1)) -> dict[str, int]:
        return {"value": value}

    @test_app.post("/testing-errors/validated-form")
    def validated_form(value: str = Form(...)) -> dict[str, str]:
        return {"value": value}

    @test_app.post("/testing-errors/post-only")
    def post_only() -> dict[str, bool]:
        return {"ok": True}

    @test_app.post("/api/testing-errors/post-only")
    def api_post_only() -> dict[str, bool]:
        return {"ok": True}

    @test_app.post("/api/testing-errors/upload-failure")
    async def upload_failure(file: UploadFile = File(...)) -> None:
        await file.read()
        raise RuntimeError(f"{EXPECTED_SECRET} {SQL_SECRET} {PATH_SECRET}")

    @test_app.post("/api/testing-errors/rollback")
    def rollback_failure(db: Session = Depends(get_db)) -> None:
        db.add(Tag(name="Uncommitted error tag"))
        db.flush()
        raise RuntimeError(EXPECTED_SECRET)

    with TestClient(test_app) as test_client:
        yield test_client


def _assert_request_id(response: object) -> str:
    request_id = response.headers[REQUEST_ID_HEADER]
    assert is_valid_request_id(request_id)
    return request_id


def test_page_404_uses_unified_html_without_becoming_500(
    error_client: TestClient,
) -> None:
    response = error_client.get("/missing-page")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "页面不存在" in response.text
    assert "请求标识" in response.text
    assert _assert_request_id(response) in response.text


@pytest.mark.parametrize(
    ("status_code", "title"),
    [
        (400, "请求无效"),
        (403, "禁止访问"),
        (409, "操作冲突"),
    ],
)
def test_expected_page_http_errors_use_unified_html(
    error_client: TestClient,
    status_code: int,
    title: str,
) -> None:
    response = error_client.get(f"/testing-errors/http/{status_code}")

    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("text/html")
    assert title in response.text
    assert _assert_request_id(response) in response.text


def test_api_and_explicit_json_404_use_error_envelope(
    error_client: TestClient,
) -> None:
    api_response = error_client.get("/api/missing-resource")
    accepted_response = error_client.get(
        "/another-missing-resource",
        headers={"Accept": "application/json"},
    )

    for response in (api_response, accepted_response):
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        payload = response.json()
        assert payload["error"] == "not_found"
        assert payload["message"]
        assert payload["detail"]
        assert payload["request_id"] == _assert_request_id(response)


@pytest.mark.parametrize("status_code", [400, 403, 409])
def test_expected_api_http_errors_keep_status_and_json_shape(
    error_client: TestClient,
    status_code: int,
) -> None:
    response = error_client.get(f"/api/testing-errors/http/{status_code}")

    assert response.status_code == status_code
    assert response.json() == {
        "error": {
            400: "bad_request",
            403: "forbidden",
            409: "conflict",
        }[status_code],
        "message": "Expected API error",
        "request_id": response.headers[REQUEST_ID_HEADER],
        "detail": "Expected API error",
    }


def test_sensitive_http_detail_is_replaced_with_generic_message(
    error_client: TestClient,
) -> None:
    response = error_client.get("/api/testing-errors/sensitive-http")
    rendered = response.text

    assert response.status_code == 400
    assert response.json()["message"] == "无法处理这个请求，请检查输入后重试。"
    for secret in (SQL_SECRET, PATH_SECRET, PASSWORD_SECRET):
        assert secret not in rendered


def test_405_preserves_allow_header_for_generated_and_explicit_errors(
    error_client: TestClient,
) -> None:
    generated = error_client.get("/testing-errors/post-only")
    explicit = error_client.get("/testing-errors/http/405")

    for response in (generated, explicit):
        assert response.status_code == 405
        assert response.headers["allow"] == "POST"
        assert response.headers["content-type"].startswith("text/html")
        _assert_request_id(response)


def test_api_405_preserves_allow_header_and_json_shape(
    error_client: TestClient,
) -> None:
    response = error_client.get("/api/testing-errors/post-only")

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"] == "method_not_allowed"
    assert response.json()["request_id"] == _assert_request_id(response)


def test_api_422_preserves_validation_location_without_echoing_input(
    error_client: TestClient,
) -> None:
    response = error_client.get(
        "/api/testing-errors/validated",
        params={"value": "password=validation-secret"},
    )
    payload = response.json()

    assert response.status_code == 422
    assert payload["error"] == "validation_error"
    assert payload["request_id"] == _assert_request_id(response)
    assert isinstance(payload["detail"], list)
    assert payload["detail"][0]["loc"] == ["query", "value"]
    assert {"type", "loc", "msg"} <= set(payload["detail"][0])
    assert "input" not in payload["detail"][0]
    assert "validation-secret" not in response.text


def test_page_422_uses_html_error_page(error_client: TestClient) -> None:
    response = error_client.post("/testing-errors/validated-form", data={})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert "输入校验失败" in response.text
    assert _assert_request_id(response) in response.text


@pytest.mark.parametrize("path", ["/testing-errors/failure", "/api/testing-errors/failure"])
def test_unhandled_500_is_generic_and_contains_only_safe_request_context(
    error_client: TestClient,
    path: str,
) -> None:
    response = error_client.get(path)
    request_id = _assert_request_id(response)

    assert response.status_code == 500
    assert request_id in response.text
    for secret in (EXPECTED_SECRET, SQL_SECRET, PATH_SECRET, "Traceback"):
        assert secret not in response.text
    if path.startswith("/api/"):
        assert response.json() == {
            "error": "internal_server_error",
            "message": "发生内部错误，请稍后重试。",
            "request_id": request_id,
        }
    else:
        assert response.headers["content-type"].startswith("text/html")
        assert "暂时无法完成请求" in response.text


def test_valid_request_id_is_returned_and_invalid_values_are_replaced(
    error_client: TestClient,
) -> None:
    accepted = error_client.get(
        "/api/missing-resource",
        headers={REQUEST_ID_HEADER: "client-request_123"},
    )
    rejected = error_client.get(
        "/api/missing-resource",
        headers={REQUEST_ID_HEADER: "invalid request id"},
    )
    oversized = error_client.get(
        "/api/missing-resource",
        headers={REQUEST_ID_HEADER: "a" * 65},
    )

    assert accepted.headers[REQUEST_ID_HEADER] == "client-request_123"
    assert rejected.headers[REQUEST_ID_HEADER] != "invalid request id"
    assert oversized.headers[REQUEST_ID_HEADER] != "a" * 65
    assert is_valid_request_id(rejected.headers[REQUEST_ID_HEADER])
    assert is_valid_request_id(oversized.headers[REQUEST_ID_HEADER])


def test_success_and_redirect_responses_also_include_request_id(
    error_client: TestClient,
) -> None:
    success = error_client.get("/login")
    redirect = error_client.get("/items", follow_redirects=False)

    assert success.status_code == 200
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/login"
    _assert_request_id(success)
    _assert_request_id(redirect)


def test_request_log_has_safe_fields_and_omits_headers_body_and_query(
    error_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error.nsfwtrack.request")
    response = error_client.post(
        f"/api/testing-errors/upload-failure?{PASSWORD_SECRET}",
        headers={
            "Authorization": AUTH_SECRET,
            "Cookie": COOKIE_SECRET,
        },
        files={"file": ("private.txt", UPLOAD_SECRET, "text/plain")},
    )
    request_id = response.headers[REQUEST_ID_HEADER]
    rendered_log = caplog.text

    assert response.status_code == 500
    assert f"request_id={request_id}" in rendered_log
    assert "method=POST" in rendered_log
    assert "path=/api/testing-errors/upload-failure" in rendered_log
    assert "status=500" in rendered_log
    assert re.search(r"duration_ms=\d+\.\d{3}", rendered_log)
    assert "exception_type=RuntimeError" in rendered_log
    for secret in (
        AUTH_SECRET,
        COOKIE_SECRET,
        PASSWORD_SECRET,
        UPLOAD_SECRET.decode(),
        EXPECTED_SECRET,
        SQL_SECRET,
        PATH_SECRET,
    ):
        assert secret not in rendered_log


def test_expected_404_is_not_logged_as_system_exception(
    error_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error.nsfwtrack.request")
    response = error_client.get("/api/ordinary-missing")
    records = [
        record
        for record in caplog.records
        if record.name == "uvicorn.error.nsfwtrack.request"
    ]

    assert response.status_code == 404
    assert records
    assert records[-1].levelno == logging.INFO
    assert "status=404" in records[-1].getMessage()
    assert "exception_type=" not in records[-1].getMessage()


def test_unhandled_database_write_is_rolled_back(error_client: TestClient) -> None:
    response = error_client.post("/api/testing-errors/rollback")

    assert response.status_code == 500
    with SessionLocal() as db:
        assert db.scalar(
            select(Tag).where(Tag.name == "Uncommitted error tag")
        ) is None
