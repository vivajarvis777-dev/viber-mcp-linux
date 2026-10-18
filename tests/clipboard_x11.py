"""Hostile selection owners on a fresh Xvfb only; never use the user's DISPLAY."""
import ctypes as C
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Request(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int),
                ('display', C.c_void_p), ('owner', C.c_ulong), ('requestor', C.c_ulong),
                ('selection', C.c_ulong), ('target', C.c_ulong), ('property', C.c_ulong),
                ('time', C.c_ulong)]


class Notify(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int),
                ('display', C.c_void_p), ('requestor', C.c_ulong), ('selection', C.c_ulong),
                ('target', C.c_ulong), ('property', C.c_ulong), ('time', C.c_ulong)]


class Event(C.Union):
    _fields_ = [('request', Request), ('notify', Notify), ('pad', C.c_long * 24)]


def owner(mode):
    assert os.environ.get('VIBER_ISOLATED_CLIPBOARD_TEST') == os.environ.get('DISPLAY')
    x = C.CDLL('libX11.so.6')
    def bind(name, result, args):
        f = getattr(x, name); f.restype = result; f.argtypes = args; return f
    ptr, ul, integer = C.c_void_p, C.c_ulong, C.c_int
    opened = bind('XOpenDisplay', ptr, [C.c_char_p])(None)
    assert opened
    root = bind('XDefaultRootWindow', ul, [ptr])(opened)
    create = bind('XCreateSimpleWindow', ul, [ptr, ul, integer, integer, C.c_uint,
                                             C.c_uint, C.c_uint, ul, ul])
    intern = bind('XInternAtom', ul, [ptr, C.c_char_p, integer])
    atom = lambda name: intern(opened, name.encode(), 0)
    atoms = {name: atom(name) for name in ('CLIPBOARD', 'TARGETS', 'UTF8_STRING', 'STRING', 'ATOM')}
    set_owner = bind('XSetSelectionOwner', integer, [ptr, ul, ul, ul])
    change = bind('XChangeProperty', integer, [ptr, ul, ul, ul, integer, integer, ptr, integer])
    send = bind('XSendEvent', integer, [ptr, ul, integer, C.c_long, ptr])
    flush = bind('XFlush', integer, [ptr])
    next_event = bind('XNextEvent', integer, [ptr, ptr])
    window = create(opened, root, 0, 0, 1, 1, 0, 0, 0)
    set_owner(opened, atoms['CLIPBOARD'], window, 0)
    bind('XSync', integer, [ptr, integer])(opened, 0)
    print(json.dumps({'ready': True, 'window': window}), flush=True)
    switched = False
    while True:
        event = Event(); next_event(opened, C.byref(event))
        if event.request.type != 30:  # SelectionRequest
            continue
        request = event.request
        prop = request.property or request.target
        if request.target == atoms['TARGETS']:
            data = (ul * 3)(atoms['TARGETS'], atoms['UTF8_STRING'], atoms['STRING'])
            change(opened, request.requestor, prop, atoms['ATOM'], 32, 0, data, 3)
        elif request.target == atoms['UTF8_STRING'] and mode == 'silent':
            continue
        elif (request.target == atoms['UTF8_STRING'] and mode in ('empty', 'unicode', 'wrongtype', 'switch')) or (
                request.target == atoms['STRING'] and mode == 'fallback'):
            value = b'' if mode == 'empty' else 'SYNTHETIC Привіт 👋'.encode()
            if mode in ('wrongtype', 'fallback'): value = b'ASCII downgrade'
            datatype = atoms['STRING'] if mode == 'wrongtype' or request.target == atoms['STRING'] else atoms['UTF8_STRING']
            buffer = C.create_string_buffer(value)
            if mode == 'switch' and not switched:
                replacement = create(opened, root, 0, 0, 1, 1, 0, 0, 0)
                set_owner(opened, atoms['CLIPBOARD'], replacement, 0); switched = True
            change(opened, request.requestor, prop, datatype, 8, 0, buffer, len(value))
        else:
            prop = 0  # Advertised target but refused conversion.
        reply = Event(); reply.notify.type = 31
        reply.notify.display = opened; reply.notify.requestor = request.requestor
        reply.notify.selection = request.selection; reply.notify.target = request.target
        reply.notify.property = prop; reply.notify.time = request.time
        send(opened, request.requestor, 0, 0, C.byref(reply)); flush(opened)


