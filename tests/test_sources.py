from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Item, ItemSource
from app.services.sources import (
    SourceError,
    build_source_preview,
    import_source_rows,
    normalize_source_url,
    parse_bookmarks_html,
    parse_source_text,
)


def _create_item(auth_client: object, title: str) -> int:
    response = auth_client.post(
        "/api/items",
        json={"title": title, "tags": [], "creators": []},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _source_rows() -> list[ItemSource]:
    with SessionLocal() as db:
        return list(db.scalars(select(ItemSource).order_by(ItemSource.id)).all())


def _item_titles() -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(Item.title).order_by(Item.id)).all())


def test_source_pages_require_login(client: object) -> None:
    assert client.get("/sources/import", follow_redirects=False).status_code == 303
    assert (
        client.post(
            "/sources/import/preview",
            data={"source_text": "https://example.com"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        client.post(
            "/sources/import/apply",
            data={"payload": "https://example.com", "confirm": "1"},
            follow_redirects=False,
        ).status_code
        == 303
    )


def test_url_normalization_is_deterministic_and_rejects_unsafe_values() -> None:
    assert (
        normalize_source_url(" HTTPS://ExAmPle.COM:443/a%7eb?q=%7e#fragment ")
        == "https://example.com/a~b?q=~"
    )
    assert normalize_source_url("http://example.com:80") == "http://example.com/"
    for value in (
        "javascript:alert(1)",
        "file:///tmp/a",
        "https://user:pass@example.com/",
        "https://example.com/bad path",
        "https://example.com/bad%escape",
        "not-a-url",
    ):
        try:
            normalize_source_url(value)
        except SourceError as exc:
            assert exc.code == "invalid_url"
        else:  # pragma: no cover - explicit failure message
            raise AssertionError(f"accepted unsafe URL: {value}")


def test_detail_supports_multiple_sources_and_confirmed_delete(auth_client: object) -> None:
    item_id = _create_item(auth_client, "Source Item")
    first = auth_client.post(
        f"/items/{item_id}/sources",
        data={"title": "Primary", "url": "https://Example.com:443/a#top"},
        follow_redirects=True,
    )
    second = auth_client.post(
        f"/items/{item_id}/sources",
        data={"title": "Second", "url": "https://example.org/b"},
        follow_redirects=True,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "来源链接已添加" in second.text
    assert "https://example.com/a" in second.text
    assert len(_source_rows()) == 2

    source_id = _source_rows()[0].id
    missing_confirm = auth_client.post(
        f"/items/{item_id}/sources/{source_id}/delete",
        follow_redirects=True,
    )
    assert missing_confirm.status_code == 200
    assert len(_source_rows()) == 2

    deleted = auth_client.post(
        f"/items/{item_id}/sources/{source_id}/delete",
        data={"confirm": "1"},
        follow_redirects=True,
    )
    assert "来源链接已删除" in deleted.text
    assert len(_source_rows()) == 1


def test_normalized_url_is_globally_unique_and_reports_conflict(auth_client: object) -> None:
    first_id = _create_item(auth_client, "First")
    second_id = _create_item(auth_client, "Second")
    assert auth_client.post(
        f"/items/{first_id}/sources",
        data={"url": "https://example.com/path#one"},
        follow_redirects=True,
    ).status_code == 200

    duplicate = auth_client.post(
        f"/items/{first_id}/sources",
        data={"url": "HTTPS://EXAMPLE.COM:443/path#two"},
        follow_redirects=True,
    )
    conflict = auth_client.post(
        f"/items/{second_id}/sources",
        data={"url": "https://example.com/path"},
        follow_redirects=True,
    )

    assert "已关联到当前条目" in duplicate.text
    assert "已关联到其他条目" in conflict.text
    assert len(_source_rows()) == 1


def test_text_preview_reports_new_duplicate_invalid_and_conflict_without_write(
    auth_client: object,
) -> None:
    item_id = _create_item(auth_client, "Existing")
    auth_client.post(
        f"/items/{item_id}/sources",
        data={"url": "https://example.com/existing"},
    )
    before_items = _item_titles()
    before_sources = len(_source_rows())
    payload = (
        "Existing\thttps://example.com/existing#fragment\n"
        "Other\tHTTPS://EXAMPLE.COM:443/existing\n"
        "New title\thttps://example.com/new\n"
        "bad-url\n"
        "New title\thttps://example.com/new#again\n"
    )
    with SessionLocal() as db:
        preview = build_source_preview(db, parse_source_text(payload))
        assert (
            preview.total,
            preview.new,
            preview.duplicate,
            preview.invalid,
            preview.conflict,
            preview.new_items,
        ) == (5, 1, 2, 1, 1, 1)

    response = auth_client.post(
        "/sources/import/preview",
        data={"source_text": payload},
    )

    assert response.status_code == 200
    assert "<strong>5</strong>" in response.text
    assert "<strong>1</strong>" in response.text
    assert "重复" in response.text
    assert "无效" in response.text
    assert "冲突" in response.text
    assert _item_titles() == before_items
    assert len(_source_rows()) == before_sources


def test_text_import_requires_confirmation_and_creates_placeholder_item(
    auth_client: object,
) -> None:
    payload = "https://example.com/path/to/item\nTitle\thttps://example.org/two"
    missing_confirm = auth_client.post(
        "/sources/import/apply",
        data={"payload": payload},
        follow_redirects=True,
    )
    assert missing_confirm.status_code == 200
    assert _source_rows() == []

    response = auth_client.post(
        "/sources/import/apply",
        data={"payload": payload, "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "新增 2" in response.text
    assert len(_source_rows()) == 2
    assert _item_titles() == ["example.com/path/to/item", "Title"]


def test_bookmark_html_preview_parses_local_file_without_fetching(auth_client: object) -> None:
    bookmarks = b"""<!DOCTYPE NETSCAPE-Bookmark-file-1>
    <DL><p>
      <DT><A HREF="https://example.com/a">Example A</A>
      <DT><A HREF="https://example.org/b#fragment">Example B</A>
      <DT><A HREF="javascript:alert(1)">Blocked</A>
    </DL><p>"""

    response = auth_client.post(
        "/sources/import/preview",
        files={"bookmarks_file": ("bookmarks.html", bookmarks, "text/html")},
    )

    assert response.status_code == 200
    assert "Example A" in response.text
    assert "https://example.org/b" in response.text
    assert "<strong>3</strong>" in response.text
    assert _source_rows() == []


def test_bookmark_parser_and_import_support_multiple_urls_for_one_title() -> None:
    rows = parse_bookmarks_html(
        b'<A HREF="https://example.com/a">Same Item</A>'
        b'<A HREF="https://example.com/b">Same Item</A>'
    )
    with SessionLocal() as db:
        preview = build_source_preview(db, rows)
        assert preview.new == 2
        assert preview.new_items == 1
        result = import_source_rows(db, rows)
        assert result.new == 2

    assert _item_titles() == ["Same Item"]
    assert len(_source_rows()) == 2


def test_identical_existing_titles_are_ambiguous_and_never_imported(
    auth_client: object,
) -> None:
    first_id = _create_item(auth_client, "Same title")
    second_id = _create_item(auth_client, "Same title")
    payload = "Same title\thttps://example.com/ambiguous"

    with SessionLocal() as db:
        preview = build_source_preview(db, parse_source_text(payload))
        assert (preview.new, preview.conflict, preview.new_items) == (0, 1, 0)
        assert preview.rows[0].detail == "ambiguous_existing_title"

    response = auth_client.post(
        "/sources/import/preview",
        data={"source_text": payload},
    )
    assert "存在多个同名条目，无法确定目标" in response.text

    auth_client.post(
        "/sources/import/apply",
        data={"payload": payload, "confirm": "1"},
        follow_redirects=True,
    )
    assert _source_rows() == []
    with SessionLocal() as db:
        items = list(db.scalars(select(Item).order_by(Item.id)).all())
        assert [(item.id, item.title) for item in items] == [
            (first_id, "Same title"),
            (second_id, "Same title"),
        ]


def test_casefold_equivalent_existing_titles_are_ambiguous_in_english_preview(
    auth_client: object,
) -> None:
    _create_item(auth_client, "Case Title")
    _create_item(auth_client, "case title")
    payload = "CASE TITLE\thttps://example.com/casefold-ambiguous"

    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/sources/import"},
    )
    response = auth_client.post(
        "/sources/import/preview",
        data={"source_text": payload},
    )
    assert response.status_code == 200
    assert "Multiple items have the same title" in response.text
    assert "target cannot be determined" in response.text

    with SessionLocal() as db:
        result = import_source_rows(db, parse_source_text(payload))
        assert (result.new, result.conflict) == (0, 1)
    assert _source_rows() == []
    assert _item_titles() == ["Case Title", "case title"]


def test_mixed_ambiguous_and_normal_rows_import_only_the_normal_row(
    auth_client: object,
) -> None:
    _create_item(auth_client, "Ambiguous")
    _create_item(auth_client, "AMBIGUOUS")
    normal_id = _create_item(auth_client, "Normal")
    payload = (
        "ambiguous\thttps://example.com/skipped\n"
        "Normal\thttps://example.com/imported"
    )

    response = auth_client.post(
        "/sources/import/apply",
        data={"payload": payload, "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "新增 1" in response.text
    assert "冲突 1" in response.text
    sources = _source_rows()
    assert len(sources) == 1
    assert sources[0].item_id == normal_id
    assert sources[0].normalized_url == "https://example.com/imported"
    assert _item_titles() == ["Ambiguous", "AMBIGUOUS", "Normal"]


def test_apply_rechecks_title_ambiguity_after_preview(monkeypatch: object) -> None:
    rows = parse_source_text("Race title\thttps://example.com/race")
    original_preview = build_source_preview

    def preview_then_add_ambiguity(
        db: object, pending_rows: object
    ) -> object:
        preview = original_preview(db, pending_rows)
        db.add_all([Item(title="Race title"), Item(title="RACE TITLE")])
        db.flush()
        return preview

    monkeypatch.setattr(
        "app.services.sources.build_source_preview",
        preview_then_add_ambiguity,
    )
    with SessionLocal() as db:
        try:
            import_source_rows(db, rows)
        except SourceError as exc:
            assert exc.code == "ambiguous_existing_title"
        else:
            raise AssertionError("source import ignored a newly ambiguous title")

    assert _source_rows() == []
    assert _item_titles() == []


def test_batch_failure_rolls_back_items_and_sources(monkeypatch: object) -> None:
    rows = parse_source_text(
        "One\thttps://example.com/one\nTwo\thttps://example.com/two"
    )
    with SessionLocal() as db:
        original_commit = db.commit

        def fail_commit() -> None:
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        try:
            import_source_rows(db, rows)
        except SourceError as exc:
            assert exc.code == "import_failed"
        else:
            raise AssertionError("source import unexpectedly committed")
        monkeypatch.setattr(db, "commit", original_commit)

    assert _item_titles() == []
    assert _source_rows() == []
