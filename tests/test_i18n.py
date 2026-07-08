from __future__ import annotations

from app.i18n import TRANSLATIONS, assert_translation_coverage


def test_translation_keys_have_full_coverage() -> None:
    assert assert_translation_coverage(TRANSLATIONS)