@contextmanager
def fixture(mode):
    process = subprocess.Popen([sys.executable, __file__, '--owner', mode], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
    try:
        assert select.select([process.stdout], [], [], 3)[0], 'Owner startup deadline'
        assert json.loads(process.stdout.readline())['ready']
        yield process
    finally:
        process.terminate()
        process.communicate(timeout=3)


def main():
    r, w = os.pipe()
    xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(w), '-screen', '0', '800x600x24',
                             '-nolisten', 'tcp'], pass_fds=(w,), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    os.close(w)
    try:
        assert select.select([r], [], [], 5)[0], 'Xvfb startup deadline'
        with os.fdopen(r) as pipe: display = pipe.readline().strip()
        assert display.isdigit()
        os.environ.update(DISPLAY=':' + display, VIBER_ISOLATED_CLIPBOARD_TEST=':' + display,
                          NO_AT_BRIDGE='1', GTK_MODULES='', GDK_BACKEND='x11')
        os.environ.pop('DBUS_SESSION_BUS_ADDRESS', None)
        os.environ.pop('XAUTHORITY', None)
        from linux_backend import SafetyError
        from x11_worker import Desktop
        for mode in ('refuse', 'fallback', 'wrongtype', 'silent', 'empty', 'unicode', 'switch'):
            with fixture(mode):
                if mode == 'refuse' and os.getenv('VIBER_XSEL'):
                    legacy = subprocess.run([os.environ['VIBER_XSEL'], '--clipboard', '--output'],
                                            capture_output=True, timeout=3, stdin=subprocess.DEVNULL)
                    print(json.dumps({'legacy_refused_rc': legacy.returncode,
                                      'legacy_refused_bytes': len(legacy.stdout)}), flush=True)
                start = time.monotonic()
                original_popen = subprocess.Popen
                readers = []
                def tracked_popen(args, *a, **kw):
                    child = original_popen(args, *a, **kw)
                    if any(str(arg).endswith('/clipboard_reader.py') for arg in args):
                        readers.append(child)
                    return child
                subprocess.Popen = tracked_popen
                try:
                    if mode == 'switch':
                        desktop = Desktop.__new__(Desktop)
                        desktop.guard = lambda **kw: None
                        desktop.clipboard_set = lambda *a: (_ for _ in ()).throw(AssertionError('Changed raced selection'))
                        with desktop.clipboard():
                            raise AssertionError('Allowed raced selection')
                    else:
                        data = Desktop.clipboard_get()
                except SafetyError:
                    assert mode not in ('empty', 'unicode'), mode
                else:
                    assert mode in ('empty', 'unicode'), 'Accepted failed conversion: ' + mode
                    assert data == (b'' if mode == 'empty' else 'SYNTHETIC Привіт 👋'.encode())
                finally:
                    subprocess.Popen = original_popen
                assert readers, 'Strict reader was not exercised'
                for child in readers:
                    assert child.returncode is not None
                    assert child.stdout.closed and child.stderr.closed
                    try:
                        os.waitpid(child.pid, os.WNOHANG)
                    except ChildProcessError:
                        pass  # Already reaped by subprocess.run, including timeout.
                    else:
                        raise AssertionError('Unreaped clipboard reader')
                assert time.monotonic() - start < 4, 'Read exceeded fixed deadline'
        print(json.dumps({'isolated_clipboard': True, 'strict_conversion_cases': 'passed',
                          'cases': 7, 'readers_reaped': True, 'owner_race_blocked': True,
                          'live_viber': False}), flush=True)
    finally:
        xvfb.terminate(); xvfb.wait(timeout=3)


if __name__ == '__main__':
    owner(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--owner' else main()
