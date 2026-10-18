"""Read one visible Text element at a calibrated point. No input or UI actions."""
import ast
import json
import os
import socket
import subprocess
import sys
import time


def read_text(req, Atspi):
    Atspi.set_timeout(750, 750)
    desktop = Atspi.get_desktop(0)
    apps = [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]
    apps = [app for app in apps if app.get_name() == req['application']
            and app.get_process_id() == req['pid']]
    if len(apps) != 1:
        raise ValueError('application mismatch')
    frames = [apps[0].get_child_at_index(i) for i in range(apps[0].get_child_count())]
    frames = [frame for frame in frames if frame.get_role_name() == 'frame'
              and frame.get_name() == req['window']]
    if len(frames) != 1:
        raise ValueError('window mismatch')
    frame = frames[0]
    bounds = frame.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    if [bounds.x, bounds.y, bounds.width, bounds.height] != req['geometry']:
        raise ValueError('geometry mismatch')
    px, py = req['point']
    pending, candidates = [(frame, 0)], []
    visited = 0
    deadline = time.monotonic() + 3
    while pending:
        if time.monotonic() > deadline or visited >= 700:
            raise ValueError('tree budget exceeded')
        node, depth = pending.pop()
        visited += 1
        if 'Text' in node.get_interfaces():
            states = node.get_state_set()
            component = node.get_component_iface()
            if component and states.contains(Atspi.StateType.SHOWING) and states.contains(Atspi.StateType.VISIBLE):
                rect = component.get_extents(Atspi.CoordType.SCREEN)
                if rect.x <= px < rect.x + rect.width and rect.y <= py < rect.y + rect.height:
                    candidates.append(node)
        if depth < 14:
            for i in range(node.get_child_count()):
                child = node.get_child_at_index(i)
                if child is not None:
                    pending.append((child, depth + 1))
    if len(candidates) != 1:
        raise ValueError('text missing or ambiguous')
    interface = candidates[0].get_text_iface()
    count = Atspi.Text.get_character_count(interface)
    if not 0 <= count <= 20000:
        raise ValueError('text exceeds limit')
    # GI's Accessible.get_text() shadows the Text interface method on this object.
    value = Atspi.Text.get_text(interface, 0, count)
    if count != Atspi.Text.get_character_count(interface) or len(value) > 10000:
        raise ValueError('text changed or exceeds limit')
    return value


def main():
    try:
        req = json.loads(sys.stdin.read(16000))
        if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
            raise ValueError('session bus missing')
        # A stale AT-SPI socket can abort libatspi, so verify the returned address first.
        address = ast.literal_eval(subprocess.check_output([
            'gdbus', 'call', '--session', '--dest', 'org.a11y.Bus', '--object-path',
            '/org/a11y/bus', '--method', 'org.a11y.Bus.GetAddress'], text=True, timeout=2).strip())[0]
        if not address.startswith('unix:path='):
            raise ValueError('unsupported bus')
        path = address.split('unix:path=', 1)[1].split(',', 1)[0]
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(.5)
            connection.connect(path)
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        print(json.dumps({'text': read_text(req, Atspi)}, ensure_ascii=False))
    except Exception:
        print(json.dumps({'error': 'text_interface_missing'}))


if __name__ == '__main__':
    main()
