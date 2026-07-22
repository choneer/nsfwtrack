"""Offline Jiuse VideoMetadataAdapter (fixture HTML catalog)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.providers.jiuse.approval import JIUSE_HOST, JIUSE_PROVIDER_KEY
from app.providers.jiuse.parse import JiuseParseError, parse_jiuse_video_html
from app.source_adapters.contracts import (
    ProviderAdapterError,
    ProviderError,
    ProviderErrorCode,
    ProviderOperation,
)
from app.video_metadata.contracts import (
    VideoConfidence,
    VideoDetail,
    VideoIdentifier,
    VideoMetadataProvenance,
    VideoPerson,
    VideoPersonRole,
    VideoProvenanceOperation,
    VideoSearchPage,
    VideoSearchResult,
)


class JiuseFixtureVideoMetadataAdapter:
    """Maps local HTML fixtures into SEARCH/DETAIL DTOs."""

    key = JIUSE_PROVIDER_KEY

    def __init__(self, fixture_root: Path) -> None:
        self._root = fixture_root
        self._base = f"https://{JIUSE_HOST}"

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        if not query.strip() or page < 1 or page_size < 1:
            raise _error(ProviderOperation.SEARCH)
        cards = self._index()
        q = query.strip().casefold()
        if q not in {"*", "__all__"}:
            cards = [
                c
                for c in cards
                if q in c["video_id"].casefold()
                or q in (c.get("title") or "").casefold()
            ]
        start = (page - 1) * page_size
        window = cards[start : start + page_size]
        observed = datetime.now(tz=UTC)
        items = tuple(
            VideoSearchResult(
                identifier=VideoIdentifier(
                    provider_key=JIUSE_PROVIDER_KEY,
                    external_id=card["video_id"],
                    canonical_url=card.get("page_url"),
                ),
                title=card.get("title") or card["video_id"],
                provenance=(
                    VideoMetadataProvenance(
                        provider_key=JIUSE_PROVIDER_KEY,
                        external_id=card["video_id"],
                        operation=VideoProvenanceOperation.SEARCH,
                        field_name="title",
                        observed_at=observed,
                        confidence=VideoConfidence.MEDIUM,
                    ),
                ),
            )
            for card in window
        )
        return VideoSearchPage(
            items=items,
            page=page,
            page_size=page_size,
            has_next=start + page_size < len(cards),
            total=len(cards),
            query=query,
        )

    async def detail(self, external_id: str) -> VideoDetail:
        if not external_id or not external_id.strip():
            raise _error(ProviderOperation.DETAIL)
        vid = external_id.strip()
        path = self._root / f"detail_{vid}.html"
        if not path.is_file():
            path = self._root / "detail_normal.html"
        try:
            html = path.read_text(encoding="utf-8")
            raw = parse_jiuse_video_html(
                html,
                page_url=f"{self._base}/video/view/{vid}",
                approved_hosts={JIUSE_HOST, "cdn.jiuse.invalid"},
            )
        except (OSError, JiuseParseError, UnicodeError) as exc:
            raise _error(ProviderOperation.DETAIL) from exc
        observed = datetime.now(tz=UTC)
        author = raw.get("author")
        performers = ()
        if isinstance(author, str) and author.strip():
            performers = (
                VideoPerson(
                    provider_key=JIUSE_PROVIDER_KEY,
                    external_id=f"author:{author}",
                    display_name=author,
                    role=VideoPersonRole.PERFORMER,
                ),
            )
        return VideoDetail(
            identifier=VideoIdentifier(
                provider_key=JIUSE_PROVIDER_KEY,
                external_id=str(raw["video_id"]),
                canonical_url=str(raw.get("page_url") or ""),
            ),
            title=str(raw.get("title") or raw["video_id"]),
            performers=performers,
            provenance=(
                VideoMetadataProvenance(
                    provider_key=JIUSE_PROVIDER_KEY,
                    external_id=str(raw["video_id"]),
                    operation=VideoProvenanceOperation.DETAIL,
                    field_name="title",
                    observed_at=observed,
                    confidence=VideoConfidence.HIGH,
                ),
            ),
        )

    async def asset_list(self, external_id: str) -> tuple:
        raise _error(ProviderOperation.ASSET_LIST)

    def _index(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for path in sorted(self._root.glob("detail_*.html")):
            vid = path.stem.removeprefix("detail_")
            try:
                raw = parse_jiuse_video_html(
                    path.read_text(encoding="utf-8"),
                    page_url=f"{self._base}/video/view/{vid}",
                    approved_hosts={JIUSE_HOST, "cdn.jiuse.invalid"},
                )
            except (OSError, JiuseParseError, UnicodeError):
                continue
            cards.append(
                {
                    "video_id": str(raw["video_id"]),
                    "title": str(raw.get("title") or raw["video_id"]),
                    "page_url": str(raw.get("page_url") or ""),
                }
            )
        if not cards and (self._root / "detail_normal.html").is_file():
            raw = parse_jiuse_video_html(
                (self._root / "detail_normal.html").read_text(encoding="utf-8"),
                page_url=f"{self._base}/video/view/V-001",
                approved_hosts={JIUSE_HOST, "cdn.jiuse.invalid"},
            )
            cards.append(
                {
                    "video_id": str(raw["video_id"]),
                    "title": str(raw.get("title") or raw["video_id"]),
                    "page_url": str(raw.get("page_url") or ""),
                }
            )
        return cards


def _error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=JIUSE_PROVIDER_KEY,
            operation=operation,
        )
    )
