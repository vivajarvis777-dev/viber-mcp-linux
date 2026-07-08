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

# UI positions as fractions of the Viber window (measured on v28.2.0 with the contact-info
# panel CLOSED). Recomputed from live window bounds each call.
_COMPOSE_FRAC = (0.45, 0.96)
_SEND_BTN_FRAC = (0.97, 0.955)
_SEARCH_FRAC = (0.15, 0.075)        # search box in the top-left


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


def _type(text: str) -> None:
    """Type `text` via HID keyboard events (handles unicode/emoji)."""
    for ch in text:
        for down in (True, False):
            e = Quartz.CGEventCreateKeyboardEvent(_SRC, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(e, len(ch), ch)
            _post(e)
            time.sleep(0.012)


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


def reply(text: str) -> dict:
    """Send `text` into the CURRENTLY OPEN chat — no navigation, no recipient resolution.

    Use after read_open_chat when the desired chat is already on screen. Clears any draft,
    pastes, clicks send, and OCR-verifies. The clipboard is saved and restored.
    """
    if not text:
        raise SendError("Refusing to send an empty message.")
    if not viber_is_running():
        raise SendError("Viber is not running. Launch and sign in to Viber first.")

    saved = _get_clipboard()
    verified = None
    try:
        _set_clipboard(text)
        _focus_viber()
        b = _window_bounds()
        _paste_into_compose(text, b)
        _click(*_point(_SEND_BTN_FRAC, b))
        time.sleep(1.3)  # let the sent bubble render before verifying
        try:
            verified = _text_landed(text, viber_ocr.read_open_chat()["text"])
        except viber_ocr.OCRError:
            verified = None
    finally:
        time.sleep(0.25)
        if saved is not None:
            _set_clipboard(saved)
    return {"sent": True, "text": text, "verified": verified}


# Search-result rows that are not contacts/chats and must never be opened.
_RESULT_SKIP = {
    "new group", "new community", "new channel", "new call link", "all contacts",
    "viber only", "contacts", "search...", "search", "chats", "unread", "favorites",
    "all", "recent", "messages", "people", "share a link to your viber call",
    # search-result section headers
    "conversations", "channels", "businesses", "bots", "cars", "communities",
}

# Observations above this normalized y are the search bar / top nav, not result rows.
_RESULTS_TOP_Y = 0.12
_PHONE_RE = re.compile(r"^[+\d][\d\s()\-]+$")
_COUNT_RE = re.compile(r"^\d+\s+contacts?$")


def _score_result(query: str, text: str) -> int:
    """Rank how well an OCR'd result row matches `query`. Higher = better; <=0 = reject."""
    q = query.lower().strip()
    t = text.lower().strip()
    if not t or t in _RESULT_SKIP or _PHONE_RE.match(t) or _COUNT_RE.match(t):
        return -1
    if t == q:
        return 4
    if t.startswith(q):
        return 3
    if any(w.startswith(q) for w in t.split()):  # any word starts with the query
        return 3
    if q in t:                                    # substring only (weak, e.g. "ivy" in "Divya")
        return 1
    return -1


def _find_result_row(query: str, observations: list[dict], b: dict):
    """Pick the best-matching result row; return (text, x, y, score) or None.

    Only considers the left column (the results list). Prefers exact/prefix matches over
    substrings so, e.g., searching "Ivy" opens "Ivy Cloma-Rosales", not "Divya".
    """
    candidates = []
    for o in observations:
        if o["x"] >= 0.35 or o["y"] < _RESULTS_TOP_Y:  # left column, below the search bar
            continue
        score = _score_result(query, o["text"])
        if score > 0:
            candidates.append((score, o["y"], o["text"]))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[0], c[1]))  # best score, then topmost
    score, y, text = candidates[0]
    x = b["X"] + b["Width"] * 0.14
    click_y = b["Y"] + b["Height"] * y
    return text, x, click_y, score


def search_and_open(name: str) -> dict:
    """Search Viber for `name` and open the best-matching result.

    Works for any Viber contact/chat by name (not limited to contacts.json). Types into the
    search box, then picks the result row that best matches `name` (exact/prefix beats
    substring) by OCR-ing the results and clicking that row's actual position. Raises
    SendError if there's no confident match. Returns the opened chat's visible text plus the
    matched name and a `low_confidence` flag (true if only a weak substring match was found).
    """
    name = name.strip()
    if not name:
        raise SendError("Search query is empty.")
    if not viber_is_running():
        raise SendError("Viber is not running. Launch and sign in to Viber first.")

    _focus_viber()
    b = _window_bounds()

    _click(*_point((0.25, 0.08), b))   # click the search ✕ to clear any previous query
    time.sleep(0.4)
    _click(*_point(_SEARCH_FRAC, b))   # focus the search field
    time.sleep(0.4)
    _type(name)
    time.sleep(1.6)                     # let results populate

    _, obs = viber_ocr._capture_and_ocr()
    match = _find_result_row(name, obs, b)
    if match is None:
        raise SendError(
            f"No matching contact/chat found for '{name}' in Viber search. Try a fuller name "
            "or use a phone number with open_chat."
        )
    matched_text, x, y, score = match
    _click(x, y)
    time.sleep(1.2)

    result = _wait_for_sendable_chat(number=name, name=name, timeout=8.0)
    return {
        "query": name,
        "matched": matched_text,
        "low_confidence": score <= 1,  # only a substring match — verify before sending
        "opened": True,
        "text": result,
    }


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
        time.sleep(1.3)  # let the sent bubble render before verifying

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
