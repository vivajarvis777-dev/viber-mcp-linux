"""Tests for Viber chat switching via UI search and round-trip verification."""
import os
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

import viber_mcp_service
from viber_mcp_service import ViberAutomation, open_chat


def test_find_result_card_detects_card_center():
    """Verify that _find_result_card detects the vertical center of result cards."""
    # Create synthetic image with white background (300 x 450)
    img = Image.new("RGB", (300, 450), color=(255, 255, 255))
    
    # Draw a card between y=120 and y=180 (center y=150)
    for y in range(120, 181):
        for x in range(30, 270):
            img.putpixel((x, y), (240, 245, 250))
            
    detected_y = ViberAutomation._find_result_card(img)
    assert detected_y is not None
    assert abs(detected_y - 150) <= 2, f"Expected center ~150, got {detected_y}"


def test_find_result_card_returns_none_on_blank():
    """Verify that _find_result_card returns None when no card is present."""
    blank = Image.new("RGB", (300, 450), color=(255, 255, 255))
    assert ViberAutomation._find_result_card(blank) is None


@pytest.mark.anyio
async def test_open_chat_calls_ui_search_first():
    """Verify open_chat_by_number executes calibrated UI search as primary path."""
    auto = ViberAutomation()
    auto.contacts = {
        "+380991112233": {"name": "Test User", "ref_image": None}
    }
    auto.current_phone = "+380990000000"

    with patch.object(auto, "navigate_via_ui_search", return_value=True) as mock_search, \
         patch.object(auto, "_navigate_via_uri") as mock_uri, \
         patch.object(auto, "_verify_chat_switch", return_value=True):
        
        auto.open_chat_by_number("+380991112233")
        mock_search.assert_called_once_with("+380991112233")
        mock_uri.assert_not_called()
        assert auto.current_phone == "+380991112233"


@pytest.mark.anyio
async def test_open_chat_fallback_to_uri():
    """Verify open_chat_by_number falls back to URI handoff if UI search fails."""
    auto = ViberAutomation()
    auto.contacts = {
        "+380991112233": {"name": "Test User", "ref_image": None}
    }
    auto.current_phone = "+380990000000"

    with patch.object(auto, "navigate_via_ui_search", side_effect=RuntimeError("search failed")), \
         patch.object(auto, "_navigate_via_uri") as mock_uri, \
         patch.object(auto, "_verify_chat_switch", return_value=True):
        
        auto.open_chat_by_number("+380991112233")
        mock_uri.assert_called_once_with("+380991112233")
        assert auto.current_phone == "+380991112233"


@pytest.mark.anyio
async def test_open_chat_returns_chat_switch_failed_code():
    """Verify open_chat tool returns code: chat_switch_failed when neither path works."""
    with patch.object(viber_mcp_service.auto, "open_chat_by_number",
                      side_effect=RuntimeError("chat_switch_failed: could not switch")), \
         patch("viber_mcp_service.viber_ui_mutex"):
        
        res = await open_chat("+380991112233")
        assert res["ok"] is False
        assert res["code"] == "chat_switch_failed"
        assert "chat_switch_failed" in res["error"]


@pytest.mark.skipif(os.getenv("VIBER_ALLOW_GUI") != "1", reason="Live X11 Viber required")
def test_round_trip_chat_switch_live():
    """Live E2E test: open chat A -> open chat B -> open chat A with header verification."""
    phone_a = "+380981901991"
    phone_b = "+380674032750"

    auto = ViberAutomation(display=os.getenv("DISPLAY", ":10"))

    # 1. Switch to Chat A
    auto.open_chat_by_number(phone_a)
    assert auto.verify_header_contact(phone_a, timeout=2.0), f"Header for {phone_a} did not match"
    assert not auto.verify_header_contact(phone_b, timeout=0.5), f"Header for {phone_b} unexpectedly matched"

    # 2. Switch to Chat B
    auto.open_chat_by_number(phone_b)
    assert auto.verify_header_contact(phone_b, timeout=2.0), f"Header for {phone_b} did not match"
    assert not auto.verify_header_contact(phone_a, timeout=0.5), f"Header for {phone_a} unexpectedly matched"

    # 3. Switch back to Chat A
    auto.open_chat_by_number(phone_a)
    assert auto.verify_header_contact(phone_a, timeout=2.0), f"Header for {phone_a} did not match on switch-back"
    assert not auto.verify_header_contact(phone_b, timeout=0.5), f"Header for {phone_b} unexpectedly matched"
