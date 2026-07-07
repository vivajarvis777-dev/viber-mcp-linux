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
    viber = [
        w
        for w in windows
        if "viber" in (w.get("kCGWindowOwnerName") or "").lower()
        and w.get("kCGWindowNumber")
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


def ocr_image(image_path: str) -> list[str]:
    """Run Apple Vision text recognition on an image; return lines top-to-bottom."""
    url = NSURL.fileURLWithPath_(image_path)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)

    results: list[tuple[float, str]] = []

    def _completion(request, error):
        for obs in request.results() or []:
            top = obs.topCandidates_(1)
            if not top:
                continue
            text = top[0].string()
            # boundingBox origin is bottom-left; use -y so higher-on-screen sorts first.
            box = obs.boundingBox()
            y = box.origin.y
            results.append((-y, text))

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(_completion)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)

    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise OCRError(f"Vision OCR failed: {error}")

    results.sort(key=lambda t: t[0])
    return [text for _, text in results]


def read_open_chat() -> dict:
    """Capture the visible Viber window and OCR it.

    Returns the recognized lines and the joined text of the currently-open conversation.
    """
    window = find_viber_window()
    window_id = int(window["kCGWindowNumber"])
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        capture_window(window_id, tmp.name)
        lines = ocr_image(tmp.name)
    return {
        "window_id": window_id,
        "line_count": len(lines),
        "lines": lines,
        "text": "\n".join(lines),
    }
