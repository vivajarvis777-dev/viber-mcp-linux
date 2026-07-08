"""Read the visible Viber conversation by OCR-ing the app window.

Viber's Qt accessibility tree is unreadable and its message DB is encrypted, so to "receive"
we capture the on-screen Viber window and run Apple's Vision text recognizer over the image.
This sees exactly what is currently visible in the frontmost/open chat.

Requires: Screen Recording permission granted to the process running this code.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import Quartz  # type: ignore
import Vision  # type: ignore
from Foundation import NSURL  # type: ignore


class OCRError(Exception):
    """Raised when the Viber window can't be found or captured."""


def find_viber_window() -> dict:
    """Return the largest on-screen window owned by Viber.

    Chooses the biggest window so we pick the main chat window rather than a tooltip
    or notification. Raises OCRError if none is visible (app hidden/minimized).
    """
    options = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
    # The macOS window owner is "Rakuten Viber" (the app's CFBundleName), so match
    # any owner containing "viber" rather than an exact string.
    # Skip the tiny menu-bar / status window (e.g. 38x43) so we always get the main chat window.
    viber = [
        w
        for w in windows
        if "viber" in (w.get("kCGWindowOwnerName") or "").lower()
        and w.get("kCGWindowNumber")
        and float(w.get("kCGWindowBounds", {}).get("Width", 0)) > 200
        and float(w.get("kCGWindowBounds", {}).get("Height", 0)) > 200
    ]
    if not viber:
        raise OCRError(
            "No visible Viber window found. Make sure Viber is running, unminimized, "
            "and a chat is open in the foreground."
        )

    def area(w: dict) -> float:
        b = w.get("kCGWindowBounds", {})
        return float(b.get("Width", 0)) * float(b.get("Height", 0))

    return max(viber, key=area)


def capture_window(window_id: int, out_path: str) -> None:
    """Capture a single window by id to a PNG using the system screencapture tool.

    -x = no capture sound, -o = omit window shadow, -l = capture window by id.
    """
    proc = subprocess.run(
        ["screencapture", "-x", "-o", "-l", str(window_id), out_path],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0 or not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
        raise OCRError(
            "Failed to capture the Viber window. Grant Screen Recording permission to the "
            f"terminal/host process in System Settings. Detail: {proc.stderr.strip()}"
        )


def ocr_observations(image_path: str) -> list[dict]:
    """Run Apple Vision OCR; return observations with normalized positions.

    Each dict: {"text", "x", "y"} where x is the left edge (0=left, 1=right) and y is the
    top position (0=top, 1=bottom), both normalized 0..1. Sorted top-to-bottom.
    """
    url = NSURL.fileURLWithPath_(image_path)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)

    results: list[dict] = []

    def _completion(request, error):
        for obs in request.results() or []:
            top = obs.topCandidates_(1)
            if not top:
                continue
            box = obs.boundingBox()  # origin bottom-left
            results.append(
                {
                    "text": top[0].string(),
                    "x": box.origin.x,
                    "y": 1.0 - (box.origin.y + box.size.height),  # flip to top-down
                }
            )

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(_completion)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise OCRError(f"Vision OCR failed: {error}")

    results.sort(key=lambda o: o["y"])
    return results


def ocr_image(image_path: str) -> list[str]:
    """Run Apple Vision text recognition on an image; return lines top-to-bottom."""
    return [o["text"] for o in ocr_observations(image_path)]


def _capture_and_ocr() -> tuple[int, list[dict]]:
    window = find_viber_window()
    window_id = int(window["kCGWindowNumber"])
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        capture_window(window_id, tmp.name)
        obs = ocr_observations(tmp.name)
    return window_id, obs


def read_open_chat() -> dict:
    """Capture the visible Viber window and OCR it.

    Returns the recognized lines and the joined text of the currently-open conversation.
    """
    window_id, obs = _capture_and_ocr()
    lines = [o["text"] for o in obs]
    return {
        "window_id": window_id,
        "line_count": len(lines),
        "lines": lines,
        "text": "\n".join(lines),
    }


# The chat-list sidebar occupies roughly the left third of the window.
_SIDEBAR_MAX_X = 0.30


def read_chat_list() -> dict:
    """Capture the window and return only the left-sidebar (chat list) text.

    Filters OCR to the left column so the returned lines are the chat list — contact
    names, message previews, timestamps, and unread counts — without the open
    conversation's text mixed in. Order is top-to-bottom (most recent first).
    """
    window_id, obs = _capture_and_ocr()
    lines = [o["text"] for o in obs if o["x"] < _SIDEBAR_MAX_X]
    return {
        "window_id": window_id,
        "line_count": len(lines),
        "lines": lines,
        "text": "\n".join(lines),
    }
