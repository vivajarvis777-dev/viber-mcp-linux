"""Bounded, isolated AT-SPI adapter. No daemon, input grabs or clipboard mutation."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from linux_errors import CODES


class SafetyError(RuntimeError):
    pass


class LinuxBackend:
    worker_name = 'atspi_worker.py'
    def __init__(self, profile=None, timeout=8):
        self.profile = profile or os.getenv('VIBER_UI_PROFILE')
        self.timeout = timeout
        self.cancelled = threading.Event()
        self.process = None
        self.guard = threading.Lock()

    def health(self):
        return {'platform': 'linux', 'display_configured': bool(os.getenv('DISPLAY')),
                'session_bus_configured': bool(os.getenv('DBUS_SESSION_BUS_ADDRESS')),
                'profile_configured': bool(self.profile), 'gui_enabled': os.getenv('VIBER_ALLOW_GUI') == '1',
                'send_enabled': os.getenv('VIBER_ENABLE_SEND') == '1',
                'xdotool_available': bool(shutil.which('xdotool')),
                'live_chat_read': False, 'live_send_tested': False}

    def reset(self):
        self.cancelled.clear()

    def abort(self, process):
        process.kill()

    def stop(self):
        self.cancelled.set()
        with self.guard:
            if self.process and self.process.poll() is None:
                self.abort(self.process)
        # AT-SPI setTextContents/doAction never hold modifier keys or pointer grabs.
        return {'stopped': True, 'input_grabs': False}

    def call(self, action, **kwargs):
        if self.cancelled.is_set():
            raise SafetyError('cancelled')
        if os.getenv('VIBER_ALLOW_GUI') != '1' or not self.profile:
            raise SafetyError('GUI disabled or calibrated profile missing')
        request = {'action': action, 'profile': self.profile, **kwargs}
        with self.guard:
            if self.cancelled.is_set():
                raise SafetyError('cancelled')
            p = subprocess.Popen([os.getenv('VIBER_ATSPI_PYTHON', '/usr/bin/python3'),
                                  str(Path(__file__).with_name(self.worker_name))],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True)
            self.process = p
        try:
            out, _ = p.communicate(json.dumps(request, ensure_ascii=False), timeout=self.timeout)
            if self.cancelled.is_set():
                raise SafetyError('cancelled')
            if p.returncode:
                raise SafetyError('AT-SPI operation failed; no retry')
            try:
                response = json.loads(out)
                if not isinstance(response, dict) or not ('error' in response or 'result' in response):
                    raise ValueError()
            except (ValueError, TypeError):
                raise SafetyError('AT-SPI operation failed; no retry') from None
            if 'error' in response:
                code = response['error']
                raise SafetyError(code if isinstance(code, str) and code in CODES else 'operation_failed')
            return response['result']
        except subprocess.TimeoutExpired:
            self.abort(p)
            p.communicate()
            raise SafetyError('AT-SPI timeout; outcome may be unknown') from None
        finally:
            with self.guard:
                if self.process is p:
                    self.process = None

    def identity(self): return self.call('identity')
    def draft(self): return self.call('draft')
    def write(self, text, recipient): return self.call('write', text=text, recipient=recipient)
    def navigate(self, query): return self.call('navigate', query=query)
    def read(self, region): return self.call('read', region=region)
    def messages(self): return self.call('messages')
    def send(self, recipient, text): return self.call('send', recipient=recipient, text=text)


class X11Backend(LinuxBackend):
    """Opt-in calibrated X11 adapter. OCR never supplies stable message IDs."""
    worker_name = 'x11_worker.py'
    stable_message_ids = False

    def abort(self, process):
        # Let the worker restore its clipboard on cancellation/timeout.
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    def health(self):
        return {**super().health(), 'backend': 'x11-ocr',
                'ocr_available': bool(shutil.which(os.getenv('VIBER_TESSERACT', 'tesseract'))),
                'clipboard_available': bool(shutil.which('xclip')),
                'delivery_verification': False, 'stable_message_ids': False}

    def read_visible(self, region):
        return self.call('read', region=region)


def configured_backend():
    mode = os.getenv('VIBER_BACKEND', 'atspi')
    if mode not in ('atspi', 'x11'):
        raise SafetyError('Unknown VIBER_BACKEND; choose atspi or x11')
    return X11Backend() if mode == 'x11' else LinuxBackend()
