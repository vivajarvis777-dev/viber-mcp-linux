"""Backend selection. Returns the singleton Backend for the current platform."""

from __future__ import annotations

import sys

from .base import Backend, OCRError

_backend: Backend | None = None


def get_backend() -> Backend:
    """Return the platform Backend (cached). Raises on unsupported platforms."""
    global _backend
    if _backend is None:
        if sys.platform == "darwin":
            from .macos import MacBackend
            _backend = MacBackend()
        else:
            # Port target: implement backends/windows.py (WindowsBackend, likely via UI
            # Automation) or backends/linux.py, then wire them up here.
            raise NotImplementedError(
                f"No Viber backend for platform {sys.platform!r} yet (only macOS is implemented)."
            )
    return _backend


__all__ = ["Backend", "OCRError", "get_backend"]
