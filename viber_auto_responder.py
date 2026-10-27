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
import re
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
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except Exception:
    dbus = None
    DBusGMainLoop = None
    GLib = None
    DBUS_AVAILABLE = False


if DBUS_AVAILABLE:
    class NotificationServer(dbus.service.Object):
        """Notification service sink claiming org.freedesktop.Notifications on session bus."""
        def __init__(self, responder, bus):
            self.responder = responder
            self._next_id = 1
            bus_name = dbus.service.BusName("org.freedesktop.Notifications", bus)
            super().__init__(bus_name, "/org/freedesktop/Notifications")

        @dbus.service.method("org.freedesktop.Notifications", in_signature="", out_signature="as")
        def GetCapabilities(self):
            return ["body", "body-markup", "actions"]

        @dbus.service.method("org.freedesktop.Notifications", in_signature="", out_signature="ssss")
        def GetServerInformation(self):
            return ("Viber Auto Responder", "VivaGas", "1.0", "1.2")

        @dbus.service.method("org.freedesktop.Notifications", in_signature="susssasa{sv}i", out_signature="u")
        def Notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout):
            nid = self._next_id
            self._next_id += 1
            logger.info(f"Received Notify call: app={app_name}, summary={summary}, body={body}")
            threading.Thread(
                target=self.responder.process_incoming_notification,
                args=(str(app_name), str(summary), str(body)),
                daemon=True,
                name="auto-reply-worker",
            ).start()
            return dbus.UInt32(nid)

        @dbus.service.method("org.freedesktop.Notifications", in_signature="u", out_signature="")
        def CloseNotification(self, id):
            pass
else:
    NotificationServer = None

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
    ViberDispatchUnconfirmedError,
)

logger = logging.getLogger("viber_auto_responder")

DEFAULT_AUTO_REPLY_TEXT = (
    "🤖 Дякуємо за повідомлення! Це автоматичний канал Viva!Gas, тому відповіді по суті в цьому чаті не буде. "
    "Для подальшого спілкування зателефонуйте або напишіть: 067 238 2080."
)


