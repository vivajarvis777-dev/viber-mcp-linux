"""Tests for consolidated Viber MCP server (server.py -> viber_mcp_service.py).

Verifies:
1. Single server unification: linux_server delegates to viber_mcp_service; exactly 8 canonical tools.
2. Cross-process / async file mutex serialization on desktop.lock.
3. Shared ledger duplicate protection across transports.
4. Fail-closed gates: VIBER_ENABLE_SEND kill-switch and recipient subscriber gate.
"""
import asyncio
import os
import pathlib
import time
import pytest
from starlette.testclient import TestClient

import server
import linux_server
import viber_mcp_service
from viber_mcp_service import (
    mcp,
    auto,
    viber_ui_mutex,
    ViberBusyError,
    ViberDispatchUnconfirmedError,
    get_lock_file_path,
    get_shared_ledger,
    create_http_app,
    health,
    list_contacts,
    open_chat,
    send_message,
)


def test_single_server_unification():
    """Verify that linux_server is a thin decorator delegating to viber_mcp_service."""
    assert linux_server.mcp is viber_mcp_service.mcp
    assert server.mcp is viber_mcp_service.mcp

    # Check that tool count is exactly 8 canonical tools for Hermes
    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    expected = {
        "health",
        "list_contacts",
        "find_contact",
        "save_contact",
        "open_chat",
        "read_open_chat",
        "put_draft",
        "send_message",
    }
    assert tool_names == expected, f"Unexpected tools: {tool_names}"


@pytest.mark.anyio
async def test_ui_mutex_serialization(tmp_path, monkeypatch):
    """Verify that viber_ui_mutex serializes operations and rejects with busy on timeout."""
    lock_file = tmp_path / "desktop.lock"
    monkeypatch.setenv("VIBER_LOCK_PATH", str(lock_file))

    order = []

    async def op1():
        async with viber_ui_mutex(timeout=1.0):
            order.append("op1_start")
            await asyncio.sleep(0.15)
            order.append("op1_end")

    async def op2():
        await asyncio.sleep(0.03)  # start slightly after op1
        async with viber_ui_mutex(timeout=1.0):
            order.append("op2_start")
            await asyncio.sleep(0.05)
            order.append("op2_end")

    await asyncio.gather(op1(), op2())
    assert order == ["op1_start", "op1_end", "op2_start", "op2_end"], f"Order was not serialized: {order}"


@pytest.mark.anyio
async def test_ui_mutex_busy_timeout(tmp_path, monkeypatch):
    """Verify that when mutex is held longer than timeout, ViberBusyError is raised."""
    lock_file = tmp_path / "desktop.lock"
    monkeypatch.setenv("VIBER_LOCK_PATH", str(lock_file))

    async with viber_ui_mutex(timeout=0.5):
        # Nested / concurrent attempt with 0.1s timeout should fail
        with pytest.raises(ViberBusyError):
            # Bypass asyncio.Lock to simulate another process contending on the file lock
            import fcntl
            fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                deadline = time.monotonic() + 0.1
                while time.monotonic() < deadline:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(0.02)
                else:
                    raise ViberBusyError("Viber UI is busy")
            finally:
                os.close(fd)


def test_shared_ledger_duplicate_blocked(tmp_path, monkeypatch):
    """Verify that duplicate message to same recipient is rejected by shared ledger."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    phone = "+380501234567"
    text = "Important notification text"

    # Mock low-level UI functions so we don't need real Viber window
    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", lambda t: {"drafted": True, "verified": True, "text": t})
    monkeypatch.setattr(auto, "send", lambda t: {"sent": True, "verified": True, "text": t})

    # First send succeeds
    res1 = asyncio.run(send_message(phone, text))
    assert res1["ok"] is True
    assert res1["sent"] is True

    # Second send with same text and recipient is blocked
    res2 = asyncio.run(send_message(phone, text))
    assert res2["ok"] is False
    assert res2["code"] == "duplicate_blocked"
    assert "blocked by ledger" in res2["error"]

    # Different text to same recipient is allowed
    res3 = asyncio.run(send_message(phone, "Different text"))
    assert res3["ok"] is True
    assert res3["sent"] is True


def test_fail_closed_send_disabled(tmp_path, monkeypatch):
    """Verify that VIBER_ENABLE_SEND != '1' blocks sending fail-closed."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "0")

    res = asyncio.run(send_message("+380501234567", "Hello"))
    assert res["ok"] is False
    assert res["code"] == "send_disabled"


