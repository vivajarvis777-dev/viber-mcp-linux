"""One read-only UTF8_STRING conversion; failure is not an empty selection.

Run in a subprocess with a parent-owned deadline. No clipboard ownership changes,
legacy STRING fallback, user input, daemon, or inherited stdout-writing child.
"""
import base64
import json
import os
import sys
from linux_diagnostics import phase, record

MAX_BYTES = 1024 * 1024


def selection_bytes(selection):
    if selection is None:
        raise ValueError('conversion refused')
    length = selection.get_length()
    datatype = selection.get_data_type()
    if (not 0 <= length <= MAX_BYTES or selection.get_format() != 8
            or datatype is None or datatype.name() != 'UTF8_STRING'):
        raise ValueError('unsupported selection')
    data = selection.get_data()
    if data is None and length == 0:
        data = b''
    data = bytes(data)
    if len(data) != length:
        raise ValueError('length mismatch')
    data.decode('utf-8', errors='strict')
    return data


def read_once():
    try:
        record('clipboard_init_start', 'checkpoint')
        os.environ['NO_AT_BRIDGE'] = '1'
        os.environ['GTK_MODULES'] = ''
        os.environ['GDK_BACKEND'] = 'x11'
        os.environ['GSETTINGS_BACKEND'] = 'memory'
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        from gi.repository import Gdk, Gtk
        if not Gtk.init_check()[0]:
            raise ValueError('display unavailable')
        record('clipboard_init_ready', 'checkpoint')
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        target = Gdk.Atom.intern('UTF8_STRING', False)
        record('clipboard_convert_start', 'checkpoint')
        selection = clipboard.wait_for_contents(target)
        record('clipboard_convert_done', 'checkpoint')
        data = selection_bytes(selection)
        print(json.dumps({'utf8_base64': base64.b64encode(data).decode('ascii')}))
    except Exception:
        # Never print exception/UI data. The parent maps this to a closed reason.
        print(json.dumps({'error': 'clipboard_failed'}))
        return 1
    return 0


def main():
    with phase(os.getenv('VIBER_DIAGNOSTIC_PHASE', 'setup')):
        return read_once()


if __name__ == '__main__':
    sys.exit(main())
