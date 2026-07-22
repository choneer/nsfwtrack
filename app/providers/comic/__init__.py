"""Comic / doujin local-download package (phase D).

Import approval constants lightly; builders via ``package_build`` submodule.
"""

from app.providers.comic.approval import (
    COMIC_APPROVAL,
    COMIC_CAPABILITIES,
    COMIC_ENDPOINT,
    COMIC_PROVIDER_KEY,
)

__all__ = [
    "COMIC_APPROVAL",
    "COMIC_CAPABILITIES",
    "COMIC_ENDPOINT",
    "COMIC_PROVIDER_KEY",
]
