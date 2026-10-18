"""Bounded X11 worker: local OCR, calibrated regions, guarded clipboard input.

No automatic focusing, resizing, URI dispatch, coordinate guessing, or send retry.
Each worker handles exactly one request. OCR cannot prove delivery or message IDs.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
import base64
import ctypes
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

from linux_backend import SafetyError
from linux_errors import reason_code


def command(args, data=None, timeout=3):
    try:
        return subprocess.run(args, input=data, capture_output=True,
                              check=True, timeout=timeout,
                              env={**os.environ, 'LC_ALL': 'C'}).stdout
    except (OSError, subprocess.SubprocessError):
        raise SafetyError('ui_command_failed') from None


def normalized(text):
    """Whitespace/case only, never discard Cyrillic or punctuation."""
    return ' '.join(text.split()).casefold()


def selection_owner(clear=False):
    """Distinguish an empty selection from a failing clipboard provider."""
    xlib = ctypes.CDLL('libX11.so.6')
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    display = xlib.XOpenDisplay(None)
    if not display:
        raise SafetyError('clipboard_failed')
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    try:
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        xlib.XInternAtom.restype = ctypes.c_ulong
        atom = xlib.XInternAtom(display, b'CLIPBOARD', 0)
        xlib.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        xlib.XGetSelectionOwner.restype = ctypes.c_ulong
        owner = xlib.XGetSelectionOwner(display, atom)
        if clear:
            xlib.XSetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
            xlib.XSetSelectionOwner(display, atom, 0, 0)
            xlib.XFlush.argtypes = [ctypes.c_void_p]
            xlib.XFlush(display)
        return owner
    finally:
        xlib.XCloseDisplay(display)


def window_geometry(window_id):
    # xdotool 3.20160805 double-counts frame offsets on this XFCE session.
    # Use X11 absolute client coordinates, not parent-relative geometry.
    output = command(['xwininfo', '-id', window_id]).decode()
    values = []
    for key in ('Absolute upper-left X', 'Absolute upper-left Y', 'Width', 'Height'):
        match = re.search(r'^\s*' + re.escape(key) + r':\s*(-?\d+)\s*$', output, re.MULTILINE)
        if not match:
            raise SafetyError('window_geometry_changed')
        values.append(int(match[1]))
    return tuple(values)


def observed_phone(lines):
    """Formatting removal is not country-code inference. Require whole OCR line."""
    found = set()
    for line in lines:
        value = line['text'].strip()
        if line.get('confidence', 0) < 85:
            continue
        if re.fullmatch(r'\+?[0-9][0-9 ()-]{6,}[0-9]', value):
            value = re.sub(r'[ ()-]', '', value)
            if re.fullmatch(r'(?:\+[1-9][0-9]{7,14}|[0-9]{8,15})', value):
                found.add(value)
    if len(found) != 1:
        raise SafetyError('identity_not_visible')
    return found.pop()


def parse_tsv(data, scale):
    groups = {}
    for row in csv.DictReader(io.StringIO(data), delimiter='\t', quoting=csv.QUOTE_NONE):
        if row.get('level') != '5' or not row.get('text', '').strip():
            continue
        key = tuple(row[k] for k in ('page_num', 'block_num', 'par_num', 'line_num'))
        groups.setdefault(key, []).append(row)
    lines = []
    for words in groups.values():
        left = min(int(w['left']) for w in words)
        top = min(int(w['top']) for w in words)
        right = max(int(w['left']) + int(w['width']) for w in words)
        bottom = max(int(w['top']) + int(w['height']) for w in words)
        lines.append({'text': ' '.join(w['text'] for w in words),
                      'confidence': round(min(float(w['conf']) for w in words), 1),
                      'box': [left / scale, top / scale,
                              (right - left) / scale, (bottom - top) / scale]})
    return sorted(lines, key=lambda item: (item['box'][1], item['box'][0]))


class Desktop:
    def __init__(self, profile):
        self.profile = profile
        if os.getenv('VIBER_ALLOW_GUI') != '1':
            raise SafetyError('gui_disabled_or_profile_missing')
        if not os.getenv('DISPLAY') or os.getenv('XDG_SESSION_TYPE') == 'wayland':
            raise SafetyError('x11_required')
        try:
            ids = command(['xdotool', 'search', '--onlyvisible', '--class', '^(Viber|ViberPC)$']).decode().split()
        except SafetyError:
            raise SafetyError('window_missing_or_ambiguous') from None
        if len(ids) != 1 or not ids[0].isdigit():
            raise SafetyError('window_missing_or_ambiguous')
        self.wid = ids[0]
        self.geometry = self.state()
        if profile.get('window_size') != list(self.geometry[2:]):
            raise SafetyError('window_geometry_changed')
        if profile.get('version') != 1:
            raise SafetyError('profile_invalid')

    def state(self):
        if command(['xdotool', 'getactivewindow']).decode().strip() != self.wid:
            raise SafetyError('window_not_foreground')
        pid = command(['xdotool', 'getwindowpid', self.wid]).decode().strip()
        if not pid.isdigit():
            raise SafetyError('unexpected_window_owner')
        proc = Path('/proc') / pid
        if proc.stat().st_uid != os.getuid() or (proc / 'comm').read_text().strip() != 'Viber':
            raise SafetyError('unexpected_window_owner')
        if getattr(self, 'pid', pid) != pid:
            raise SafetyError('unexpected_window_owner')
        self.pid = pid
        return window_geometry(self.wid)

    def guard(self, input_action=False):
        if self.state() != self.geometry:
            raise SafetyError('window_geometry_changed')
        if input_action and os.getenv('VIBER_ALLOW_INPUT') != '1':
            raise SafetyError('input_disabled')
        if input_action and self.profile.get('input_calibrated') is not True:
            raise SafetyError('input_disabled')

    def rect(self, name):
        value = self.profile.get('regions', {}).get(name)
        if (not isinstance(value, list) or len(value) != 4 or
                any(type(v) is not int for v in value)):
            raise SafetyError('profile_invalid')
        x, y, w, h = value
        if min(x, y) < 0 or min(w, h) < 1 or x + w > self.geometry[2] or y + h > self.geometry[3]:
            raise SafetyError('profile_invalid')
        return value

    def capture(self, name):
        from PIL import ImageGrab
        self.guard()
        dx, dy, w, h = self.rect(name)
        x, y = self.geometry[:2]
        image = ImageGrab.grab(bbox=(x + dx, y + dy, x + dx + w, y + dy + h))
        self.guard()
        return image

    def ocr(self, name):
        image = self.capture(name)
        scale = 2
        data = io.BytesIO()
        image.resize((image.width * scale, image.height * scale)).save(data, format='PNG')
        env = dict(os.environ, OMP_THREAD_LIMIT='1')
        args = [os.getenv('VIBER_TESSERACT', 'tesseract'), 'stdin', 'stdout',
                '-l', self.profile.get('languages', 'eng+ukr+rus'), '--psm', '6', 'tsv']
        try:
            result = subprocess.run(args, input=data.getvalue(), capture_output=True,
                                    timeout=4, check=True, env=env)
        except FileNotFoundError:
            raise SafetyError('ocr_unavailable') from None
        except (OSError, subprocess.SubprocessError):
            raise SafetyError('ocr_failed') from None
        self.guard()
        return parse_tsv(result.stdout.decode(), scale)

    def read(self, region):
        started = time.monotonic()
        if region not in ('conversation', 'sidebar', 'header', 'status'):
            raise SafetyError('profile_invalid')
        lines = self.ocr(region)
        return {'source': 'x11_tesseract', 'region': region, 'visible_only': True,
                'lines': lines, 'text': '\n'.join(x['text'] for x in lines),
                'line_count': len(lines), 'elapsed_ms': round((time.monotonic() - started) * 1000),
                'recipient_verified': False, 'send_authorized': False}

    def identity(self):
        if self.profile.get('identity_mode') == 'clipboard_menu':
            return self.clipboard_identity()
        # A name, placeholder, sidebar hit or guessed country code is never identity.
        return observed_phone(self.ocr('identity'))

    def clipboard_identity(self):
        """Copy number from the current contact's calibrated header menu, then restore clipboard."""
        number = None
        try:
            with self.clipboard():
                sentinel = ('viber-identity-' + uuid.uuid4().hex).encode()
                self.clipboard_set(sentinel)
                self.click(self.point('identity_menu'), button=3)
                time.sleep(.12)
                self.click(self.point('copy_number'))
                deadline = time.monotonic() + .6
                while time.monotonic() < deadline:
                    value = self.clipboard_get()
                    if value != sentinel:
                        candidate = re.sub(r'[\s()-]', '', value.decode('utf-8'))
                        if re.fullmatch(r'(?:\+[1-9][0-9]{7,14}|[0-9]{8,15})', candidate):
                            number = candidate
                            break
                        raise SafetyError('identity_not_visible')
                    time.sleep(.03)
                if number is None:
                    raise SafetyError('identity_not_visible')
        finally:
            # Restore selection ownership before further X11 round trips. A successful
            # Copy number closes its menu itself; only failures require cancellation.
            if number is None:
                self.key('Escape')
        self.guard()
        return number

    def verify(self, recipient):
        if self.identity() != recipient:
            raise SafetyError('recipient_changed')

    def click(self, point, button=1):
        self.guard(input_action=True)
        if button not in (1, 3):
            raise SafetyError('profile_invalid')
        if (not isinstance(point, list) or len(point) != 2 or
                any(type(v) is not int for v in point) or
                not (0 <= point[0] < self.geometry[2] and 0 <= point[1] < self.geometry[3])):
            raise SafetyError('profile_invalid')
        # One click, no held pointer state, no global keyboard typing.
        command(['xdotool', 'mousemove', str(self.geometry[0] + point[0]),
                 str(self.geometry[1] + point[1]), 'click', str(button)])
        self.guard()

    def point(self, name):
        return self.profile.get('points', {}).get(name)

    def key(self, key):
        self.guard(input_action=True)
        if key not in ('ctrl+a', 'ctrl+c', 'ctrl+v', 'BackSpace', 'Right', 'Escape'):
            raise SafetyError('profile_invalid')
        command(['xdotool', 'key', '--clearmodifiers', key])
        self.guard()

    @staticmethod
    def clipboard_get():
        if os.getenv('VIBER_XSEL'):
            try:
                return subprocess.run([os.environ['VIBER_XSEL'], '--clipboard', '--output'],
                                      capture_output=True, timeout=3, check=True,
                                      env={**os.environ, 'LC_ALL': 'C.UTF-8'}).stdout
            except (OSError, subprocess.SubprocessError):
                raise SafetyError('clipboard_failed') from None
        return command(['xclip', '-selection', 'clipboard', '-o', '-target', 'UTF8_STRING'])

    @staticmethod
    def clipboard_set(data):
        # xclip owns selection in its normal background child. No pipe inheritance.
        try:
            args = ([os.environ['VIBER_XSEL'], '--clipboard', '--input'] if os.getenv('VIBER_XSEL')
                    else ['xclip', '-selection', 'clipboard', '-i', '-target', 'UTF8_STRING'])
            subprocess.run(args,
                           input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=2, check=True, env={**os.environ, 'LC_ALL': 'C.UTF-8'})
        except (OSError, subprocess.SubprocessError):
            raise SafetyError('clipboard_failed') from None

    clipboard_owner = staticmethod(selection_owner)

    @staticmethod
    def clipboard_clear():
        selection_owner(clear=True)

    @contextmanager
    def clipboard(self):
        self.guard(input_action=True)
        if self.clipboard_owner() == 0:
            try:
                yield
            finally:
                self.clipboard_clear()
            return
        try:
            targets = command(['xclip', '-selection', 'clipboard', '-o', '-target', 'TARGETS']).decode().split()
        except SafetyError:
            # Absence and inaccessible clipboard cannot be distinguished safely.
            raise SafetyError('clipboard_unsupported') from None
        allowed = {'TARGETS', 'MULTIPLE', 'TIMESTAMP', 'SAVE_TARGETS', 'UTF8_STRING', 'DELETE', 'INCR',
                   'STRING', 'TEXT', 'COMPOUND_TEXT', 'text/plain', 'text/plain;charset=utf-8'}
        if 'UTF8_STRING' not in targets or set(targets) - allowed:
            raise SafetyError('clipboard_unsupported')
        saved = self.clipboard_get()
        try:
            yield
        finally:
            self.clipboard_set(saved)

    def copy_field(self, name, allow_empty=False):
        sentinel = ('viber-mcp-' + uuid.uuid4().hex).encode()
        self.clipboard_set(sentinel)
        self.click(self.point(name))
        self.key('ctrl+a')
        self.key('ctrl+c')
        deadline = time.monotonic() + .6
        while time.monotonic() < deadline:
            data = self.clipboard_get()
            if data != sentinel:
                self.key('Right')
                return data.decode('utf-8')
            time.sleep(.03)
        self.key('Right')
        if allow_empty:
            return ''
        raise SafetyError('draft_unreadable')

    def draft(self):
        if self.profile.get('atspi_composer') is True:
            return self.read_composer_atspi()
        lines = self.ocr('composer')
        placeholders = {normalized(x) for x in self.profile.get('empty_composer_labels', [])}
        # Empty OCR is not proof of an empty draft. Require visible placeholder.
        empty_candidate = (len(lines) == 1 and normalized(lines[0]['text']) in placeholders
                           and lines[0]['confidence'] >= 75)
        with self.clipboard():
            return self.copy_field('composer', allow_empty=empty_candidate)

    def read_composer_atspi(self):
        self.guard()
        point = self.point('composer')
        request = {'application': self.profile.get('atspi_application', 'ViberPC'),
                   'window': self.profile.get('atspi_window', 'Rakuten Viber'),
                   'pid': int(self.pid), 'geometry': list(self.geometry),
                   'point': [self.geometry[0] + point[0], self.geometry[1] + point[1]]}
        args = [os.getenv('VIBER_ACCESSIBILITY_PYTHON', '/usr/bin/python3'),
                str(Path(__file__).with_name('atspi_text_reader.py'))]
        try:
            result = json.loads(command(args, json.dumps(request).encode(), timeout=6))
        except (ValueError, TypeError):
            raise SafetyError('text_interface_missing') from None
        self.guard()
        if not isinstance(result.get('text'), str):
            raise SafetyError('text_interface_missing')
        return result['text']

    def write(self, text, recipient):
        self.verify(recipient)
        old = self.draft()
        if old == text:
            return {'drafted': True}
        if old:
            raise SafetyError('draft_protected')
        with self.clipboard():
            self.click(self.point('composer'))
            self.clipboard_set(text.encode('utf-8'))
            self.key('ctrl+v')
            # Qt fetches CLIPBOARD asynchronously. Keep the paste payload owned
            # until that event is consumed before copy_field installs its sentinel.
            time.sleep(.25)
            # This checks all Unicode/newlines, not an ASCII-only OCR signature.
            if self.profile.get('atspi_composer') is True:
                deadline = time.monotonic() + 3
                actual = self.read_composer_atspi()
                while actual == '' and time.monotonic() < deadline:
                    time.sleep(.05)
                    actual = self.read_composer_atspi()
            else:
                actual = self.copy_field('composer')
            if actual != text:
                raise SafetyError('unicode_readback_mismatch')
        self.verify(recipient)
        return {'drafted': True}

    def navigate(self, query):
        if not isinstance(query, str) or not query.strip() or len(query) > 200 or '\x00' in query:
            raise SafetyError('search_missing_or_ambiguous')
        if self.profile.get('viber_launcher') and re.fullmatch(r'\+[1-9][0-9]{7,14}', query):
            return self.navigate_phone(query)
        # Search labels are explicit calibration, never guess compose field coordinates.
        current = self.ocr('search')
        labels = {normalized(x) for x in self.profile.get('empty_search_labels', [])}
        if len(current) != 1 or normalized(current[0]['text']) not in labels:
            raise SafetyError('draft_protected')
        with self.clipboard():
            self.click(self.point('search'))
            self.clipboard_set(query.encode())
            self.key('ctrl+v')
            try:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    results = self.ocr('results')
                    matches = [line for line in results if normalized(line['text']) == normalized(query)
                               and line['confidence'] >= 85]
                    if len(matches) > 1:
                        raise SafetyError('search_missing_or_ambiguous')
                    if len(matches) == 1:
                        x, y, _, _ = self.rect('results')
                        bx, by, bw, bh = matches[0]['box']
                        self.click([round(x + bx + bw / 2), round(y + by + bh / 2)])
                        return {'matched': matches[0]['text'], 'recipient_verified': False}
                    time.sleep(.1)
                raise SafetyError('search_missing_or_ambiguous')
            finally:
                # Clear only the query we just inserted. Never clear a changed field.
                if self.copy_field('search') == query:
                    self.click(self.point('search'))
                    self.key('ctrl+a')
                    self.key('BackSpace')

    def navigate_phone(self, number):
        from urllib.parse import quote
        self.guard(input_action=True)
        launcher = Path(self.profile['viber_launcher'])
        if not launcher.is_absolute() or not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise SafetyError('profile_invalid')
        # Explicitly local handler, never xdg-open/default-browser or a shell.
        try:
            # Qt helpers may inherit a captured stdout pipe after the launcher exits.
            # This handoff has no stdout contract; never wait for those pipes to close.
            subprocess.run([str(launcher), 'viber://chat?number=' + quote(number, safe='')],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=3, check=True)
        except (OSError, subprocess.SubprocessError):
            raise SafetyError('navigation_command_failed') from None
        # URI handoff returns before Qt has processed its queued navigation event.
        # Settling is never evidence: the copied contact number still must match.
        time.sleep(.3)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                if self.identity() == number:
                    return {'matched': number, 'recipient_verified': True, 'navigation': 'viber_uri'}
            except SafetyError as error:
                if str(error) not in ('identity_not_visible', 'recipient_changed'):
                    raise
            time.sleep(.1)
        raise SafetyError('recipient_changed')

    def assert_send_button(self):
        from PIL import Image, ImageChops, ImageStat
        encoded = self.profile.get('send_button_template', '')
        if not isinstance(encoded, str) or not 0 < len(encoded) <= 12000:
            raise SafetyError('profile_invalid')
        try:
            template = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
            if template.size != (36, 36) or template.format != 'PNG':
                raise ValueError('invalid template')
            template = template.convert('RGB')
        except (ValueError, OSError):
            raise SafetyError('profile_invalid') from None
        rect = self.rect('send_button')
        point = self.point('send')
        if rect[2:] != [36, 36] or point != [rect[0] + 18, rect[1] + 18]:
            raise SafetyError('profile_invalid')
        current = self.capture('send_button').convert('RGB')
        rms = ImageStat.Stat(ImageChops.difference(current, template)).rms
        if max(rms) > 6:
            raise SafetyError('send_button_changed')

    def preflight_send(self):
        self.guard(input_action=True)
        if os.getenv('VIBER_ENABLE_SEND') != '1':
            raise SafetyError('input_disabled')
        if self.profile.get('send_calibrated') is not True:
            raise SafetyError('input_disabled')
        status = normalized(' '.join(line['text'] for line in self.ocr('status')))
        if any(normalized(marker) in status for marker in self.profile.get('offline_labels',
                   ['No internet connection', 'Немає з’єднання', 'Нет подключения'])):
            raise SafetyError('offline')
        if not self.profile.get('send_button_template'):
            raise SafetyError('profile_invalid')
        return {'ready_for_guarded_attempt': True, 'delivered': None}

    def send(self, recipient, text):
        self.preflight_send()
        self.verify(recipient)
        if self.draft() != text:
            raise SafetyError('draft_changed')
        self.verify(recipient)
        self.assert_send_button()
        self.click(self.point('send'))
        return {'attempted': True, 'sent': None, 'delivered': None}


def dispatch(desktop, request):
    action = request['action']
    if action == 'read':
        return desktop.read(request['region'])
    if action == 'identity':
        return desktop.identity()
    if action == 'draft':
        return desktop.draft()
    if action == 'write':
        return desktop.write(request['text'], request['recipient'])
    if action == 'navigate':
        return desktop.navigate(request['query'])
    if action == 'send':
        return desktop.send(request['recipient'], request['text'])
    if action == 'preflight_send':
        return desktop.preflight_send()
    if action == 'messages':
        # OCR has no stable Viber message ID. Domain must never claim verified sent.
        return []
    raise SafetyError('unknown_operation')


def main():
    def cancelled(signum, frame):
        raise SafetyError('cancelled')
    signal.signal(signal.SIGTERM, cancelled)
    try:
        request = json.loads(sys.stdin.read(100_000))
        profile = json.loads(Path(request['profile']).read_text())
        result = dispatch(Desktop(profile), request)
        print(json.dumps({'result': result}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'error': reason_code(exc)}))


if __name__ == '__main__':
    main()
