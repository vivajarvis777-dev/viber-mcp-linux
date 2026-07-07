"""Send Viber messages by driving the desktop app via URL scheme + HID-sourced input.

Viber Desktop exposes no local API and its message DB is encrypted, so the only reliable
send path is UI automation:

1. Open the target chat with the `viber://chat?number=` URL scheme (desktop needs a few
   seconds to navigate, so we poll the window via OCR until a sendable chat is visible).
2. Click the compose box and paste the text (clipboard paste survives emoji/unicode).
3. Click the send button.

Key detail: Viber is a Qt app that **ignores synthetic events unless they carry a real HID
event source**. So every click/keystroke is created from
`CGEventSourceCreate(kCGEventSourceStateHIDSystemState)`. Plain System Events keystrokes and
plain CGEvents are silently dropped by Qt's input widgets.

We click the send button rather than pressing Return because "Send message with Enter" may be
off (then Return only inserts a newline).

Requires: Viber running + signed in, and Accessibility + Screen Recording permission granted
to the process that launches this code.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

import Quartz  # type: ignore
from AppKit import NSPasteboard, NSStringPboardType  # type: ignore

import viber_ocr

CONTACTS_PATH = Path(__file__).with_name("contacts.json")

# E.164: leading +, then 8–15 digits. We also accept bare digit strings and normalize them.
_E164_RE = re.compile(r"^\+\d{8,15}$")
_DIGITS_RE = re.compile(r"^\d{8,15}$")

# macOS virtual key codes.
_KEY_A = 0
_KEY_V = 9
_KEY_RETURN = 36
_KEY_DELETE = 51
_KEY_ESCAPE = 53

# Compose box and send button positions as fractions of the Viber window (measured on
# v28.2.0 with the contact-info panel CLOSED). Recomputed from live window bounds each call.
_COMPOSE_FRAC = (0.45, 0.96)
_SEND_BTN_FRAC = (0.97, 0.955)


class SendError(Exception):
    """Raised when a message cannot be sent (recipient unresolved, Viber not running, etc.)."""


# --------------------------------------------------------------------------- recipients


def viber_is_running() -> bool:
    """True if the Viber desktop app process is alive."""
    return subprocess.run(["pgrep", "-x", "Viber"], capture_output=True).returncode == 0


def load_contacts() -> dict[str, str]:
    """Return the name->E.164 alias map, or {} if the file is absent/empty."""
    if not CONTACTS_PATH.exists():
        return {}
    try:
        data = json.loads(CONTACTS_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise SendError(f"contacts.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SendError("contacts.json must be a JSON object of {name: number}")
    return {str(k): str(v) for k, v in data.items()}


def _normalize_number(num: str) -> str:
    num = num.strip()
    if _E164_RE.match(num):
        return num
    if _DIGITS_RE.match(num):
        return "+" + num
    raise SendError(f"Invalid phone number: {num!r} (expected E.164 like +639171234567)")


def resolve_recipient(to: str) -> tuple[str, str | None]:
    """Resolve `to` to (E.164 number, contact_name_or_None).

    Accepts an E.164 string, a bare digit string, or a contact name in contacts.json.
    Never guesses: an unknown name raises SendError so we never message the wrong person.
    """
    to = to.strip()
    if _E164_RE.match(to):
        return to, None
    if _DIGITS_RE.match(to):
        return "+" + to, None

    contacts = load_contacts()
    if to in contacts:
        return _normalize_number(contacts[to]), to
    lowered = {k.lower(): (k, v) for k, v in contacts.items()}
    if to.lower() in lowered:
        name, num = lowered[to.lower()]
        return _normalize_number(num), name

    known = ", ".join(sorted(contacts)) or "(none)"
    raise SendError(
        f"Could not resolve recipient '{to}'. Provide an E.164 number (e.g. +639171234567) "
        f"or a name present in contacts.json. Known names: {known}"
    )


# ------------------------------------------------------------------------ HID synthetic input

_SRC = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)


def _post(event) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _click(x: float, y: float) -> None:
    down = Quartz.CGEventCreateMouseEvent(_SRC, Quartz.kCGEventLeftMouseDown, (x, y), Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(_SRC, Quartz.kCGEventLeftMouseUp, (x, y), Quartz.kCGMouseButtonLeft)
    _post(down)
    time.sleep(0.06)
    _post(up)


def _key(code: int, flags: int = 0) -> None:
    down = Quartz.CGEventCreateKeyboardEvent(_SRC, code, True)
    up = Quartz.CGEventCreateKeyboardEvent(_SRC, code, False)
    if flags:
        Quartz.CGEventSetFlags(down, flags)
        Quartz.CGEventSetFlags(up, flags)
    _post(down)
    time.sleep(0.03)
    _post(up)


def _focus_viber() -> None:
    subprocess.run(["open", "-b", "com.viber.osx"], check=False)
    time.sleep(0.6)


def _window_bounds() -> dict:
    return viber_ocr.find_viber_window()["kCGWindowBounds"]


def _point(frac: tuple[float, float], b: dict) -> tuple[float, float]:
    return b["X"] + b["Width"] * frac[0], b["Y"] + b["Height"] * frac[1]


# ------------------------------------------------------------------------------ clipboard


def _get_clipboard() -> str | None:
    return NSPasteboard.generalPasteboard().stringForType_(NSStringPboardType)


def _set_clipboard(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSStringPboardType)


# ----------------------------------------------------------------------------- open / send


def _wait_for_sendable_chat(number: str, name: str | None, timeout: float = 12.0) -> str:
    """Poll the Viber window (via OCR) until a sendable chat is visible.

    Success signals (any one, and no error screen):
      - the contact `name` (first token) is visible in the header/list, OR
      - the compose placeholder "type a message" is visible (empty draft), OR
      - a settle period passed with no error screen (number-addressed, saved contact whose
        header shows a name we don't know).
    Raises SendError if the number is not a Viber user or nothing sendable appears in time.
    Returns the OCR text of the confirmed chat.
    """
    deadline = time.time() + timeout
    name_token = (name or "").strip().split()[0].lower() if name else ""
    started = time.time()
    last = ""
    while time.time() < deadline:
        try:
            last = viber_ocr.read_open_chat()["text"].lower()
        except viber_ocr.OCRError:
            time.sleep(0.6)
            continue
        if "isn't on viber" in last or "not in your contact list" in last:
            raise SendError(f"{number} is not a Viber user — cannot send a message.")
        if "cannot add yourself" in last:
            raise SendError("Cannot message your own number (Viber blocks self-chat via number).")
        if name_token and name_token in last:
            return last
        if "type a message" in last:
            return last
        if not name_token and time.time() - started >= 4.0:
            return last  # number-addressed, no error after settle — accept
        time.sleep(0.8)
    raise SendError(
        f"Timed out opening {number}'s chat. Viber may be slow/minimized, the number may be "
        "unreachable, or (for a name) the contact's chat didn't come to the front."
    )


def open_chat(to: str, confirm: bool = True) -> str:
    """Open (or focus) the Viber conversation for `to`. Returns the resolved E.164 number.

    With confirm=True, polls until a sendable chat is visible (and errors if the number
    is not a Viber user).
    """
    if not viber_is_running():
        raise SendError("Viber is not running. Launch and sign in to Viber first.")
    number, name = resolve_recipient(to)
    subprocess.run(["open", f"viber://chat?number={number}"], check=True)
    if confirm:
        _wait_for_sendable_chat(number, name)
    else:
        time.sleep(5.0)  # desktop needs a few seconds to navigate
    return number


def _text_landed(text: str, ocr_text: str) -> bool:
    """Best-effort check that `text` appears in the OCR of the conversation.

    Compares an alphanumeric-only, lowercased signature so spacing/emoji differences and
    OCR noise don't cause false negatives. Returns True if we can't build a signature.
    """
    sig = re.sub(r"[^a-z0-9]", "", text.lower())[:24]
    if len(sig) < 6:
        return True  # too little ASCII to verify (e.g. emoji-only) — don't claim failure
    haystack = re.sub(r"[^a-z0-9]", "", ocr_text.lower())
    return sig in haystack


def _paste_into_compose(text: str, b: dict) -> None:
    """Click the compose box of the open chat, clear any draft, and paste `text` (no send).

    Assumes `text` is already on the clipboard. `b` is the live window bounds.
    """
    _click(*_point(_COMPOSE_FRAC, b))                 # focus compose box
    time.sleep(0.4)
    _key(_KEY_A, Quartz.kCGEventFlagMaskCommand)      # select any leftover draft
    time.sleep(0.1)
    _key(_KEY_DELETE)                                  # clear it
    time.sleep(0.15)
    _key(_KEY_V, Quartz.kCGEventFlagMaskCommand)      # paste
    time.sleep(0.4)


def paste_into_open_chat(text: str) -> dict:
    """Paste `text` into the CURRENTLY OPEN chat's compose box — no navigation, no send.

    Use this to drop a drafted reply into whatever chat the user has open, so they can
    review and send it themselves. The clipboard is saved and restored.
    """
    if not text:
        raise SendError("Refusing to draft an empty message.")
    if not viber_is_running():
        raise SendError("Viber is not running. Launch and sign in to Viber first.")

    saved = _get_clipboard()
    try:
        _set_clipboard(text)
        _focus_viber()
        _paste_into_compose(text, _window_bounds())
    finally:
        time.sleep(0.25)
        if saved is not None:
            _set_clipboard(saved)
    return {"drafted": True, "sent": False, "text": text}


def send_message(to: str, text: str, dry_run: bool = False) -> dict:
    """Send `text` to `to` via the Viber desktop app.

    Steps: resolve recipient -> open & confirm chat -> click compose -> paste ->
    click send button -> verify the message appears. The user's clipboard is saved and
    restored. With dry_run=True the text is pasted into the compose box but NOT sent.
    """
    if not text:
        raise SendError("Refusing to send an empty message.")

    number = open_chat(to, confirm=True)

    saved = _get_clipboard()
    verified = None
    try:
        _set_clipboard(text)
        _focus_viber()
        b = _window_bounds()
        _paste_into_compose(text, b)

        if dry_run:
            return {"recipient": number, "text": text, "sent": False, "dry_run": True}

        _click(*_point(_SEND_BTN_FRAC, b))   # click send
        time.sleep(0.8)

        # Verify the message actually appears in the conversation.
        try:
            ocr = viber_ocr.read_open_chat()["text"]
            verified = _text_landed(text, ocr)
        except viber_ocr.OCRError:
            verified = None
    finally:
        time.sleep(0.25)
        if saved is not None:
            _set_clipboard(saved)

    return {
        "recipient": number,
        "text": text,
        "sent": True,
        "dry_run": False,
        "verified": verified,  # True = confirmed on screen; False = not seen; None = couldn't check
    }
