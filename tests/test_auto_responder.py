"""Tests for autonomous Viber Auto-Responder (feat/viber-auto-responder).

Verifies:
1. SQLite Ledger cooldown tracking, deduplication, and stats.
2. Sender phone resolution from E.164 digits, local format, or contacts book.
3. Strict fail-closed kill-switches (VIBER_AUTO_REPLY_ENABLED and VIBER_ENABLE_SEND).
4. Full dispatch cycle with UI serialization and canned multiline response.
5. Cooldown enforcement preventing infinite bot-to-bot loops.
6. Non-Viber notification filtering.
7. Health reporting integration.
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from linux_domain import Ledger
from viber_auto_responder import (
    DEFAULT_AUTO_REPLY_TEXT,
    ViberAutoResponder,
    get_auto_responder,
)
import viber_mcp_service
from viber_mcp_service import health, ViberDispatchUnconfirmedError


class MockAutomation:
    def __init__(self, contacts=None):
        self.contacts = contacts or {
            "+380981901991": {"name": "Юрій", "aliases": ["yurko", "admin"]},
            "+380501112233": {"name": "Марія", "aliases": ["maria"]},
        }
        self.calls = []
        self.sent_messages = []
        self.drafted = None

    def open_chat_by_number(self, phone: str):
        self.calls.append(("open_chat_by_number", phone))

    def check_recipient_gate(self, phone: str):
        self.calls.append(("check_recipient_gate", phone))

    def put_draft(self, text: str):
        self.calls.append(("put_draft", text))
        self.drafted = text
        return {"drafted": True, "verified": True, "text": text}

    def send(self, text: str):
        self.calls.append(("send", text))
        self.sent_messages.append(text)
        return {"sent": True, "verified": True, "text": text}


def test_ledger_auto_reply_cooldown_and_stats(tmp_path):
    """Verify Ledger accurately tracks cooldown windows and auto-reply counts."""
    state_dir = tmp_path / "state"
    ledger = Ledger(state_dir)
    phone = "+380981901991"

    # Initially, can auto-reply
    assert ledger.can_auto_reply(phone, cooldown_hours=24.0) is True

    # Record first auto-reply
    ledger.record_auto_reply(phone, "Перша відповідь")

    # Immediate next check within 24h must be blocked
    assert ledger.can_auto_reply(phone, cooldown_hours=24.0) is False
    assert ledger.can_auto_reply(phone, cooldown_hours=1.0) is False

    # Check stats
    stats = ledger.get_auto_reply_stats()
    assert stats["unique_recipients"] == 1
    assert stats["total_replies_sent"] == 1
    assert stats["recent"][0]["phone"] == phone
    assert stats["recent"][0]["reply_count"] == 1

    # Record second auto-reply to same phone
    ledger.record_auto_reply(phone, "Друга відповідь")
    stats2 = ledger.get_auto_reply_stats()
    assert stats2["unique_recipients"] == 1
    assert stats2["total_replies_sent"] == 2
    assert stats2["recent"][0]["reply_count"] == 2

    # Disabling cooldown must not bypass the one-time limit.
    assert ledger.can_auto_reply(phone, cooldown_hours=0) is False


def test_recipient_resolution(tmp_path):
    """Verify resolution of notifications to canonical E.164 phone numbers."""
    automation = MockAutomation()
    responder = ViberAutoResponder(automation=automation)

    # 1. Direct E.164 number in notification summary
    assert responder.resolve_recipient("+380981901991") == "+380981901991"

    # 2. Local Ukrainian 10-digit number
    assert responder.resolve_recipient("0981901991") == "+380981901991"

    # 3. Known contact name from address book
    assert responder.resolve_recipient("Юрій") == "+380981901991"
    assert responder.resolve_recipient("юрій") == "+380981901991"

    # 4. Known contact alias from address book
    assert responder.resolve_recipient("yurko") == "+380981901991"

    # 5. Unknown contact name not in address book
    assert responder.resolve_recipient("Невідомий Абонент") is None
    assert responder.resolve_recipient("") is None


def test_ignore_non_viber_apps(tmp_path):
    """Verify notifications from other desktop apps are silently ignored."""
    automation = MockAutomation()
    responder = ViberAutoResponder(automation=automation)

    res = responder.process_incoming_notification("Telegram", "+380981901991", "Hello")
    assert res["status"] == "ignored"
    assert res["reason"] == "not_viber_app"

    res_slack = responder.process_incoming_notification("Slack", "Channel", "Ping")
    assert res_slack["status"] == "ignored"
    assert res_slack["reason"] == "not_viber_app"


def test_auto_reply_disabled_by_kill_switch(tmp_path, monkeypatch):
    """Verify that VIBER_AUTO_REPLY_ENABLED=0 blocks auto-responder."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "0")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    res = responder.process_incoming_notification("Viber", "+380981901991", "Питання по рахунку")
    assert res["status"] == "ignored"
    assert res["reason"] == "auto_reply_disabled"
    assert len(automation.calls) == 0


