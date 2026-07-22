"""CopyManga-style JSON parse helpers (Venera-compatible fixed fields).

Attribution:
- https://github.com/venera-app/venera
- https://github.com/venera-app/venera/blob/master/doc/comic_source.md
"""

from __future__ import annotations

from typing import Any


class CopymangaParseError(ValueError):
    """Bounded parse failure for CopyManga-style JSON."""


def _results_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results")
    if isinstance(results, dict):
        # search: results.list
        items = results.get("list") or results.get("comics") or results.get("chapters")
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
        # detail/chapter payloads
        return [results]
    if isinstance(results, list):
        return [i for i in results if isinstance(i, dict)]
    # bare list root
    if isinstance(payload.get("list"), list):
        return [i for i in payload["list"] if isinstance(i, dict)]
    raise CopymangaParseError("comic JSON has no results list")


def parse_search_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        raise CopymangaParseError("search root must be an object")
    cards: list[dict[str, str]] = []
    for item in _results_list(payload):
        path_word = (
            item.get("path_word")
            or item.get("pathWord")
            or item.get("comic_id")
            or item.get("id")
        )
        name = item.get("name") or item.get("title") or path_word
        if not path_word or not name:
            continue
        cards.append(
            {
                "external_id": str(path_word),
                "title": str(name),
                "cover": str(item.get("cover") or item.get("cover_url") or ""),
            }
        )
    return cards


def parse_detail_payload(payload: dict[str, Any], *, external_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CopymangaParseError("detail root must be an object")
    results = payload.get("results")
    if not isinstance(results, dict):
        # allow flat detail
        results = payload
    comic = results.get("comic") if isinstance(results.get("comic"), dict) else results
    name = comic.get("name") or comic.get("title") or external_id
    path_word = comic.get("path_word") or comic.get("pathWord") or external_id
    summary = comic.get("brief") or comic.get("summary") or comic.get("desc") or ""
    return {
        "external_id": str(path_word),
        "title": str(name),
        "summary": str(summary) if summary else None,
        "cover": str(comic.get("cover") or comic.get("cover_url") or ""),
        "author": comic.get("author") or comic.get("authors"),
    }


def parse_chapters_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        raise CopymangaParseError("chapters root must be an object")
    results = payload.get("results")
    chapters_raw: list[Any] = []
    if isinstance(results, dict):
        lst = results.get("list") or results.get("chapters")
        if isinstance(lst, list):
            chapters_raw = lst
        elif isinstance(results.get("groups"), dict):
            # some APIs nest groups.default.chapters
            for group in results["groups"].values():
                if isinstance(group, dict) and isinstance(group.get("chapters"), list):
                    chapters_raw.extend(group["chapters"])
    elif isinstance(results, list):
        chapters_raw = results
    out: list[dict[str, str]] = []
    for ch in chapters_raw:
        if not isinstance(ch, dict):
            continue
        cid = ch.get("uuid") or ch.get("id") or ch.get("chapter_id") or ch.get("path_word")
        name = ch.get("name") or ch.get("title") or cid
        if not cid:
            continue
        out.append({"chapter_id": str(cid), "title": str(name)})
    return out


def parse_chapter_pages_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Page image URLs for one chapter (for acquisition)."""

    if not isinstance(payload, dict):
        raise CopymangaParseError("chapter pages root must be an object")
    results = payload.get("results") if isinstance(payload.get("results"), dict) else payload
    chapter = results.get("chapter") if isinstance(results.get("chapter"), dict) else results
    contents = chapter.get("contents") or chapter.get("pages") or chapter.get("images") or []
    if not isinstance(contents, list):
        raise CopymangaParseError("chapter pages list missing")
    pages: list[dict[str, str]] = []
    for index, item in enumerate(contents):
        if isinstance(item, str) and item.startswith("http"):
            pages.append({"asset_id": f"p{index+1:04d}", "url": item})
        elif isinstance(item, dict):
            url = item.get("url") or item.get("src") or item.get("path")
            if isinstance(url, str) and url.startswith("http"):
                aid = str(item.get("id") or f"p{index+1:04d}")
                pages.append({"asset_id": aid, "url": url})
    return pages
