"""Opt-in read-only X11/OCR calibration. NEVER recipient authorization or sending.

Only a configured header rectangle is captured; screenshots stay in memory.
Does not focus windows, enumerate chats, access clipboard, or generate input.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from x11_worker import window_geometry


class ProbeError(RuntimeError):
    pass


def command(args, **kwargs):
    try:
        result = subprocess.run(args, capture_output=True, timeout=8, check=True, **kwargs)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise ProbeError('probe_command_failed') from None


def accessibility_socket(address):
    """Check transport without importing libatspi (which can abort on stale bus)."""
    if not address.startswith('unix:path='):
        return False
    path = address[len('unix:path='):].split(',')[0]
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(1)
            client.connect(path)
        return True
    except OSError:
        return False


def phone_summary(image, expected, executable='tesseract'):
    if not isinstance(expected, str) or not re.fullmatch(r'\+?[0-9]{7,15}', expected):
        raise ProbeError('invalid_literal')
    data = io.BytesIO()
    image.resize((image.width * 3, image.height * 3)).save(data, format='PNG')
    text = command([executable, 'stdin', 'stdout', '--psm', '6', '-l', 'eng'],
                   input=data.getvalue()).decode('utf-8', errors='replace')
    # Do not normalize spaces/country codes; OCR is advisory, not identity proof.
    phones = re.findall(r'(?<![\w+])\+?[0-9][0-9 ()-]{5,}[0-9](?!\w)', text)
    return {'source': 'x11_header_ocr', 'phone_candidates': len(phones),
            'literal_match_observed': len(phones) == 1 and phones[0] == expected,
            'international_form_observed': any(p.startswith('+') for p in phones),
            'recipient_verified': False, 'send_authorized': False,
            'private_text_returned': False}


def rectangle(profile, width, height):
    if profile.get('window_size') != [width, height]:
        raise ProbeError('window_geometry_changed')
    crop = profile.get('header_rect')
    if not isinstance(crop, list) or len(crop) != 4 or any(type(v) is not int for v in crop):
        raise ProbeError('invalid_header_rectangle')
    x, y, w, h = crop
    if min(x, y) < 0 or min(w, h) < 1 or x+w > width or y+h > height:
        raise ProbeError('invalid_header_rectangle')
    # Calibration is confined to the header, never history/sidebar or full screen.
    if x < width // 4 or y+h > min(160, height // 4):
        raise ProbeError('header_scope_required')
    return crop


def snapshot(profile):
    if os.getenv('VIBER_ALLOW_GUI') != '1':
        raise ProbeError('gui_disabled')
    ids = command(['xdotool', 'search', '--onlyvisible', '--class', '^(Viber|ViberPC)$']).decode().split()
    if len(ids) != 1 or not ids[0].isdigit():
        raise ProbeError('window_missing_or_ambiguous')
    wid = ids[0]
    def state():
        active = command(['xdotool', 'getactivewindow']).decode().strip()
        if active != wid:
            raise ProbeError('window_not_foreground')
        pid = command(['xdotool', 'getwindowpid', wid]).decode().strip()
        if not pid.isdigit():
            raise ProbeError('unexpected_window_owner')
        proc = Path('/proc') / pid
        if proc.stat().st_uid != os.getuid() or (proc / 'comm').read_text().strip() != 'Viber':
            raise ProbeError('unexpected_window_owner')
        return window_geometry(wid)
    before = state()
    x, y, width, height = before
    dx, dy, w, h = rectangle(profile, width, height)
    from PIL import ImageGrab
    image = ImageGrab.grab(bbox=(x+dx, y+dy, x+dx+w, y+dy+h))
    if state() != before:
        raise ProbeError('window_geometry_changed')
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--recipient', required=True)
    args = parser.parse_args()
    try:
        profile = json.loads(Path(args.profile).read_text())
        image = snapshot(profile)
        print(json.dumps(phone_summary(image, args.recipient, os.getenv('VIBER_TESSERACT', 'tesseract'))))
    except Exception as exc:
        # Never expose OCR text, file paths, process output or arbitrary exceptions.
        reason = str(exc) if isinstance(exc, ProbeError) else 'probe_failed'
        print(json.dumps({'error': reason, 'recipient_verified': False, 'send_authorized': False}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
