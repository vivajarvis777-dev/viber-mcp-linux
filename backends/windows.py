r"""Windows backend for Viber Desktop — SCAFFOLD (not yet implemented).

Every method raises NotImplementedError with notes on the intended approach. Fill these in to
support Windows; the domain logic (`viber_send.py` / `viber_ocr.py`) needs no changes.

Recommended stack
-----------------
- **UI Automation (UIA) is the big win on Windows.** Unlike macOS (where Viber's Qt exposes no
  usable accessibility tree), Qt-on-Windows generally exposes a real UIA tree. So prefer targeting
  actual elements (compose edit, send button, search box, chat-list items) by ControlType / Name /
  AutomationId and invoking them — far more robust than screen coordinates and OCR.
  Libraries: `uiautomation` (simplest) or `pywinauto` (backend="uia").
- **Process / window / focus:** `psutil` (or `tasklist`) for the process; `pywin32`
  (`win32gui`/`win32process`) or UIA for finding + foregrounding the window
  (`ShowWindow(SW_RESTORE)` + `SetForegroundWindow`).
- **URL scheme:** `os.startfile("viber://chat?number=...")` (or `subprocess` `cmd /c start`).
- **Clipboard:** `win32clipboard` (or `pyperclip`).
- **OCR fallback (only if UIA text isn't enough):** capture with `PrintWindow` /
  `Windows.Graphics.Capture`, OCR with `Windows.Media.Ocr` (via `winrt`/`winsdk`, or `winocr`).

Interface note — clicking results
----------------------------------
`observe()` and `click_result(norm_y)` are coordinate-oriented for the OCR-based macOS backend. On
Windows you'll likely want `observe()` to return one entry per UIA text/list element AND stash a
parallel list of the underlying UIA elements (keyed by normalized y). Then `click_result(norm_y)`
maps `norm_y` back to the stored element and calls its Invoke/Select pattern — no pixels needed.
The `{text, x, y}` contract still holds: derive x,y from each element's BoundingRectangle normalized
over the window rect. (The domain only uses x for left-column filtering and y for ordering/row pick.)

Viber data paths on Windows (for reference): `%APPDATA%\ViberPC\<phone>\` — same encrypted `viber.db`.
"""

from __future__ import annotations

from .base import Backend, OCRError

_TODO = "WindowsBackend is a scaffold — implement this method (see module docstring)."


class WindowsBackend(Backend):
    name = "windows"

    # --- app / process ---------------------------------------------------------------
    def app_running(self) -> bool:
        # psutil: any(p.name().lower() == "viber.exe" for p in psutil.process_iter(["name"]))
        raise NotImplementedError(_TODO)

    def focus(self) -> None:
        # Find Viber's top window (UIA or win32gui.FindWindow), ShowWindow(SW_RESTORE) +
        # SetForegroundWindow. Un-minimize if needed.
        raise NotImplementedError(_TODO)

    def open_url(self, url: str) -> None:
        # os.startfile(url)  (registers/opens the viber:// handler)
        raise NotImplementedError(_TODO)

    # --- perception ------------------------------------------------------------------
    def observe(self) -> list[dict]:
        # Preferred: walk the Viber UIA tree, emit {text, x, y} per text/list element with x,y
        # normalized over the window BoundingRectangle; stash the elements for click_result().
        # Fallback: PrintWindow capture + Windows.Media.Ocr. Raise OCRError if no window.
        raise NotImplementedError(_TODO)

    # --- clipboard -------------------------------------------------------------------
    def clipboard_get(self) -> str | None:
        raise NotImplementedError(_TODO)

    def clipboard_set(self, text: str) -> None:
        raise NotImplementedError(_TODO)

    # --- keyboard --------------------------------------------------------------------
    def type_text(self, text: str) -> None:
        # UIA ValuePattern.SetValue on the focused edit is most reliable; else SendInput with
        # KEYEVENTF_UNICODE per character.
        raise NotImplementedError(_TODO)

    def select_all(self) -> None:
        # SendInput Ctrl+A (note: Ctrl, not Cmd).
        raise NotImplementedError(_TODO)

    def delete(self) -> None:
        # SendInput Delete/Backspace.
        raise NotImplementedError(_TODO)

    def paste(self) -> None:
        # SendInput Ctrl+V.
        raise NotImplementedError(_TODO)

    # --- clicks on Viber UI elements -------------------------------------------------
    def click_compose(self) -> None:
        # UIA: find the message input Edit control and SetFocus()/Invoke; avoids coordinates.
        raise NotImplementedError(_TODO)

    def click_send(self) -> None:
        # UIA: find the send Button by Name/AutomationId and InvokePattern.Invoke().
        raise NotImplementedError(_TODO)

    def click_search(self) -> None:
        # UIA: find the search Edit and SetFocus().
        raise NotImplementedError(_TODO)

    def click_result(self, norm_y: float) -> None:
        # Map norm_y to the UIA element stashed during observe() and Invoke/Select it.
        raise NotImplementedError(_TODO)

    def click_panel_close(self) -> None:
        # UIA: find the info/settings panel close Button; or no-op if you close panels a different way.
        raise NotImplementedError(_TODO)
