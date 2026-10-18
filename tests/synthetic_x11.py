"""Synthetic GTK fixture and real X11/OCR test in a private Xvfb; never Viber."""
import ctypes
import base64
import io
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fixture(profile_path):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib, Gdk
    # Only in the private test display; exercise production owner/class checks.
    ctypes.CDLL(None).prctl(15, b'Viber', 0, 0, 0)
    window = Gtk.Window(title='Synthetic Viber fixture - no network')
    window.set_wmclass('synthetic', 'Viber')
    window.set_default_size(800, 600)
    window.set_resizable(False)
    fixed = Gtk.Fixed()
    window.add(fixed)
    css = Gtk.CssProvider()
    css.load_from_data(b'* { font-family: DejaVu Sans; font-size: 18px; background: white; color: black; }')
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 800)

    def put(widget, x, y, w, h):
        widget.set_size_request(w, h)
        fixed.put(widget, x, y)
        return widget

    put(Gtk.Label(label='Connected'), 10, 5, 200, 35)
    search = put(Gtk.Entry(), 10, 50, 200, 40)
    search.set_placeholder_text('Search...')
    put(Gtk.Label(label='+12025550123'), 240, 10, 300, 40)
    conversation = put(Gtk.Label(label='SYNTHETIC conversation only'), 240, 90, 520, 270)
    put(Gtk.Label(label='SYNTHETIC sidebar only'), 5, 120, 220, 260)
    overlay = put(Gtk.Overlay(), 240, 450, 450, 120)
    composer = Gtk.TextView()
    overlay.add(composer)
    placeholder = Gtk.Label(label='Type a message...')
    placeholder.set_halign(Gtk.Align.START)
    placeholder.set_valign(Gtk.Align.START)
    overlay.add_overlay(placeholder)
    overlay.set_overlay_pass_through(placeholder, True)
    buffer = composer.get_buffer()
    buffer.connect('changed', lambda *_: placeholder.set_visible(buffer.get_char_count() == 0))
    send = put(Gtk.Button(label='Send'), 700, 470, 80, 45)

    def clicked(*_):
        conversation.set_text(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True))
        buffer.set_text('')
    send.connect('clicked', clicked)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()

    def ready():
        wid = window.get_window().get_xid()
        # Minimal EWMH properties on this isolated server (no window manager needed).
        xlib = ctypes.CDLL('libX11.so.6')
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        display = xlib.XOpenDisplay(None)
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        root = xlib.XDefaultRootWindow(display)
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        xlib.XInternAtom.restype = ctypes.c_ulong
        atom = lambda name: xlib.XInternAtom(display, name.encode(), 0)
        xlib.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                        ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_void_p, ctypes.c_int]
        active = atom('_NET_ACTIVE_WINDOW')
        for prop, kind, value in ((active, atom('WINDOW'), wid),
                                   (atom('_NET_SUPPORTED'), atom('ATOM'), active)):
            data = (ctypes.c_ulong * 1)(value)
            xlib.XChangeProperty(display, root, prop, kind, 32, 0, data, 1)
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        xlib.XFlush(display)
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XCloseDisplay(display)
        subprocess.run(['xdotool', 'windowfocus', str(wid)], check=True)
        size = list(window.get_size())
        profile = {'version': 1, 'window_size': size, 'languages': 'eng+ukr+rus',
                   'input_calibrated': True, 'send_calibrated': True,
                   'regions': {'status': [0, 0, 220, 40], 'search': [10, 50, 200, 40],
                               'header': [240, 0, 520, 60], 'identity': [240, 0, 300, 60],
                               'conversation': [240, 80, 520, 300],
                               'sidebar': [0, 110, 225, 300], 'composer': [240, 450, 450, 120]},
                   'points': {'composer': [300, 485], 'search': [100, 70], 'send': [740, 490]},
                   'empty_composer_labels': ['Type a message...']}
        Path(profile_path).write_text(json.dumps(profile))
        return False
    GLib.timeout_add(250, ready)
    Gtk.main()


def main():
    r, w = os.pipe()
    xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(w), '-screen', '0',
                             '1000x800x24', '-nolisten', 'tcp'], pass_fds=(w,),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(w)
    app = None
    try:
        assert select.select([r], [], [], 5)[0], 'Xvfb startup timed out'
        with os.fdopen(r) as pipe:
            display = pipe.readline().strip()
        assert display.isdigit()
        os.environ.update(DISPLAY=':' + display, XDG_SESSION_TYPE='x11',
                          VIBER_ALLOW_GUI='1', VIBER_ALLOW_INPUT='1', VIBER_ENABLE_SEND='1')
        with tempfile.TemporaryDirectory(prefix='viber-x11-fixture-') as tmp:
            path = Path(tmp) / 'profile.json'
            app = subprocess.Popen(['/usr/bin/python3', __file__, '--fixture', str(path)],
                                   stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 8
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            assert path.exists(), 'Fixture did not start'
            from x11_worker import Desktop
            from linux_backend import X11Backend
            Desktop.clipboard_set('SYNTHETIC original clipboard'.encode())
            backend = X11Backend(str(path), timeout=12)
            assert backend.identity() == '+12025550123'
            assert backend.draft() == ''
            value = 'Привіт 👋\nЮнікод ї є І — SYNTHETIC'
            backend.write(value, '+12025550123')
            assert backend.draft() == value
            assert Desktop.clipboard_get() == b'SYNTHETIC original clipboard'
            assert 'conversation only' in backend.read('conversation')['text']
            assert 'sidebar only' in backend.read('sidebar')['text']
            assert backend.messages() == []
            # Calibrate only the synthetic Send button after a verified draft is present.
            profile = json.loads(path.read_text())
            profile['regions']['send_button'] = [722, 472, 36, 36]
            desktop = Desktop(profile)
            image = desktop.capture('send_button')
            encoded = io.BytesIO(); image.save(encoded, format='PNG')
            profile['send_button_template'] = base64.b64encode(encoded.getvalue()).decode()
            path.write_text(json.dumps(profile))
            # One local synthetic button callback. No Viber process/network in this display.
            backend.send('+12025550123', value)
            assert backend.draft() == ''
            assert Desktop.clipboard_get() == b'SYNTHETIC original clipboard'
            print(json.dumps({'real_x11_fixture': True, 'ocr_identity': 'passed',
                              'unicode_clipboard_readback': 'passed', 'clipboard_restore': 'passed',
                              'scoped_reads': 'passed', 'local_button': 'passed', 'live_viber': False}))
    finally:
        if app:
            app.terminate()
            app.wait(timeout=5)
        xvfb.terminate()
        xvfb.wait(timeout=5)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--fixture':
        fixture(sys.argv[2])
    else:
        main()
