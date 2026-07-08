from __future__ import annotations

from typing import Any, Literal, TypedDict

from fastapi import Request

from app.i18n import translate


FLASH_SESSION_KEY = "_flash_messages"
FLASH_LEVELS = {"success", "error", "info"}

FlashLevel = Literal["success", "error", "info"]


class RenderedFlash(TypedDict):
    level: str
    message: str


def add_flash(
    request: Request,
    level: FlashLevel,
    key: str,
    **values: str | int | float | bool | None,
) -> None:
    messages = list(request.session.get(FLASH_SESSION_KEY, []))
    messages.append({"level": level, "key": key, "values": values})
    request.session[FLASH_SESSION_KEY] = messages


def pop_flash_messages(request: Request, language: str) -> list[RenderedFlash]:
    raw_messages = request.session.pop(FLASH_SESSION_KEY, [])
    if not isinstance(raw_messages, list):
        return []

    rendered: list[RenderedFlash] = []
    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue
        level = str(raw_message.get("level", "info"))
        if level not in FLASH_LEVELS:
            level = "info"
        key = str(raw_message.get("key", ""))
        values: Any = raw_message.get("values", {})
        if not isinstance(values, dict):
            values = {}
        rendered.append(
            {
                "level": level,
                "message": translate(language, key, **values),
            }
        )
    return rendered
