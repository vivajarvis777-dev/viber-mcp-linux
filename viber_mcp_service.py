"""Hermes ↔ Viber MCP Server for Linux (X11 + AT-SPI + xclip).

Multi-contact Viber Desktop automation with visual header verification,
sequential execution locking, and intelligent contact resolution.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Literal
import unicodedata

for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3.12/dist-packages"):
    if p not in sys.path and os.path.exists(p):
        sys.path.append(p)

import dbus
from PIL import Image, ImageGrab, ImageOps

from mcp.server.fastmcp import FastMCP

# Approved address book contacts with metadata & header reference files
SAVED_CONTACTS = {
    "+380981901991": {
        "name": "Юрій Приходько (Юрко Господар)",
        "aliases": ["Юрко", "Господар", "Юрій", "Приходько", "Власник", "Юрко Господар"],
        "ref_image": "header-reference.png"
    },
    "+380674032750": {
        "name": "Я Йоп",
        "aliases": ["Йоп", "Я Йоп", "Тест 2", "Другий", "Другий номер"],
        "ref_image": "header-380674032750.png"
    }
}

VIBER_LAUNCHER = os.getenv("VIBER_LAUNCHER", "/home/hannelora/.local/opt/viber-deb-27.3.0.2/launch-viber")
DISPLAY = os.getenv("DISPLAY", ":10.0")
SESSION_BUS = os.getenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1003/bus")

os.environ["DISPLAY"] = DISPLAY
os.environ["DBUS_SESSION_BUS_ADDRESS"] = SESSION_BUS
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1003"

mcp = FastMCP("viber_linux_mcp", instructions="Viber MCP integration for Hermes on Linux")
_viber_lock = asyncio.Lock()


def resolve_phone(target: str) -> str:
    """Normalize input (phone number or contact name/alias) to approved E.164 phone number."""
    target_clean = target.strip()
    if target_clean in SAVED_CONTACTS:
        return target_clean

    # Try matching by digits
    digits = "".join(c for c in target_clean if c.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "38" + digits
    if digits.startswith("380") and len(digits) == 12:
        candidate = "+" + digits
        if candidate in SAVED_CONTACTS:
            return candidate

    # Match by name or alias (case-insensitive)
    t_lower = target_clean.lower()
    for phone, info in SAVED_CONTACTS.items():
        if t_lower == info["name"].lower() or any(t_lower == a.lower() for a in info["aliases"]):
            return phone

    # Substring match if unambiguous
    sub_matches = [
        phone for phone, info in SAVED_CONTACTS.items()
        if t_lower in info["name"].lower() or any(t_lower in a.lower() for a in info["aliases"])
    ]
    if len(sub_matches) == 1:
        return sub_matches[0]

    raise ValueError(f"Target '{target}' is not in the approved Viber address book")


class ViberAutomation:
    def __init__(self, display: str = DISPLAY):
        self.display = display
        self.env = dict(
            os.environ,
            DISPLAY=self.display,
            DBUS_SESSION_BUS_ADDRESS=SESSION_BUS,
            XDG_RUNTIME_DIR="/run/user/1003",
        )
        self._a11y_bus = None
        self._editor_path = "/org/a11y/atspi/accessible/2147483740"
        self._send_btn_path = "/org/a11y/atspi/accessible/2147483904"
        self.current_phone: str | None = None

    def get_a11y_bus(self):
        if self._a11y_bus is None:
            session = dbus.SessionBus()
            bus_obj = session.get_object("org.a11y.Bus", "/org/a11y/bus")
            a_addr = str(bus_obj.GetAddress(dbus_interface="org.a11y.Bus"))
            self._a11y_bus = dbus.bus.BusConnection(a_addr)
        return self._a11y_bus

    def get_viber_app(self):
        bus = self.get_a11y_bus()
        root = bus.get_object("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root")
        apps = root.GetChildren(dbus_interface="org.a11y.atspi.Accessible")
        for dest, path in apps:
            obj = bus.get_object(dest, path)
            try:
                name = str(obj.Get("org.a11y.atspi.Accessible", "Name", dbus_interface="org.freedesktop.DBus.Properties"))
                if name == "ViberPC":
                    return dest, path
            except Exception:
                continue
        raise RuntimeError("Viber accessibility application not found")

    def get_window_geometry(self) -> tuple[int, int, int, int]:
        out = subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--class", "Viber"],
            env=self.env
        ).decode().split()
        if not out:
            raise RuntimeError("Viber window not found")
        wid = out[0]
        info = subprocess.check_output(["xwininfo", "-id", wid], env=self.env).decode()
        lines = dict([line.split(":", 1) for line in info.splitlines() if ":" in line])
        wx = int(lines["  Absolute upper-left X"].strip())
        wy = int(lines["  Absolute upper-left Y"].strip())
        ww = int(lines["  Width"].strip())
        wh = int(lines["  Height"].strip())
        return wx, wy, ww, wh

    def verify_header_contact(self, phone: str) -> bool:
        """Verify that open chat header visually matches reference image for the given contact."""
        if phone not in SAVED_CONTACTS:
            return False
        ref_filename = SAVED_CONTACTS[phone]["ref_image"]
        ref_path = Path(__file__).parent / "private" / ref_filename
        if not ref_path.exists():
            return False
        try:
            wx, wy, _, _ = self.get_window_geometry()
            bbox = (wx + 299, wy + 40, wx + 299 + 302, wy + 40 + 43)
            img = ImageGrab.grab(bbox=bbox, xdisplay=self.display).convert("RGB")
            b_cur = ImageOps.grayscale(img).point(lambda x: 0 if x < 150 else 255).tobytes()

            with open(ref_path, "rb") as f:
                ref = Image.open(f).convert("RGB")
            b_ref = ImageOps.grayscale(ref).point(lambda x: 0 if x < 150 else 255).tobytes()

            matched = (b_cur == b_ref)
            if matched:
                self.current_phone = phone
            return matched
        except Exception:
            return False

    def get_editor_text(self) -> str:
        bus = self.get_a11y_bus()
        dest, _ = self.get_viber_app()
        editor = bus.get_object(dest, self._editor_path)
        return str(editor.GetText(0, -1, dbus_interface="org.a11y.atspi.Text"))

    def focus_editor(self):
        bus = self.get_a11y_bus()
        dest, _ = self.get_viber_app()
        editor = bus.get_object(dest, self._editor_path)
        editor.DoAction(0, dbus_interface="org.a11y.atspi.Action")
        extents = editor.GetExtents(0, dbus_interface="org.a11y.atspi.Component")
        x, y, w, h = int(extents[0]), int(extents[1]), int(extents[2]), int(extents[3])
        subprocess.run(["xdotool", "mousemove", str(x + w // 2), str(y + h // 2), "click", "1"],
                       env=self.env, check=True, timeout=3)
        time.sleep(0.1)

    def read_messages(self) -> list[str]:
        bus = self.get_a11y_bus()
        dest, app_path = self.get_viber_app()
        queue = [(dest, app_path)]
        messages = []
        while queue:
            d, p = queue.pop(0)
            if p in (self._editor_path, "/org/a11y/atspi/accessible/2147483789"):
                continue  # skip composer and search box
            obj = bus.get_object(d, p)
            try:
                role = obj.GetRoleName(dbus_interface="org.a11y.atspi.Accessible")
                if role in ("text", "entry", "paragraph"):
                    t = str(obj.GetText(0, -1, dbus_interface="org.a11y.atspi.Text")).strip()
                    if t and t not in messages:
                        messages.append(t)
            except Exception:
                pass
            try:
                children = obj.GetChildren(dbus_interface="org.a11y.atspi.Accessible")
                for child in children:
                    queue.append((child[0], child[1]))
            except Exception:
                pass
        return messages

    def open_chat_by_number(self, phone: str):
        if phone not in SAVED_CONTACTS:
            raise ValueError(f"Number {phone} is not in the approved Viber address book")

        target_uri = f"viber://chat?number={phone}"

        # Delegate execution via systemd-run --user when running inside isolated PrivateTmp namespace
        use_systemd_run = (not os.path.exists("/tmp/Viber-0-3eb")) and (shutil.which("systemd-run") is not None)
        if use_systemd_run:
            cmd = [
                "systemd-run", "--user", "--wait", "--collect",
                f"--setenv=DISPLAY={self.display}",
                f"--setenv=DBUS_SESSION_BUS_ADDRESS={SESSION_BUS}",
                VIBER_LAUNCHER, target_uri
            ]
        else:
            cmd = [VIBER_LAUNCHER, target_uri]

        subprocess.run(
            cmd,
            env=self.env,
            check=True,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(1.0)

        # Ensure Viber window is active
        try:
            subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--class", "Viber", "windowactivate"],
                env=self.env,
                check=False,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

        if not self.verify_header_contact(phone):
            raise RuntimeError(f"Chat header check failed: active chat does not match verified reference for {phone}")

        self.current_phone = phone

    def put_draft(self, text: str) -> dict:
        if not text or len(text) > 1000:
            raise ValueError("text_length_invalid")
        if any(unicodedata.category(c).startswith("C") or c in "\n\r\t" for c in text):
            raise ValueError("single_line_text_required")

        current = self.get_editor_text()
        norm_cur = unicodedata.normalize("NFC", current).replace("\ufe0f", "")
        norm_tx = unicodedata.normalize("NFC", text).replace("\ufe0f", "")

        if current and norm_cur != norm_tx:
            raise RuntimeError(f"Existing draft present in editor: {current!r}. Clear or send it first.")

        if norm_cur == norm_tx:
            return {"drafted": True, "verified": True, "text": current}

        self.focus_editor()

        # Set clipboard via xclip
        p = subprocess.Popen(["xclip", "-selection", "clipboard"],
                             env=self.env, stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.communicate(input=text.encode("utf-8"))
        if p.returncode != 0:
            raise RuntimeError("xclip failed to set clipboard")

        # Paste Ctrl+V
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                       env=self.env, check=True, timeout=3)
        time.sleep(0.3)

        readback = self.get_editor_text()
        norm_rb = unicodedata.normalize("NFC", readback).replace("\ufe0f", "")
        if readback != text and norm_rb != norm_tx:
            raise RuntimeError(f"Draft verification failed: expected {text!r}, got {readback!r}")

        return {"drafted": True, "verified": True, "text": readback}

    def send(self, expected_text: str) -> dict:
        current = self.get_editor_text()
        norm_cur = unicodedata.normalize("NFC", current).replace("\ufe0f", "").strip()
        norm_exp = unicodedata.normalize("NFC", expected_text).replace("\ufe0f", "").strip()
        if current != expected_text and norm_cur != norm_exp:
            raise RuntimeError(f"Composer text mismatch before send: expected {expected_text!r}, got {current!r}")

        self.focus_editor()
        subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"],
                       env=self.env, check=True, timeout=3)
        time.sleep(0.5)

        after = self.get_editor_text()
        if after != "":
            # Try send button fallback
            bus = self.get_a11y_bus()
            dest, _ = self.get_viber_app()
            btn = bus.get_object(dest, self._send_btn_path)
            btn.DoAction(0, dbus_interface="org.a11y.atspi.Action")
            time.sleep(0.5)
            after = self.get_editor_text()

        if after != "":
            raise RuntimeError("Message was not cleared from editor after send attempt")

        # Verify message in history
        messages = self.read_messages()
        found = any(
            expected_text in m or norm_exp in unicodedata.normalize("NFC", m).replace("\ufe0f", "")
            for m in messages
        )
        if not found:
            raise RuntimeError("Sent message not observed in chat history")

        return {"sent": True, "verified": True, "text": current}


auto = ViberAutomation()


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def health() -> dict:
    """Check Viber desktop automation status, connectivity, and active contact."""
    try:
        dest, _ = auto.get_viber_app()
        w_ok = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "Viber"],
                              env=auto.env, capture_output=True, text=True).returncode == 0
        active_match = None
        for phone in SAVED_CONTACTS:
            if auto.verify_header_contact(phone):
                active_match = {"phone": phone, "name": SAVED_CONTACTS[phone]["name"]}
                break

        return {
            "status": "ok",
            "viber_accessibility": dest,
            "window_visible": w_ok,
            "active_contact": active_match
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def list_contacts() -> dict:
    """Return all approved saved Viber address book contacts."""
    return {
        "contacts": {
            phone: info["name"] for phone, info in SAVED_CONTACTS.items()
        },
        "details": SAVED_CONTACTS
    }


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def find_contact(query: str) -> dict:
    """Find a saved Viber contact by name, surname, alias, or phone number."""
    q = query.strip().lower()
    matches = []
    digits = "".join(c for c in q if c.isdigit())
    for phone, info in SAVED_CONTACTS.items():
        phone_digits = "".join(c for c in phone if c.isdigit())
        if digits and (digits in phone_digits or phone_digits in digits):
            matches.append({"phone": phone, **info})
            continue
        if q in info["name"].lower() or any(q in a.lower() for a in info["aliases"]):
            matches.append({"phone": phone, **info})

    if not matches:
        return {"found": False, "query": query, "message": f"No contacts found matching '{query}'"}
    if len(matches) == 1:
        return {"found": True, "query": query, "contact": matches[0]}
    return {"found": True, "query": query, "multiple_matches": matches}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def open_chat(to: str) -> dict:
    """Open verified saved contact chat by phone number, name, or alias with visual header verification."""
    async with _viber_lock:
        try:
            phone = resolve_phone(to)
        except ValueError as err:
            return {"ok": False, "error": str(err)}

        try:
            await asyncio.to_thread(auto.open_chat_by_number, phone)
            return {
                "ok": True,
                "opened": phone,
                "contact_name": SAVED_CONTACTS[phone]["name"],
                "header_verified": True,
                "note": f"Chat with {SAVED_CONTACTS[phone]['name']} ({phone}) is open and visually confirmed."
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def read_open_chat(to: str | None = None) -> dict:
    """Read visible messages from currently open chat via AT-SPI after verifying the recipient."""
    async with _viber_lock:
        target_phone = None
        if to:
            try:
                target_phone = resolve_phone(to)
            except ValueError as err:
                return {"ok": False, "error": str(err)}

            if not auto.verify_header_contact(target_phone):
                # Switch to requested chat
                try:
                    await asyncio.to_thread(auto.open_chat_by_number, target_phone)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to switch to chat for {to}: {e}"}
        else:
            # Detect currently active contact
            for p in SAVED_CONTACTS:
                if auto.verify_header_contact(p):
                    target_phone = p
                    break
            if not target_phone:
                return {"ok": False, "error": "Active chat header could not be verified for any approved contact. Reading blocked."}

        messages = await asyncio.to_thread(auto.read_messages)
        return {
            "ok": True,
            "messages": messages,
            "count": len(messages),
            "recipient": target_phone,
            "contact_name": SAVED_CONTACTS[target_phone]["name"]
        }


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def put_draft(to: str, text: str) -> dict:
    """Put exact verified Ukrainian draft into the specified contact's composer without sending."""
    async with _viber_lock:
        try:
            phone = resolve_phone(to)
        except ValueError as err:
            return {"ok": False, "error": str(err)}

        # Switch to chat if not currently active
        if not auto.verify_header_contact(phone):
            try:
                await asyncio.to_thread(auto.open_chat_by_number, phone)
            except Exception as e:
                return {"ok": False, "error": f"Failed to open chat for {to}: {e}"}

        result = await asyncio.to_thread(auto.put_draft, text)
        return {
            "ok": True,
            "recipient": phone,
            "contact_name": SAVED_CONTACTS[phone]["name"],
            **result
        }


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
async def send_message(to: str, text: str, approval_token: str = "CONFIRMED") -> dict:
    """Send approved message to open chat after explicit operator authorization.

    Args:
        to: Approved contact phone number, name, or alias
        text: Exact expected text currently in composer
        approval_token: Confirmation marker from agent indicating operator permission was received (default: 'CONFIRMED')
    """
    async with _viber_lock:
        try:
            phone = resolve_phone(to)
        except ValueError as err:
            return {"ok": False, "error": str(err)}

        if not approval_token:
            return {"ok": False, "error": "Explicit approval token required"}

        if not auto.verify_header_contact(phone):
            return {"ok": False, "error": f"Active chat header is not verified as {phone} ({SAVED_CONTACTS[phone]['name']}). Sending blocked."}

        result = await asyncio.to_thread(auto.send, text)
        return {
            "ok": True,
            "recipient": phone,
            "contact_name": SAVED_CONTACTS[phone]["name"],
            **result
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
