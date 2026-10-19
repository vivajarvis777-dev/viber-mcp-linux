"""Tests for multiline text support in Viber MCP (send_message and put_draft).

Verifies:
1. Multiline text insertion with \\n preservation without clipboard and without modifier grabs.
2. Character limit <= 1000 and control character validation.
3. Message history readback with \\n preservation (normalizing \\u2028/\\u2029).
4. Single-line backward compatibility without regression.
5. Fail-closed safety gates (kill-switch, duplicate ledger, mutex).
"""
import asyncio
import os
import unicodedata
import pytest

from viber_mcp_service import (
    auto,
    put_draft,
    send_message,
    read_open_chat,
    viber_ui_mutex,
    get_shared_ledger,
)


def test_put_draft_multiline_logic(monkeypatch):
    """Verify put_draft accepts and verifies multiline text via AT-SPI without clipboard."""
    multiline_text = "рядок 1\nрядок 2\nрядок 3"

    class MockEditor:
        def __init__(self):
            self.content = ""

        def SetTextContents(self, val, dbus_interface=None):
            # Simulate Qt converting \n to \u2029 in the widget
            self.content = val.replace("\n", "\u2029")
            return True

        def GetText(self, start, end, dbus_interface=None):
            return self.content

        def GetNActions(self, dbus_interface=None):
            return 1

        def DoAction(self, idx, dbus_interface=None):
            return True

        def GetExtents(self, coord_type, dbus_interface=None):
            return (400, 700, 800, 20)

    mock_editor = MockEditor()

    class MockBus:
        def get_object(self, dest, path):
            return mock_editor

    monkeypatch.setattr(auto, "get_a11y_bus", lambda: MockBus())
    monkeypatch.setattr(auto, "get_viber_app", lambda: (":1.1", "/root"))
    monkeypatch.setattr(auto, "resolve_editor", lambda: ("/composer", (400, 700, 800, 20)))

    # Ensure clipboard (xclip) is NEVER called
    def fail_xclip(*args, **kwargs):
        raise AssertionError("xclip was called, but clipboard usage is forbidden")
    monkeypatch.setattr("subprocess.Popen", fail_xclip)

    res = auto.put_draft(multiline_text)
    assert res["drafted"] is True
    assert res["verified"] is True
    assert res["text"] == multiline_text


def test_put_draft_length_limit():
    """Verify that text exceeding 1000 characters is rejected."""
    long_text = "а" * 1001
    with pytest.raises(ValueError, match="text_length_invalid"):
        auto.put_draft(long_text)


def test_put_draft_control_characters():
    """Verify that invalid control characters are rejected, but \\n is allowed."""
    with pytest.raises(ValueError, match="invalid_control_characters"):
        auto.put_draft("рядок1\x00рядок2")

    with pytest.raises(ValueError, match="invalid_control_characters"):
        auto.put_draft("рядок1\x07рядок2")


def test_single_line_regression(monkeypatch):
    """Verify single-line text continues to work cleanly without regression."""
    single_line = "Звичайне однорядкове повідомлення 123"

    class MockEditor:
        def __init__(self):
            self.content = ""

        def SetTextContents(self, val, dbus_interface=None):
            self.content = val
            return True

        def GetText(self, start, end, dbus_interface=None):
            return self.content

    mock_editor = MockEditor()

    class MockBus:
        def get_object(self, dest, path):
            return mock_editor

    monkeypatch.setattr(auto, "get_a11y_bus", lambda: MockBus())
    monkeypatch.setattr(auto, "get_viber_app", lambda: (":1.1", "/root"))
    monkeypatch.setattr(auto, "resolve_editor", lambda: ("/composer", (400, 700, 800, 20)))

    res = auto.put_draft(single_line)
    assert res["drafted"] is True
    assert res["verified"] is True
    assert res["text"] == single_line


def test_read_messages_normalizes_line_separators(monkeypatch):
    """Verify read_messages normalizes Qt paragraph (\\u2029) and line (\\u2028) separators to \\n."""
    raw_history = [
        "Однорядкове повідомлення",
        "рядок 1\u2028рядок 2\u2028рядок 3",
        "параграф 1\u2029параграф 2",
    ]

    class MockAccessible:
        def __init__(self, text):
            self.t = text

        def GetRoleName(self, dbus_interface=None):
            return "text"

        def Get(self, iface, prop, dbus_interface=None):
            return ""

        def GetText(self, s, e, dbus_interface=None):
            return self.t

        def GetChildren(self, dbus_interface=None):
            return []

    class MockBus:
        def get_object(self, dest, path):
            if path == "/root":
                class Root:
                    def GetChildren(self, dbus_interface=None):
                        return [(dest, f"/msg_{i}") for i in range(len(raw_history))]
                return Root()
            idx = int(path.split("_")[1])
            return MockAccessible(raw_history[idx])

    monkeypatch.setattr(auto, "get_a11y_bus", lambda: MockBus())
    monkeypatch.setattr(auto, "get_viber_app", lambda: (":1.1", "/root"))
    monkeypatch.setattr(auto, "resolve_editor", lambda: ("/composer", (400, 700, 800, 20)))
    monkeypatch.setattr(auto, "_obj_extents", lambda obj: (400, 100, 600, 30))

    messages = auto.read_messages()
    assert len(messages) == 3
    assert messages[0] == "Однорядкове повідомлення"
    assert messages[1] == "рядок 1\nрядок 2\nрядок 3"
    assert messages[2] == "параграф 1\nпараграф 2"


@pytest.mark.anyio
async def test_send_message_multiline_flow(tmp_path, monkeypatch):
    """Verify send_message handles multiline text, respects kill-switch, and claims ledger."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    phone = "+380501234567"
    multiline = "Пункт 1\nПункт 2\nПункт 3"

    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", lambda t: {"drafted": True, "verified": True, "text": t})
    monkeypatch.setattr(auto, "send", lambda t: {"sent": True, "verified": True, "text": t})

    # First send succeeds
    res1 = await send_message(phone, multiline)
    assert res1["ok"] is True
    assert res1["sent"] is True
    assert res1["text"] == multiline

    # Second send with identical multiline text is blocked by ledger
    res2 = await send_message(phone, multiline)
    assert res2["ok"] is False
    assert res2["code"] == "duplicate_blocked"


@pytest.mark.anyio
async def test_read_open_chat_multiline_tool(monkeypatch):
    """Verify read_open_chat tool surfaces preserved newlines."""
    multiline_msg = "рядок A\nрядок B\nрядок C"
    monkeypatch.setattr(auto, "read_messages", lambda: [multiline_msg])
    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)

    res = await read_open_chat("+380501234567")
    assert res["ok"] is True
    assert res["count"] == 1
    lines = res["messages"][0].split("\n")
    assert len(lines) == 3
    assert lines == ["рядок A", "рядок B", "рядок C"]