def test_send_disabled_by_master_kill_switch(tmp_path, monkeypatch):
    """Verify that VIBER_ENABLE_SEND=0 blocks dispatch even if auto-responder is on."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "0")

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    res = responder.process_incoming_notification("Viber", "+380981901991", "Доброго дня")
    assert res["status"] == "blocked"
    assert res["reason"] == "send_disabled_by_kill_switch"
    assert len(automation.sent_messages) == 0


def test_successful_auto_reply_and_cooldown_loop_prevention(tmp_path, monkeypatch):
    """Verify successful auto-reply and subsequent loop prevention by cooldown."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")
    monkeypatch.setenv("VIBER_AUTO_REPLY_COOLDOWN_HOURS", "24.0")

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    phone = "+380981901991"

    # 1. First incoming message -> Auto-reply is sent
    res1 = responder.process_incoming_notification("Viber", phone, "Коли буде замовлення?")
    assert res1["status"] == "sent"
    assert res1["sender"] == phone
    assert DEFAULT_AUTO_REPLY_TEXT in res1["reply_text"]
    assert len(automation.sent_messages) == 1
    assert automation.sent_messages[0] == DEFAULT_AUTO_REPLY_TEXT

    # 2. Second incoming message (or loop feedback) -> Blocked by 24h cooldown
    res2 = responder.process_incoming_notification("Viber", phone, "Дякую, зрозумів")
    assert res2["status"] == "skipped"
    assert res2["reason"] == "cooldown_active"
    assert len(automation.sent_messages) == 1  # Not sent again!

    # 3. Third incoming message from a DIFFERENT recipient -> Allowed
    res3 = responder.process_incoming_notification("Viber", "+380501112233", "Привіт")
    assert res3["status"] == "sent"
    assert res3["sender"] == "+380501112233"
    assert len(automation.sent_messages) == 2


def test_custom_reply_text_multiline(tmp_path, monkeypatch):
    """Verify custom multiline reply template is respected."""
    state_dir = tmp_path / "state"
    custom_text = "Рядок 1: Канал сповіщень\nРядок 2: На відповіді не розраховуйте\nРядок 3: Дякуємо"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")
    monkeypatch.setenv("VIBER_AUTO_REPLY_TEXT", custom_text)

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    res = responder.process_incoming_notification("ViberPC", "0981901991", "Тест")
    assert res["status"] == "sent"
    assert res["reply_text"] == custom_text
    assert automation.sent_messages[0] == custom_text


def test_webhook_forwarding(tmp_path, monkeypatch):
    """Verify optional incoming webhook payload dispatch."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")
    monkeypatch.setenv("VIBER_INCOMING_WEBHOOK_URL", "http://127.0.0.1:9999/webhook")

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    dispatched = []

    def mock_dispatch(payload):
        dispatched.append(payload)

    responder.dispatch_webhook = mock_dispatch

    responder.process_incoming_notification("Viber", "+380981901991", "Webhook test message")
    assert len(dispatched) == 1
    assert dispatched[0]["event"] == "incoming_message"
    assert dispatched[0]["sender"] == "+380981901991"
    assert dispatched[0]["auto_replied"] is True


@pytest.mark.anyio
async def test_health_reports_auto_responder_status(tmp_path, monkeypatch):
    """Verify health() tool includes auto_responder block with stats."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    res = await health()
    assert res["status"] == "ok"
    assert "auto_responder" in res
    ar = res["auto_responder"]
    assert ar["enabled"] is True
    assert "running" in ar
    assert "cooldown_hours" in ar
    assert "stats" in ar


