"""JavDB metadata Provider package (TEST_FIXTURE + PRODUCTION submodule).

Heavy builders live in submodule imports to avoid package-init cycles:
- ``app.providers.javdb.production``
- ``app.providers.javdb.package_build``
- ``app.providers.javdb.live_adapter``
"""

from app.providers.javdb.adapter import JavDBFixtureVideoMetadataAdapter
from app.providers.javdb.approval import (
    JAVDB_APPROVAL,
    JAVDB_CAPABILITIES,
    JAVDB_ENDPOINT,
    JAVDB_PROVIDER_KEY,
)

__all__ = [
    "JAVDB_APPROVAL",
    "JAVDB_CAPABILITIES",
    "JAVDB_ENDPOINT",
    "JAVDB_PROVIDER_KEY",
    "JavDBFixtureVideoMetadataAdapter",
]
