from __future__ import annotations

from nanobot.i18n import normalize_locale, translate


def test_normalize_locale_handles_language_regions() -> None:
    assert normalize_locale("ko-KR") == "ko"
    assert normalize_locale("en_US") == "en"


def test_translate_formats_catalog_values() -> None:
    assert translate("calendar.conflict.extra_count", locale="ko-KR", count=2) == " 외 2건"
    assert translate("calendar.conflict.extra_count", locale="en-US", count=2) == " plus 2 more"


def test_translate_falls_back_to_english_for_unknown_locale() -> None:
    assert translate("calendar.buttons.cancel", locale="fr-FR") == "Cancel"