def test_dry_run_allows_draft_when_send_disabled(tmp_path, monkeypatch):
    """Verify that dry_run=True allows drafting and verification without sending."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "0")

    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", lambda t: {"drafted": True, "verified": True, "text": t})

    res = asyncio.run(send_message("+380501234567", "Dry run text", dry_run=True))
    assert res["ok"] is True
    assert res["dry_run"] is True
    assert res["drafted"] is True


def test_recipient_gate_rejects_non_subscriber(monkeypatch):
    """Verify that recipient not on Viber is rejected fail-closed."""
    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    # Simulate Viber UI showing "isn't on Viber"
    monkeypatch.setattr(auto, "read_messages", lambda: ["The user isn't on Viber", "Invite to Viber"])

    # 1. open_chat fails closed
    res_open = asyncio.run(open_chat("+380501234567"))
    assert res_open["ok"] is False
    assert res_open["code"] == "recipient_not_on_viber"

    # 2. send_message fails closed
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")
    res_send = asyncio.run(send_message("+380501234567", "Cannot send"))
    assert res_send["ok"] is False
    assert res_send["code"] == "recipient_not_on_viber"


def test_http_health_no_gui(monkeypatch):
    """Verify that GET /health requires Bearer auth and returns status without GUI actions."""
    token = "secret-token-xyz"
    app = create_http_app(token)
    client = TestClient(app)

    # Missing token -> 401
    assert client.get("/health").status_code == 401

    # Invalid token -> 401
    assert client.get("/health", headers={"Authorization": "Bearer bad"}).status_code == 401

    # Valid token -> 200
    r = client.get("/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["platform"] == "linux"
    assert "read_available" in data
    assert "send_enabled" in data
    assert "viber_window_found" in data


def test_concurrent_send_race_condition_blocked(tmp_path, monkeypatch):
    """Verify that two concurrent send requests for the same recipient and text
    cannot race through; one succeeds and the other is strictly blocked by the ledger under mutex.
    """
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    phone = "+380509998877"
    text = "Payment details: 1000 UAH"

    # Mock low-level UI functions with artificial delay inside mutex to simulate real UI interaction
    def slow_open(p):
        time.sleep(0.05)

    def slow_send(t):
        time.sleep(0.05)
        return {"sent": True, "verified": True, "text": t}

    monkeypatch.setattr(auto, "open_chat_by_number", slow_open)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", lambda t: {"drafted": True, "verified": True, "text": t})
    monkeypatch.setattr(auto, "send", slow_send)

    async def run_concurrent():
        return await asyncio.gather(
            send_message(phone, text),
            send_message(phone, text),
        )

    results = asyncio.run(run_concurrent())
    oks = [r for r in results if r.get("ok") is True]
    dups = [r for r in results if r.get("code") == "duplicate_blocked"]

    assert len(oks) == 1, f"Expected exactly 1 success, got: {results}"
    assert len(dups) == 1, f"Expected exactly 1 duplicate blocked, got: {results}"
    assert oks[0]["sent"] is True


def test_idempotency_key_cached_response(tmp_path, monkeypatch):
    """Verify that passing an idempotency_key returns cached results on repeat without re-dispatching."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    phone = "+380501112233"
    text = "Invoice #1042 details"
    key = "inv-1042-uuid"

    send_count = 0

    def mock_send(t):
        nonlocal send_count
        send_count += 1
        return {"sent": True, "verified": True, "text": t}

    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", lambda t: {"drafted": True, "verified": True, "text": t})
    monkeypatch.setattr(auto, "send", mock_send)

    # 1. Initial send
    res1 = asyncio.run(send_message(phone, text, idempotency_key=key))
    assert res1["ok"] is True
    assert res1["sent"] is True
    assert send_count == 1

    # 2. Replay with same idempotency key
    res2 = asyncio.run(send_message(phone, text, idempotency_key=key))
    assert res2["ok"] is True
    assert res2.get("cached") is True
    assert res2.get("idempotency_key") == key
    # send was NOT called again
    assert send_count == 1


def test_unconfirmed_dispatch_blocks_retry(tmp_path, monkeypatch):
    """Verify that an ambiguous failure post-dispatch returns send_unconfirmed and blocks automatic retry."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    phone = "+380503334455"
    text = "Critical transaction alert"

    def fail_after_dispatch(t):
        raise ViberDispatchUnconfirmedError("Readback verification timeout after Return key")

    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", lambda t: {"drafted": True, "verified": True, "text": t})
    monkeypatch.setattr(auto, "send", fail_after_dispatch)

    # 1. Dispatch fails ambiguously
    res1 = asyncio.run(send_message(phone, text))
    assert res1["ok"] is False
    assert res1["code"] == "send_unconfirmed"
    assert res1["can_retry"] is False

    # 2. Subsequent automatic retry MUST be blocked as duplicate
    res2 = asyncio.run(send_message(phone, text))
    assert res2["ok"] is False
    assert res2["code"] == "duplicate_blocked"


def test_pre_dispatch_failure_allows_retry(tmp_path, monkeypatch):
    """Verify that a pre-dispatch error (before Return) allows retry."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    phone = "+380503334455"
    text = "Draft test"

    def fail_draft(t):
        raise RuntimeError("Draft text mismatch before send")

    monkeypatch.setattr(auto, "open_chat_by_number", lambda p: None)
    monkeypatch.setattr(auto, "check_recipient_gate", lambda p: None)
    monkeypatch.setattr(auto, "put_draft", fail_draft)

    res = asyncio.run(send_message(phone, text))
    assert res["ok"] is False
    assert res["code"] == "send_failed_pre_dispatch"
    assert res["can_retry"] is True

