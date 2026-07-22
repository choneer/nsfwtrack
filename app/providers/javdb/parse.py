"""Conservative JavDB-shaped HTML parsers for offline fixtures.

Does not perform network I/O. Field extraction is intentionally narrow so
malformed fixtures fail closed via the adapter error boundary.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin


_SLUG_RE = re.compile(r"/v/([A-Za-z0-9_-]+)")
_CODE_RE = re.compile(r"\b([A-Z]{2,10}-?\d{2,5}[A-Z]?)\b", re.IGNORECASE)


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("__root__", {})
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {k.lower(): (v or "") for k, v in attrs})
        self._stack[-1].children.append(node)
        if tag.lower() not in {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


def _parse_tree(html: str) -> _Node:
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    return parser.root


def _walk(node: _Node) -> list[_Node]:
    out: list[_Node] = []
    for child in node.children:
        if isinstance(child, _Node):
            out.append(child)
            out.extend(_walk(child))
    return out


def _text(node: _Node) -> str:
    parts: list[str] = []
    for child in node.children:
        parts.append(_text(child) if isinstance(child, _Node) else child)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def parse_search_html(html: str, *, base_url: str) -> list[dict[str, str | None]]:
    """Return search cards: external_id (slug), catalog_number, title, cover_asset_id."""

    if not isinstance(html, str) or not html.strip():
        raise ValueError("empty html")
    root = _parse_tree(html)
    nodes = _walk(root)
    results: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for anchor in nodes:
        if anchor.tag != "a":
            continue
        href = anchor.attrs.get("href", "")
        match = _SLUG_RE.search(href)
        if not match:
            continue
        slug = match.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        # Prefer the video-title subtree or title attribute over full card text
        # (card text often includes meta dates/scores).
        title_node = None
        for child in _walk(anchor):
            if "video-title" in _classes(child):
                title_node = child
                break
        card_text = _text(title_node) if title_node is not None else ""
        attr_title = anchor.attrs.get("title", "").strip()
        title_source = card_text or attr_title or _text(anchor)
        code_match = _CODE_RE.search(title_source) or _CODE_RE.search(attr_title)
        catalog = code_match.group(1).upper() if code_match else None
        title = title_source or slug
        if catalog and title.upper().startswith(catalog):
            title = title[len(catalog) :].strip(" -:\u3000") or title
        # Drop trailing date noise if present
        title = re.sub(r"\s+\d{4}-\d{2}-\d{2}\s*$", "", title).strip() or title
        cover_id = None
        for child in _walk(anchor):
            if child.tag == "img":
                src = child.attrs.get("src") or child.attrs.get("data-src") or ""
                if src:
                    cover_id = src.rsplit("/", 1)[-1] or src
                    break
        results.append(
            {
                "external_id": slug,
                "catalog_number": catalog,
                "title": title,
                "canonical_url": urljoin(base_url.rstrip("/") + "/", href.lstrip("/")),
                "cover_asset_id": cover_id,
            }
        )
    return results


def parse_detail_html(
    html: str,
    *,
    external_id: str,
    base_url: str,
) -> dict[str, object]:
    """Parse a detail page into a flat dict for VideoDetail mapping."""

    if not isinstance(html, str) or not html.strip():
        raise ValueError("empty html")
    if not external_id:
        raise ValueError("external_id required")
    root = _parse_tree(html)
    nodes = _walk(root)
    payload: dict[str, object] = {
        "external_id": external_id,
        "canonical_url": f"{base_url.rstrip('/')}/v/{external_id}",
    }
    for node in nodes:
        classes = _classes(node)
        if "current-title" in classes or (node.tag in {"h2", "h1"} and _text(node)):
            text = _text(node)
            if not text:
                continue
            code_match = _CODE_RE.search(text)
            if code_match:
                payload["catalog_number"] = code_match.group(1).upper()
                rest = text[code_match.end() :].strip(" -:\u3000")
                payload["title"] = rest or text
            else:
                payload["title"] = text
            break
    if "title" not in payload:
        for node in nodes:
            if node.tag == "strong" and _text(node):
                payload["title"] = _text(node)
                break
    if "title" not in payload:
        raise ValueError("detail title missing")

    for node in nodes:
        if node.tag == "img" and "video-cover" in _classes(node):
            src = node.attrs.get("src") or node.attrs.get("data-src") or ""
            if src:
                payload["cover_asset_id"] = src.rsplit("/", 1)[-1] or src
                break

    label_map = {
        "日期": "release_date",
        "時長": "duration_minutes",
        "时长": "duration_minutes",
        "導演": "director",
        "导演": "director",
        "片商": "studio",
        "發行": "publisher",
        "发行": "publisher",
        "系列": "series",
    }
    for node in nodes:
        text = _text(node)
        # Skip ancestor nodes that concatenate multiple panel fields.
        if len(text) > 80:
            continue
        for label, key in label_map.items():
            if label in text and key not in payload:
                value = re.sub(rf"^.*?{re.escape(label)}\s*[:：]?\s*", "", text).strip()
                if key == "duration_minutes":
                    match = re.search(r"(\d+)", value)
                    if match:
                        payload[key] = int(match.group(1))
                elif key == "release_date":
                    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
                    if match:
                        payload[key] = match.group(1)
                elif value and value != text and len(value) <= 80:
                    payload[key] = value
                break

    tags = [
        _text(node)
        for node in nodes
        if node.tag == "a" and "/tags" in node.attrs.get("href", "") and _text(node)
    ]
    if tags:
        payload["tags"] = tags

    performers = [
        _text(node)
        for node in nodes
        if node.tag == "a" and "/actors/" in node.attrs.get("href", "") and _text(node)
    ]
    if performers:
        payload["performers"] = performers

    previews = [
        (node.attrs.get("href", "").rsplit("/", 1)[-1] or node.attrs.get("href", ""))
        for node in nodes
        if node.tag == "a" and node.attrs.get("data-fancybox") == "gallery"
        and node.attrs.get("href")
    ]
    if previews:
        payload["preview_asset_ids"] = previews

    return payload
