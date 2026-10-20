"""Порівняння тексту не повинно ламатися через невидимі bidi-маркери Viber."""
from viber_mcp_service import _match_normalize


def test_isolates_and_nbsp_ignored():
    plain = "👇 ВІДКРИТИ ЧЕК\nhttps://example.invalid/receipt/TEST-FAIL"
    decorated = "👇\u2068 ВІДКРИТИ\u00a0ЧЕК\nhttps://example.invalid/receipt/TEST-FAIL\u2069"
    assert _match_normalize(plain) == _match_normalize(decorated)


def test_different_text_still_differs():
    assert _match_normalize("Оплата 1 грн") != _match_normalize("Оплата 2 грн")


def test_variation_selector_removed():
    assert _match_normalize("✅ Готово") == _match_normalize("✅\ufe0f Готово")