def test_auto_responder_unconfirmed_dispatch_locks_cooldown(tmp_path, monkeypatch):
    """Verify that an unconfirmed dispatch in auto-responder locks cooldown to prevent spam loops."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")

    automation = MockAutomation()

    def mock_fail_unconfirmed(text):
        raise ViberDispatchUnconfirmedError("History check timed out after send key")

    automation.send = mock_fail_unconfirmed

    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    # 1. First dispatch raises unconfirmed
    res1 = responder.process_incoming_notification("Viber", "+380981901991", "Hello")
    assert res1["status"] == "unconfirmed"
    assert res1["can_retry"] is False

    # 2. Cooldown is still locked in ledger!
    assert ledger.can_auto_reply("+380981901991", cooldown_hours=24.0) is False

    # 3. Subsequent message from same phone is skipped by cooldown
    res2 = responder.process_incoming_notification("Viber", "+380981901991", "Hello again")
    assert res2["status"] == "skipped"
    assert res2["reason"] == "cooldown_active"


def test_max_replies_limit_and_reset(tmp_path, monkeypatch):
    """Only one automatic reply; even a stale 5-reply override cannot weaken it."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")
    monkeypatch.setenv("VIBER_AUTO_REPLY_COOLDOWN_HOURS", "0")
    monkeypatch.setenv("VIBER_AUTO_REPLY_MAX_COUNT", "5")

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger, cooldown_hours=0, max_replies=5)

    phone = "+380981901991"

    # First inbound gets a reply; the next is suppressed even with zero cooldown.
    first = responder.process_incoming_notification("Viber", phone, "Message 1")
    assert first["status"] == "sent"
    second = responder.process_incoming_notification("Viber", phone, "Message 2")
    assert second["status"] == "skipped"
    assert second["reason"] == "cooldown_active"
    assert len(automation.sent_messages) == 1

    # Explicit operator reset restores eligibility.
    ledger.reset_auto_reply(phone)
    assert ledger.can_auto_reply(phone, cooldown_hours=0) is True

    after_reset = responder.process_incoming_notification("Viber", phone, "Message after reset")
    assert after_reset["status"] == "sent"
    assert len(automation.sent_messages) == 2


def test_any_inbound_no_iban_gate(tmp_path, monkeypatch):
    """Any sender may receive one reply; prior IBAN delivery is not required."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("VIBER_AUTO_REPLY_ENABLED", "1")
    monkeypatch.setenv("VIBER_ENABLE_SEND", "1")
    monkeypatch.setenv("VIBER_AUTO_REPLY_REQUIRE_IBAN", "1")  # obsolete flag must not restrict scope
    monkeypatch.setenv("VIBER_AUTO_REPLY_COOLDOWN_HOURS", "0")
    monkeypatch.setenv("VIBER_AUTO_REPLY_MAX_COUNT", "5")  # obsolete override must not permit extra replies

    automation = MockAutomation()
    ledger = Ledger(state_dir)
    responder = ViberAutoResponder(automation=automation, ledger=ledger)

    phone = "+380000000000"

    # A synthetic sender with no historical payment/outbox record.
    assert ledger.has_iban_history(phone) is False
    res = responder.process_incoming_notification("Viber", phone, "Перше питання")
    assert res["status"] == "sent"
    assert len(automation.sent_messages) == 1

    # A later inbound message must not generate another automatic reply.
    res2 = responder.process_incoming_notification("Viber", phone, "Ще питання")
    assert res2["status"] == "skipped"
    assert len(automation.sent_messages) == 1
    assert "Павло, Viva!Gas — 067 238 2080" in automation.sent_messages[0]


@pytest.mark.anyio
async def test_mcp_tools_stats_and_reset(tmp_path, monkeypatch):
    """Verify get_auto_responder_stats and reset_auto_reply_limit MCP tools."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("VIBER_STATE_DIR", str(state_dir))

    from viber_mcp_service import get_auto_responder_stats, reset_auto_reply_limit
    ledger = Ledger(state_dir)
    monkeypatch.setattr("viber_mcp_service.get_shared_ledger", lambda: ledger)

    phone = "+380981901991"
    ledger.record_auto_reply(phone, "Test message")

    stats = await get_auto_responder_stats()
    assert stats["ok"] is True
    assert stats["unique_recipients"] == 1
    assert stats["total_replies_sent"] == 1

    reset_res = await reset_auto_reply_limit(phone)
    assert reset_res["ok"] is True
    assert reset_res["reset"] is True

    stats_after = await get_auto_responder_stats()
    assert stats_after["unique_recipients"] == 0


