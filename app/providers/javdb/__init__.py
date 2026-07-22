"""JavDB metadata Provider package (TEST_FIXTURE scope).

Real-site connectivity was proven in the companion nsfwpro workspace.
This package uses ``.invalid`` hosts required by TEST_FIXTURE approvals and
does not contact the network. Production hostnames require a separate GOAL.

Attribution (required):
- https://github.com/Yuukiy/JavSP
- https://github.com/lmixture/JavdBviewed
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
