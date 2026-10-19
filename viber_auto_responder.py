"""Autonomous Viber Auto-Responder for Linux MCP.

Listens for incoming Viber messages via D-Bus desktop notifications and responds
with a standard canned template (no LLM intervention required).

Key safety and reliability features:
- Fail-closed kill-switch: VIBER_AUTO_REPLY_ENABLED=1 required (default 0).
- Respects master kill-switch: VIBER_ENABLE_SEND=1 required for actual dispatch.
- Cooldown ledger: Enforces 24h (configurable) per-phone cooldown in SQLite to
  prevent bot loops and spam.
- Serialized UI execution: Acquires inter-process viber_ui_mutex (desktop.lock).
- Native multiline canned response without clipboard / modifier keys.
- Optional webhook forwarding for external systems (e.g. n8n).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any
import urllib.request

_dist_paths = [p for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3.12/dist-packages") if os.path.exists(p)]
for p in _dist_paths:
    if p not in sys.path:
        sys.path.append(p)

try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except Exception:
    dbus = None
    DBusGMainLoop = None
    GLib = None
    DBUS_AVAILABLE = False

for p in _dist_paths:
    if p in sys.path:
        sys.path.remove(p)

from linux_domain import Ledger
from viber_mcp_service import (
    auto,
    get_shared_ledger,
    get_state_dir,
    normalize_phone,
    sync_viber_ui_mutex,
    ViberBusyError,
)

logger = logging.getLogger("viber_auto_responder")

DEFAULT_AUTO_REPLY_TEXT = (
    "Доброго дня!\n"
    "Це автоматичний інформаційний канал сповіщень.\n"
    "На вхідні повідомлення за цим номером відповіді не надаються.\n"
    "Будь ласка, звертайтесь за офіційними контактами підтримки."
)


class ViberAutoResponder:
    def __init__(
        self,
        automation=None,
        ledger: Ledger | None = None,
        reply_text: str | None = None,
        cooldown_hours: float | None = None,
        webhook_url: str | None = None,
    ):
        self.automation = automation or auto
        self.ledger = ledger or get_shared_ledger()
        self._custom_reply_text = reply_text
        self._custom_cooldown_hours = cooldown_hours
        self._custom_webhook_url = webhook_url
        self._dbus_loop = None
        self._dbus_thread = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return os.getenv("VIBER_AUTO_REPLY_ENABLED") == "1"

    @property
    def send_enabled(self) -> bool:
        return os.getenv("VIBER_ENABLE_SEND") == "1"

    @property
    def cooldown_hours(self) -> float:
        if self._custom_cooldown_hours is not None:
            return float(self._custom_cooldown_hours)
        val = os.getenv("VIBER_AUTO_REPLY_COOLDOWN_HOURS", "24.0")
        try:
            return float(val)
        except ValueError:
            return 24.0

    @property
    def reply_text(self) -> str:
        if self._custom_reply_text is not None:
            return self._custom_reply_text
        return os.getenv("VIBER_AUTO_REPLY_TEXT", DEFAULT_AUTO_REPLY_TEXT)

    @property
    def webhook_url(self) -> str | None:
        if self._custom_webhook_url is not None:
            return self._custom_webhook_url
        return os.getenv("VIBER_INCOMING_WEBHOOK_URL") or os.getenv("VIBER_AUTO_REPLY_WEBHOOK_URL")

    def is_running(self) -> bool:
        return self._running and (self._dbus_thread is not None and self._dbus_thread.is_alive())

    def resolve_recipient(self, summary: str, contacts: dict | None = None) -> str | None:
        """Resolve notification summary to an E.164 phone number."""
        clean = summary.strip()
        if not clean:
            return None

        # 1. Direct phone format check
        norm = normalize_phone(clean)
        if norm:
            return norm

        # 2. Check contacts dictionary
        book = contacts if contacts is not None else getattr(self.automation, "contacts", {})
        clean_lower = clean.lower()
        for phone_key, info in book.items():
            if phone_key.lower() == clean_lower:
                return phone_key
            name = info.get("name", "").lower()
            if name == clean_lower or (clean_lower and clean_lower in name):
                return phone_key
            aliases = [a.lower() for a in info.get("aliases", [])]
            if clean_lower in aliases:
                return phone_key

        return None

    def dispatch_webhook(self, payload: dict) -> None:
        """Asynchronously dispatch notification / reply event to webhook URL (fail-safe)."""
        url = self.webhook_url
        if not url:
            return

        def _post():
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json", "User-Agent": "viber-auto-responder/0.3"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    pass
            except Exception as err:
                logger.warning(f"Webhook dispatch failed: {err}")

        threading.Thread(target=_post, daemon=True, name="webhook-dispatch").start()

    def process_incoming_notification(
        self,
        app_name: str,
        summary: str,
        body: str,
    ) -> dict[str, Any]:
        """Core deterministic handler for incoming desktop notifications."""
        # 1. Filter application name
        app_lower = app_name.strip().lower()
        if app_lower not in ("viber", "viberpc"):
            return {"status": "ignored", "reason": "not_viber_app", "app": app_name}

        # 2. Resolve sender
        recipient = self.resolve_recipient(summary)
        if not recipient:
            return {
                "status": "ignored",
                "reason": "unresolved_sender",
                "summary": summary,
                "body": body,
            }

        # 3. Check for self / notes
        if recipient == "self:my-notes":
            return {"status": "ignored", "reason": "self_notes", "sender": recipient}

        # 4. Check master auto-responder kill switch
        if not self.enabled:
            self.dispatch_webhook({
                "event": "incoming_message",
                "sender": recipient,
                "summary": summary,
                "body": body,
                "auto_replied": False,
                "reason": "auto_reply_disabled",
                "timestamp": time.time(),
            })
            return {
                "status": "ignored",
                "reason": "auto_reply_disabled",
                "sender": recipient,
                "body": body,
            }

        # 5. Check cooldown in SQLite ledger
        cooldown = self.cooldown_hours
        if not self.ledger.can_auto_reply(recipient, cooldown_hours=cooldown):
            self.dispatch_webhook({
                "event": "incoming_message",
                "sender": recipient,
                "summary": summary,
                "body": body,
                "auto_replied": False,
                "reason": "cooldown_active",
                "timestamp": time.time(),
            })
            return {
                "status": "skipped",
                "reason": "cooldown_active",
                "sender": recipient,
                "cooldown_hours": cooldown,
            }

        # 6. Check sending kill-switch
        if not self.send_enabled:
            self.dispatch_webhook({
                "event": "incoming_message",
                "sender": recipient,
                "summary": summary,
                "body": body,
                "auto_replied": False,
                "reason": "send_disabled_by_kill_switch",
                "timestamp": time.time(),
            })
            return {
                "status": "blocked",
                "reason": "send_disabled_by_kill_switch",
                "sender": recipient,
            }

        # 7. Execute auto-reply safely under mutex
        text_to_send = self.reply_text
        try:
            with sync_viber_ui_mutex():
                self.automation.open_chat_by_number(recipient)
                try:
                    self.automation.check_recipient_gate(recipient)
                except Exception as e:
                    return {"status": "failed", "reason": "recipient_gate_failed", "error": str(e)}

                self.automation.put_draft(text_to_send)
                send_res = self.automation.send(text_to_send)

            # Record in Ledger to lock cooldown
            self.ledger.record_auto_reply(recipient, text_to_send)

            self.dispatch_webhook({
                "event": "incoming_message",
                "sender": recipient,
                "summary": summary,
                "body": body,
                "auto_replied": True,
                "reply_text": text_to_send,
                "timestamp": time.time(),
            })

            return {
                "status": "sent",
                "sender": recipient,
                "reply_text": text_to_send,
                "details": send_res,
            }

        except Exception as e:
            logger.error(f"Failed to dispatch auto-reply to {recipient}: {e}", exc_info=True)
            return {
                "status": "error",
                "sender": recipient,
                "error": str(e),
            }

    def start_dbus_listener(self) -> bool:
        """Start background D-Bus listener monitoring org.freedesktop.Notifications.Notify."""
        if not DBUS_AVAILABLE:
            logger.error("D-Bus Python bindings not available; cannot start listener")
            return False

        with self._lock:
            if self._running:
                return True

            try:
                DBusGMainLoop(set_as_default=True)
                bus = dbus.SessionBus()
                bus_obj = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
                monitoring = dbus.Interface(bus_obj, "org.freedesktop.DBus.Monitoring")
                monitoring.BecomeMonitor(
                    ["type='method_call',interface='org.freedesktop.Notifications',member='Notify'"],
                    dbus.UInt32(0),
                )

                def _filter(connection, message):
                    try:
                        if (
                            message.get_interface() == "org.freedesktop.Notifications"
                            and message.get_member() == "Notify"
                        ):
                            args = message.get_args_list()
                            app_name = str(args[0]) if len(args) > 0 else ""
                            summary = str(args[3]) if len(args) > 3 else ""
                            body = str(args[4]) if len(args) > 4 else ""

                            # Handle in worker thread to prevent blocking D-Bus event loop
                            threading.Thread(
                                target=self.process_incoming_notification,
                                args=(app_name, summary, body),
                                daemon=True,
                                name="auto-reply-worker",
                            ).start()
                    except Exception as err:
                        logger.error(f"Error in D-Bus message filter: {err}")

                bus.add_message_filter(_filter)

                self._dbus_loop = GLib.MainLoop()
                self._dbus_thread = threading.Thread(
                    target=self._dbus_loop.run,
                    daemon=True,
                    name="viber-dbus-monitor",
                )
                self._dbus_thread.start()
                self._running = True
                logger.info("Viber D-Bus auto-responder listener started successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to start D-Bus monitor: {e}")
                self._running = False
                return False

    def stop_dbus_listener(self) -> None:
        """Stop background D-Bus listener."""
        with self._lock:
            if not self._running:
                return
            if self._dbus_loop and self._dbus_loop.is_running():
                self._dbus_loop.quit()
            if self._dbus_thread and self._dbus_thread.is_alive():
                self._dbus_thread.join(timeout=2.0)
            self._running = False
            logger.info("Viber D-Bus auto-responder listener stopped")


_global_responder: ViberAutoResponder | None = None


def get_auto_responder() -> ViberAutoResponder:
    global _global_responder
    if _global_responder is None:
        _global_responder = ViberAutoResponder()
    return _global_responder


def main():
    parser = argparse.ArgumentParser(description="Viber Auto-Responder daemon & CLI")
    parser.add_argument("--listen", action="store_true", help="Start D-Bus listener daemon")
    parser.add_argument("--test-notify", nargs=3, metavar=("APP", "SUMMARY", "BODY"), help="Simulate incoming notification")
    parser.add_argument("--stats", action="store_true", help="Print auto-reply stats from SQLite ledger")
    args = parser.parse_args()

    responder = get_auto_responder()

    if args.stats:
        stats = responder.ledger.get_auto_reply_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    if args.test_notify:
        app, summary, body = args.test_notify
        res = responder.process_incoming_notification(app, summary, body)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    if args.listen:
        print("Starting Viber Auto-Responder listener...")
        if not responder.start_dbus_listener():
            print("Failed to start listener.")
            sys.exit(1)
        print(f"Listener active. Auto-reply enabled: {responder.enabled}, Cooldown: {responder.cooldown_hours}h")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping...")
            responder.stop_dbus_listener()
            print("Stopped.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
