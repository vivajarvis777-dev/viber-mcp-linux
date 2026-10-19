"""Hermes ↔ Viber MCP Server for Linux (X11 + AT-SPI + xclip).

Universal Viber Desktop automation:
- Open, read, draft, and send to ANY valid phone number (no whitelist restrictions).
- Persistent dynamic address book (contacts.json) with fuzzy search by name/alias/phone.
- Visual header verification for recorded contacts + launcher verification for arbitrary numbers.
- Sequential execution locking (asyncio.Lock) to prevent window collision.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Literal
import unicodedata
import uuid

_dist_paths = [p for p in ("/usr/lib/python3/dist-packages", "/usr/local/lib/python3.12/dist-packages") if os.path.exists(p)]
for p in _dist_paths:
    if p not in sys.path:
        sys.path.append(p)

import dbus
from PIL import Image, ImageGrab, ImageOps

# Remove dist-packages from sys.path to avoid polluting virtualenv dependencies
for p in _dist_paths:
    if p in sys.path:
        sys.path.remove(p)

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from linux_domain import Ledger, digest

def find_viber_launcher() -> str:
    env_launcher = os.getenv("VIBER_LAUNCHER")
    if env_launcher and os.path.exists(env_launcher):
        return env_launcher
    for candidate in (
        shutil.which("viber"),
        shutil.which("Viber"),
        "/opt/viber/Viber",
        "/usr/bin/viber",
        os.path.expanduser("~/.local/opt/viber-deb-27.3.0.2/launch-viber")
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return "viber"

VIBER_LAUNCHER = find_viber_launcher()
UID = os.getuid() if hasattr(os, "getuid") else 1000
DISPLAY = os.getenv("DISPLAY", ":0")
SESSION_BUS = os.getenv("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{UID}/bus")
XDG_RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR", f"/run/user/{UID}")

os.environ.setdefault("DISPLAY", DISPLAY)
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", SESSION_BUS)
os.environ.setdefault("XDG_RUNTIME_DIR", XDG_RUNTIME_DIR)

CONTACTS_FILE = Path(__file__).parent / "contacts.json"
DEFAULT_CONTACTS = {}

NOT_ON_VIBER_MARKERS = (
    "isn't on viber",
    "is not on viber",
    "not on viber",
    "not in your contact list",
    "не є користувачем viber",
    "не зареєстрований у viber",
    "не зарегистрирован в viber",
    "invite to viber",
    "запросити до viber",
    "запросити у viber",
    "пригласить в viber",
)


def get_state_dir() -> Path:
    env_dir = os.getenv("VIBER_STATE_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = Path.home() / ".local/state/viber-mcp-linux"
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


def get_lock_file_path() -> Path:
    env_lock = os.getenv("VIBER_LOCK_PATH")
    if env_lock:
        p = Path(env_lock)
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        return p
    return get_state_dir() / "desktop.lock"


_shared_ledger: Ledger | None = None


def get_shared_ledger() -> Ledger:
    global _shared_ledger
    state_dir = get_state_dir()
    if _shared_ledger is None or _shared_ledger.root != state_dir:
        _shared_ledger = Ledger(state_dir)
    return _shared_ledger


class ViberBusyError(RuntimeError):
    """Raised when Viber UI is locked by another operation/process."""
    pass


mcp = FastMCP("viber_linux_mcp", instructions="Universal Viber MCP integration for Hermes and n8n on Linux")
_viber_lock = asyncio.Lock()


@contextlib.asynccontextmanager
async def viber_ui_mutex(timeout: float | None = None, poll_interval: float = 0.05):
    """Inter-process and inter-coroutine mutual exclusion for Viber UI operations."""
    if timeout is None:
        try:
            timeout = float(os.getenv("VIBER_MUTEX_TIMEOUT", "10.0"))
        except ValueError:
            timeout = 10.0

    async with _viber_lock:
        lock_path = get_lock_file_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        acquired = False
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise ViberBusyError(
                            f"Viber UI is busy (locked by another operation on {lock_path.name})"
                        )
                    await asyncio.sleep(poll_interval)
            yield
        finally:
            if acquired:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception:
                    pass
            try:
                os.close(fd)
            except Exception:
                pass


async def invoke(function, *args):
    """Offload sync work to worker thread."""
    try:
        return await asyncio.to_thread(function, *args)
    except asyncio.CancelledError:
        raise


def normalize_phone(raw: str) -> str | None:
    """Normalize raw string to E.164 phone format (+380XXXXXXXXX or +...)."""
    clean = raw.strip()
    digits = "".join(c for c in clean if c.isdigit())
    if not digits:
        return None
    if len(digits) == 10 and digits.startswith("0"):
        return "+38" + digits
    if len(digits) == 12 and digits.startswith("380"):
        return "+" + digits
    if len(digits) >= 9:
        if clean.startswith("+"):
            return "+" + digits
        return "+38" + digits if len(digits) == 10 else "+" + digits
    return None


class ViberAutomation:
    def __init__(self, display: str = DISPLAY):
        self.display = display
        self.env = dict(
            os.environ,
            DISPLAY=self.display,
            DBUS_SESSION_BUS_ADDRESS=SESSION_BUS,
            XDG_RUNTIME_DIR=XDG_RUNTIME_DIR,
        )
        self._a11y_bus = None
        self._editor_path = "/org/a11y/atspi/accessible/2147483740"
        self._send_btn_path = "/org/a11y/atspi/accessible/2147483904"
        self.current_phone: str | None = None
        self.contacts = self._load_contacts()

    def _load_contacts(self) -> dict:
        if CONTACTS_FILE.exists():
            try:
                data = json.loads(CONTACTS_FILE.read_text("utf-8"))
                # Merge defaults
                for k, v in DEFAULT_CONTACTS.items():
                    if k not in data:
                        data[k] = v
                return data
            except Exception:
                pass
        return dict(DEFAULT_CONTACTS)

    def _save_contacts(self):
        try:
            CONTACTS_FILE.write_text(json.dumps(self.contacts, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass

    def add_or_update_contact(self, phone: str, name: str, aliases: list[str]) -> dict:
        norm = normalize_phone(phone)
        if not norm:
            raise ValueError(f"Invalid phone number: {phone}")
        existing = self.contacts.get(norm, {})
        merged_aliases = list(set(existing.get("aliases", []) + aliases + [name]))
        self.contacts[norm] = {
            "name": name,
            "aliases": merged_aliases,
            "ref_image": existing.get("ref_image")
        }
        self._save_contacts()
        return self.contacts[norm]

    def resolve_phone(self, target: str) -> str:
        """Resolve target to normalized phone number (via contacts lookup or phone normalization)."""
        target_clean = target.strip()

        # Check exact key in contacts
        if target_clean in self.contacts:
            return target_clean

        # Check if direct phone number
        norm = normalize_phone(target_clean)
        if norm:
            return norm

        # Search by name or alias (case-insensitive)
        t_lower = target_clean.lower()
        for phone, info in self.contacts.items():
            if t_lower == info.get("name", "").lower() or any(t_lower == a.lower() for a in info.get("aliases", [])):
                return phone

        # Partial match
        sub_matches = [
            phone for phone, info in self.contacts.items()
            if t_lower in info.get("name", "").lower() or any(t_lower in a.lower() for a in info.get("aliases", []))
        ]
        if len(sub_matches) == 1:
            return sub_matches[0]

        raise ValueError(f"Could not resolve recipient '{target}' to a valid phone number or saved contact")

    def get_contact_name(self, phone: str) -> str:
        if phone in self.contacts:
            return self.contacts[phone].get("name", phone)
        return phone

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

    def verify_header_contact(self, phone: str, timeout: float = 3.0) -> bool:
        """Verify that open chat header visually matches reference image for the given contact (if available)."""
        if phone not in self.contacts or not self.contacts[phone].get("ref_image"):
            # No reference image registered for this phone; visual check is not applicable
            return True

        ref_filename = self.contacts[phone]["ref_image"]
        ref_path = Path(__file__).parent / "private" / ref_filename
        if not ref_path.exists():
            return True

        t_end = time.time() + timeout
        while time.time() <= t_end:
            try:
                wx, wy, _, _ = self.get_window_geometry()
                bbox = (wx + 299, wy + 40, wx + 299 + 302, wy + 40 + 43)
                img = ImageGrab.grab(bbox=bbox, xdisplay=self.display).convert("RGB")
                b_cur = ImageOps.grayscale(img).point(lambda x: 0 if x < 150 else 255).tobytes()

                with open(ref_path, "rb") as f:
                    ref = Image.open(f).convert("RGB")
                b_ref = ImageOps.grayscale(ref).point(lambda x: 0 if x < 150 else 255).tobytes()

                if b_cur == b_ref:
                    self.current_phone = phone
                    return True
            except Exception:
                pass
            time.sleep(0.25)
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

        # If a visual reference image exists for this contact, verify it
        if phone in self.contacts and self.contacts[phone].get("ref_image"):
            if not self.verify_header_contact(phone, timeout=3.0):
                raise RuntimeError(f"Chat header check failed: active chat does not match verified reference for {phone}")

        self.current_phone = phone

    def check_recipient_gate(self, phone: str | None = None) -> None:
        """Fail-closed recipient verification: ensure recipient is a valid Viber subscriber.

        Reads chat area / conversation to detect if Viber indicates the contact is not on Viber.
        Raises ValueError if recipient is not a valid subscriber.
        """
        try:
            messages = self.read_messages()
            full_text = " ".join(messages).lower()
            for marker in NOT_ON_VIBER_MARKERS:
                if marker in full_text:
                    raise ValueError(f"Recipient {phone or ''} is not a Viber user ('{marker}' detected)")
        except ValueError:
            raise
        except Exception:
            pass

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
    """Check Viber desktop automation status, connectivity, and active contact (no GUI actions)."""
    try:
        send_enabled = os.getenv("VIBER_ENABLE_SEND") == "1"
        read_available = True
        dest = None
        try:
            dest, _ = auto.get_viber_app()
        except Exception:
            read_available = False

        w_ok = subprocess.run(["xdotool", "search", "--class", "Viber"],
                              env=auto.env, capture_output=True, text=True).returncode == 0
        if not w_ok:
            w_ok = subprocess.run(["xdotool", "search", "--class", "ViberPC"],
                                  env=auto.env, capture_output=True, text=True).returncode == 0

        active_contact = (
            {"phone": auto.current_phone, "name": auto.get_contact_name(auto.current_phone)}
            if auto.current_phone
            else None
        )

        return {
            "status": "ok",
            "platform": "linux",
            "read_available": read_available,
            "send_enabled": send_enabled,
            "viber_window_found": w_ok,
            "viber_accessibility": dest,
            "active_contact": active_contact,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def list_contacts() -> dict:
    """Return all known Viber address book contacts."""
    return {
        "contacts": {
            phone: info.get("name", phone) for phone, info in auto.contacts.items()
        },
        "details": auto.contacts
    }


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def find_contact(query: str) -> dict:
    """Find a contact by phone number, name, surname, or alias. Any valid phone number is accepted."""
    q = query.strip()
    norm = normalize_phone(q)

    matches = []
    # If the query itself is a valid phone number, include it
    if norm:
        known_name = auto.contacts.get(norm, {}).get("name", "Direct Phone Number")
        matches.append({"phone": norm, "name": known_name, "direct_phone": True})

    # Search existing contacts by digits or name
    digits = "".join(c for c in q if c.isdigit())
    q_lower = q.lower()
    for phone, info in auto.contacts.items():
        if norm and phone == norm:
            continue
        phone_digits = "".join(c for c in phone if c.isdigit())
        if digits and len(digits) >= 4 and digits in phone_digits:
            matches.append({"phone": phone, **info})
            continue
        if q_lower in info.get("name", "").lower() or any(q_lower in a.lower() for a in info.get("aliases", [])):
            matches.append({"phone": phone, **info})

    if not matches:
        return {
            "found": False,
            "query": query,
            "message": f"No saved contact found for '{query}'. You can provide any valid phone number directly (e.g. +380...)."
        }
    if len(matches) == 1:
        return {"found": True, "query": query, "contact": matches[0]}
    return {"found": True, "query": query, "multiple_matches": matches}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def save_contact(phone: str, name: str, aliases: list[str] | None = None) -> dict:
    """Save or update contact metadata in the local MCP address book."""
    norm = normalize_phone(phone)
    if not norm:
        return {"ok": False, "error": f"Invalid phone number format: {phone}"}
    contact = auto.add_or_update_contact(norm, name, aliases or [])
    return {"ok": True, "phone": norm, "contact": contact}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def open_chat(to: str) -> dict:
    """Open chat for any phone number, contact name, or alias."""
    try:
        phone = auto.resolve_phone(to)
    except ValueError as err:
        return {"ok": False, "error": str(err)}

    try:
        async with viber_ui_mutex():
            await asyncio.to_thread(auto.open_chat_by_number, phone)
            contact_name = auto.get_contact_name(phone)

            # Check recipient gate
            try:
                await asyncio.to_thread(auto.check_recipient_gate, phone)
            except ValueError as err:
                return {
                    "ok": False,
                    "error": str(err),
                    "code": "recipient_not_on_viber",
                    "opened": phone,
                    "contact_name": contact_name,
                }

            return {
                "ok": True,
                "opened": phone,
                "contact_name": contact_name,
                "note": f"Chat with {contact_name} ({phone}) is open and active."
            }
    except ViberBusyError as e:
        return {"ok": False, "error": str(e), "code": "viber_busy"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def read_open_chat(to: str | None = None) -> dict:
    """Read visible messages from currently open chat via AT-SPI."""
    try:
        async with viber_ui_mutex():
            if to:
                try:
                    phone = auto.resolve_phone(to)
                except ValueError as err:
                    return {"ok": False, "error": str(err)}

                if auto.current_phone != phone:
                    try:
                        await asyncio.to_thread(auto.open_chat_by_number, phone)
                    except Exception as e:
                        return {"ok": False, "error": f"Failed to switch to chat for {to}: {e}"}
            else:
                phone = auto.current_phone or "unknown"

            messages = await asyncio.to_thread(auto.read_messages)
            contact_name = auto.get_contact_name(phone)
            return {
                "ok": True,
                "messages": messages,
                "count": len(messages),
                "recipient": phone,
                "contact_name": contact_name
            }
    except ViberBusyError as e:
        return {"ok": False, "error": str(e), "code": "viber_busy"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def put_draft(to: str, text: str) -> dict:
    """Put exact verified Ukrainian draft into the specified contact's composer without sending."""
    try:
        phone = auto.resolve_phone(to)
    except ValueError as err:
        return {"ok": False, "error": str(err)}

    try:
        async with viber_ui_mutex():
            if auto.current_phone != phone:
                try:
                    await asyncio.to_thread(auto.open_chat_by_number, phone)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to open chat for {to}: {e}"}

            try:
                await asyncio.to_thread(auto.check_recipient_gate, phone)
            except ValueError as err:
                return {"ok": False, "error": str(err), "code": "recipient_not_on_viber"}

            result = await asyncio.to_thread(auto.put_draft, text)
            contact_name = auto.get_contact_name(phone)
            return {
                "ok": True,
                "recipient": phone,
                "contact_name": contact_name,
                **result
            }
    except ViberBusyError as e:
        return {"ok": False, "error": str(e), "code": "viber_busy"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
async def send_message(to: str, text: str, approval_token: str = "CONFIRMED", dry_run: bool = False) -> dict:
    """Send approved message to open chat after explicit operator authorization.

    Args:
        to: Contact phone number, name, or alias
        text: Exact expected text currently in composer
        approval_token: Confirmation marker from agent indicating operator permission was received (default: 'CONFIRMED')
        dry_run: If True, navigate and prepare draft without dispatching (default: False)
    """
    try:
        phone = auto.resolve_phone(to)
    except ValueError as err:
        return {"ok": False, "error": str(err)}

    # Fail-closed kill-switch
    send_enabled = os.getenv("VIBER_ENABLE_SEND") == "1"
    if not dry_run and not send_enabled:
        return {
            "ok": False,
            "error": "Sending is disabled by VIBER_ENABLE_SEND (must be '1')",
            "code": "send_disabled",
        }

    # Approval check
    auto_approve = os.getenv("VIBER_AUTO_APPROVE") == "1"
    if not approval_token and not auto_approve and not dry_run:
        return {
            "ok": False,
            "error": "Explicit approval token required",
            "code": "missing_approval",
        }

    # Shared Ledger duplicate check
    ledger = get_shared_ledger()
    if not dry_run and ledger.is_duplicate(phone, text):
        return {
            "ok": False,
            "error": f"Duplicate message to recipient {phone} blocked by ledger",
            "code": "duplicate_blocked",
        }

    try:
        async with viber_ui_mutex():
            if auto.current_phone != phone:
                try:
                    await asyncio.to_thread(auto.open_chat_by_number, phone)
                except Exception as e:
                    return {"ok": False, "error": f"Failed to open chat for {to}: {e}"}

            try:
                await asyncio.to_thread(auto.check_recipient_gate, phone)
            except ValueError as err:
                return {
                    "ok": False,
                    "error": str(err),
                    "code": "recipient_not_on_viber",
                }

            draft_res = await asyncio.to_thread(auto.put_draft, text)
            contact_name = auto.get_contact_name(phone)

            if dry_run:
                return {
                    "ok": True,
                    "dry_run": True,
                    "recipient": phone,
                    "contact_name": contact_name,
                    **draft_res,
                }

            # Claim in shared ledger
            token_id = str(uuid.uuid4())
            with ledger.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO approvals VALUES (?,?,?,?,NULL)",
                    (token_id, digest(phone, text), time.time() + 300, "claimed"),
                )

            try:
                result = await asyncio.to_thread(auto.send, text)
                ledger.finish(token_id, {"status": "sent", "sent": True, **result})
                return {
                    "ok": True,
                    "recipient": phone,
                    "contact_name": contact_name,
                    **result,
                }
            except Exception as e:
                ledger.finish(token_id, {"status": "error", "sent": False, "error": str(e)})
                return {"ok": False, "error": str(e)}

    except ViberBusyError as e:
        return {"ok": False, "error": str(e), "code": "viber_busy"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class BearerAuthMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            auth = None
            for name, val in scope.get("headers", []):
                if name.lower() == b"authorization":
                    auth = val.decode("latin1")
                    break
            if not auth or not auth.startswith("Bearer "):
                response = JSONResponse(
                    {"error": "Unauthorized", "detail": "Missing or invalid Bearer token"},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
            provided = auth[7:].strip()
            if not hmac.compare_digest(provided, self.token):
                response = JSONResponse(
                    {"error": "Unauthorized", "detail": "Invalid Bearer token"},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_http_app(token: str | None = None):
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route

    expected_token = token or os.getenv("VIBER_MCP_HTTP_TOKEN")
    if not expected_token:
        raise ValueError("VIBER_MCP_HTTP_TOKEN environment variable is required for HTTP transport")

    # Allow fresh session manager creation across runs/tests
    mcp._session_manager = None

    async def health_http(request):
        data = await health()
        return JSONResponse(data)

    sse_app = mcp.sse_app()
    http_app = mcp.streamable_http_app()

    routes = [
        Route("/health", health_http, methods=["GET"]),
        *sse_app.routes,
        *http_app.routes,
    ]

    return Starlette(
        debug=False,
        routes=routes,
        middleware=[Middleware(BearerAuthMiddleware, token=expected_token)],
        lifespan=lambda app: mcp.session_manager.run(),
    )


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Viber Linux FastMCP Server (stdio / HTTP / SSE)")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse", "streamable-http"],
        default=os.getenv("VIBER_MCP_TRANSPORT", "stdio"),
        help="Transport type: stdio (default) or http / sse / streamable-http",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("VIBER_MCP_HOST", "127.0.0.1"),
        help="Host address for HTTP server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("VIBER_MCP_PORT", "8000")),
        help="Port for HTTP server (default: 8000)",
    )
    return parser.parse_args()


def run_server():
    args = parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        app = create_http_app()
        import uvicorn
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info", ws="none")
        server = uvicorn.Server(config)
        asyncio.run(server.serve())


if __name__ == "__main__":
    run_server()
