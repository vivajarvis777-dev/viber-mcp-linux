"""Bounded read-only D-Bus probe for Viber desktop notifications.

Reports only shape/provenance booleans; never logs names, phone values or bodies.
Does not own org.freedesktop.Notifications, touch the Viber GUI or send messages.
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import time

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error("seconds must be within 1..600")

    DBusGMainLoop(set_as_default=True)
    monitor_bus = dbus.SessionBus()
    lookup_bus = dbus.SessionBus(private=True)
    lookup_obj = lookup_bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
    lookup = dbus.Interface(lookup_obj, "org.freedesktop.DBus")
    totals = {"notify": 0, "viber_app": 0, "viber_process": 0}
    loop = GLib.MainLoop()

    def on_message(_connection, message):
        if message.get_interface() != "org.freedesktop.Notifications" or message.get_member() != "Notify":
            return
        totals["notify"] += 1
        try:
            fields = message.get_args_list()
            app = str(fields[0]).casefold() if len(fields) > 0 else ""
            summary = str(fields[3]) if len(fields) > 3 else ""
            body_present = bool(str(fields[4])) if len(fields) > 4 else False
            app_viber = app in {"viber", "viberpc"}
            sender_pid = None
            sender_viber = False
            try:
                sender_pid = int(lookup.GetConnectionUnixProcessID(message.get_sender()))
                cmdline = open(f"/proc/{sender_pid}/cmdline", "rb").read().split(b"\0")[0]
                sender_viber = b"viber" in os.path.basename(cmdline).lower()
            except (OSError, dbus.DBusException, ValueError):
                pass
            if app_viber:
                totals["viber_app"] += 1
                totals["viber_process"] += int(sender_viber)
                literal = bool(re.fullmatch(r"\+?[0-9][0-9 ()-]{7,24}", summary.strip()))
                print(f"viber_event sender_pid={sender_pid} origin_viber={sender_viber} literal_phone_title={literal} has_title={bool(summary)} has_body={body_present}", flush=True)
        except (ValueError, TypeError, IndexError, dbus.DBusException):
            print("notification_parse_failed", flush=True)

    monitor_bus.add_message_filter(on_message)
    iface = dbus.Interface(monitor_bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus"), "org.freedesktop.DBus.Monitoring")
    iface.BecomeMonitor(["type='method_call',interface='org.freedesktop.Notifications',member='Notify'"], dbus.UInt32(0))
    GLib.timeout_add_seconds(args.seconds, lambda: (loop.quit(), False)[1])
    signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(loop.quit))
    print("passive_monitor_ready no_send=True no_notification_sink=True", flush=True)
    try:
        loop.run()
    finally:
        print(f"summary notify={totals['notify']} viber_app={totals['viber_app']} viber_process={totals['viber_process']}", flush=True)


if __name__ == "__main__":
    main()