class ViberAutoResponder:
    def __init__(
        self,
        automation=None,
        ledger: Ledger | None = None,
        reply_text: str | None = None,
        cooldown_hours: float | None = None,
        webhook_url: str | None = None,
        max_replies: int | None = None,
    ):
        self.automation = automation or auto
        self.ledger = ledger or get_shared_ledger()
        self._custom_reply_text = reply_text
        self._custom_cooldown_hours = cooldown_hours
        self._custom_webhook_url = webhook_url
        self._custom_max_replies = max_replies
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
    def max_replies(self) -> int:
        # Automated replies are one-time. A stale environment override must not increase this.
        return 1

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
        clean = re.sub(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', summary).strip()
        if not clean:
            return None

        # A notification title is not a phone if it contains free text or a group name.
        # Accept only a literal phone-like title (plus digits, spaces, hyphens, parentheses).
        if re.fullmatch(r"\+?[0-9][0-9 ()-]{7,24}", clean):
            norm = normalize_phone(clean)
            if norm:
                return norm

        # 2. Check contacts dictionary
        book = contacts if contacts is not None else getattr(self.automation, "contacts", {})
        if not book:
            for candidate in [
                os.getenv("VIBER_CONTACTS_FILE"),
                Path(__file__).parent / "contacts.json",
                Path.home() / ".local/state/viber-mcp-linux/contacts.json",
                Path("/home/hannelora/projects/viber-mcp-linux-ocr-release/contacts.json"),
            ]:
                if candidate and os.path.exists(candidate):
                    try:
                        with open(candidate, "r", encoding="utf-8") as f:
                            book = json.load(f)
                            break
                    except Exception:
                        pass
        clean_lower = clean.casefold()
        matches = set()
        for phone_key, info in book.items():
            name = str(info.get("name", "")).casefold()
            aliases = {str(alias).casefold() for alias in info.get("aliases", [])}
            if clean_lower == phone_key.casefold() or (name and clean_lower == name) or clean_lower in aliases:
                matches.add(phone_key)
        # A partial or ambiguous contact label cannot authorize an outbound reply.
        return next(iter(matches)) if len(matches) == 1 else None

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
            logger.warning(f"Unresolved sender for summary: {repr(summary)}")
            return {
                "status": "ignored",
                "reason": "unresolved_sender",
                "summary": summary,
                "body": body,
            }

        logger.info(f"Resolved sender {recipient} from summary {repr(summary)}")

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

        # 5. One-time reply limit in the local ledger. No payment/order linkage.
        cooldown = self.cooldown_hours
        max_replies = self.max_replies
        if not self.ledger.can_auto_reply(recipient, cooldown_hours=cooldown, max_replies=max_replies):
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

        # 7. Check sending kill-switch
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

        # 8. Execute auto-reply safely under mutex
        text_to_send = self.reply_text
        try:
            with sync_viber_ui_mutex():
                # Authoritative re-check under mutex to prevent race condition between concurrent notifications
                if not self.ledger.can_auto_reply(recipient, cooldown_hours=cooldown, max_replies=max_replies):
                    return {
                        "status": "skipped",
                        "reason": "cooldown_active",
                        "sender": recipient,
                        "cooldown_hours": cooldown,
                    }

                verified_nav = False
                try:
                    from recipient_identity import open_verified_recipient
                    if hasattr(self.automation, "get_window_geometry"):
                        logger.info(f"Opening verified chat for {recipient} via native recipient identity...")
                        open_verified_recipient(self.automation, recipient)
                        verified_nav = True
                except Exception as e:
                    logger.warning(f"Native recipient verification unavailable, falling back: {e}")

                if not verified_nav:
                    logger.info(f"Opening chat for {recipient} via open_chat_by_number...")
                    self.automation.open_chat_by_number(recipient)
                    try:
                        self.automation.check_recipient_gate(recipient)
                    except Exception as e:
                        logger.error(f"Recipient gate failed for {recipient}: {e}")
                        return {"status": "failed", "reason": "recipient_gate_failed", "error": str(e)}

                logger.info(f"Drafting and sending canned response to {recipient}...")
                self.automation.put_draft(text_to_send)
                send_res = self.automation.send(text_to_send)
                # Record in Ledger immediately inside mutex
                self.ledger.record_auto_reply(recipient, text_to_send)
                logger.info(f"Auto-reply successfully sent to {recipient}: {send_res}")

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

        except ViberDispatchUnconfirmedError as e:
            # Lock cooldown even on unconfirmed dispatch to prevent infinite bot reply loops
            try:
                self.ledger.record_auto_reply(recipient, text_to_send)
            except Exception as rec_err:
                logger.error(f"Failed to record cooldown on unconfirmed reply: {rec_err}")

            self.dispatch_webhook({
                "event": "incoming_message",
                "sender": recipient,
                "summary": summary,
                "body": body,
                "auto_replied": False,
                "reason": "dispatch_unconfirmed",
                "error": str(e),
                "timestamp": time.time(),
            })

            logger.error(f"Auto-reply to {recipient} unconfirmed: {e}", exc_info=True)
            return {
                "status": "unconfirmed",
                "can_retry": False,
                "sender": recipient,
                "error": str(e),
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

                registered = False
                if NotificationServer is not None:
                    try:
                        self._notification_server = NotificationServer(self, bus)
                        registered = True
                        logger.info("Claimed org.freedesktop.Notifications service as official notification sink")
                    except Exception as srv_err:
                        logger.info(f"Could not claim notification service ({srv_err}); using BecomeMonitor fallback")

                if not registered:
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
    parser.add_argument("--reset", metavar="PHONE", help="Reset auto-reply history and count for specific phone number")
    args = parser.parse_args()

    responder = get_auto_responder()

    if args.stats:
        stats = responder.ledger.get_auto_reply_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    if args.reset:
        norm = normalize_phone(args.reset) or args.reset
        responder.ledger.reset_auto_reply(norm)
        print(json.dumps({"ok": True, "reset": norm}, indent=2, ensure_ascii=False))
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
