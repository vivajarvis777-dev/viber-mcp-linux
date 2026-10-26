"""Verify the active chat using Viber's native Copy number action.

Called inside the existing global UI mutex. No message input, no contact import,
no guessed country prefix, no reliance on a changed header or cached target.
"""
import re
import time
import uuid
import os
from pathlib import Path
from x11_worker import Desktop as _BaseDesktop, command, window_geometry
from linux_backend import SafetyError


class Desktop(_BaseDesktop):
    def state(self):
        # This production X11 session has no EWMH window manager. Use actual
        # X input focus, while retaining owner/PID/window/geometry guards.
        if command(['xdotool', 'getwindowfocus']).decode().strip() != self.wid:
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


def same_phone(observed, expected):
    value = re.sub(r'[\s()-]', '', observed)
    return bool(re.fullmatch(r'\+?[1-9][0-9]{7,14}', value)) and value.lstrip('+') == expected.lstrip('+')


def verify_current_recipient(auto, expected):
    _, _, width, height = auto.get_window_geometry()
    if width < 650 or height < 400:
        raise RuntimeError('recipient_identity_geometry_invalid')
    # The header anchor was inspected on the current Linux UI; menu selection
    # itself is semantic AT-SPI, never a guessed menu-row coordinate.
    desktop = Desktop({'version': 1, 'window_size': [width, height],
                       'input_calibrated': True})
    with desktop.clipboard():
        marker = ('viber-recipient-' + uuid.uuid4().hex).encode()
        desktop.clipboard_set(marker)
        try:
            desktop.click([430, 65], button=3)
            deadline = time.monotonic() + 2
            selected = False
            while time.monotonic() < deadline:
                matches = []
                for obj, _ in auto._walk_accessible():
                    try:
                        if str(obj.GetRoleName(dbus_interface='org.a11y.atspi.Accessible')) != 'menu item':
                            continue
                        name = str(obj.Get('org.a11y.atspi.Accessible', 'Name',
                                           dbus_interface='org.freedesktop.DBus.Properties'))
                        if name == 'Copy number' and auto._obj_extents(obj):
                            matches.append(obj)
                    except Exception:
                        continue
                if len(matches) == 1:
                    desktop.guard(input_action=True)
                    if not matches[0].DoAction(0, dbus_interface='org.a11y.atspi.Action'):
                        raise RuntimeError('recipient_identity_action_failed')
                    selected = True
                    break
                if len(matches) > 1:
                    raise RuntimeError('recipient_identity_menu_ambiguous')
                time.sleep(.05)
            if not selected:
                raise RuntimeError('recipient_identity_menu_unavailable')
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                raw = desktop.clipboard_get()
                if raw != marker:
                    if not same_phone(raw.decode('utf-8'), expected):
                        raise RuntimeError('recipient_identity_mismatch')
                    desktop.guard()
                    return True
                time.sleep(.05)
            raise RuntimeError('recipient_identity_unavailable')
        finally:
            desktop.key('Escape')


def open_verified_recipient(auto, expected):
    """Navigate using native phone proof; never trust cached phone or pixels.

    Caller holds the global UI mutex. All navigation happens before drafting or
    claiming a send. Only an identity mismatch permits another navigation path;
    clipboard, focus, geometry and composer failures stop immediately.
    """
    def verified():
        try:
            if verify_current_recipient(auto, expected) is not True:
                raise RuntimeError('recipient_identity_unavailable')
        except RuntimeError as error:
            if str(error) == 'recipient_identity_mismatch':
                return False
            raise
        auto.current_phone = expected
        return True

    if verified():
        return True
    # Discard stale cache before navigation, including when both paths fail.
    auto.current_phone = None
    for navigate in (auto.navigate_via_ui_search, auto._navigate_via_uri):
        navigate(expected)
        if verified():
            return True
    raise RuntimeError('recipient_identity_mismatch')
