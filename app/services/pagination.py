from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class PageInfo:
    page: int
    page_size: int
    total: int
    total_pages: int
    page_numbers: tuple[int, ...]

    @property
    def start(self) -> int:
        if self.total == 0:
            return 0
        return ((self.page - 1) * self.page_size) + 1

    @property
    def end(self) -> int:
        return min(self.page * self.page_size, self.total)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def parse_page(value: str | int | None) -> int:
    try:
        parsed = int(value) if value not in {None, ""} else 1
    except (TypeError, ValueError):
        return 1
    return max(parsed, 1)


def build_page_info(
    *,
    page: str | int | None,
    page_size: int,
    total: int,
) -> PageInfo:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    safe_total = max(int(total), 0)
    total_pages = max(ceil(safe_total / page_size), 1)
    current_page = min(parse_page(page), total_pages)
    start = max(1, current_page - 2)
    end = min(total_pages, start + 4)
    start = max(1, end - 4)
    return PageInfo(
        page=current_page,
        page_size=page_size,
        total=safe_total,
        total_pages=total_pages,
        page_numbers=tuple(range(start, end + 1)),
    )
