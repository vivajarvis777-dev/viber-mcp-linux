import base64
from contextlib import nullcontext
import io
import pytest
from PIL import Image
from linux_backend import SafetyError
from x11_worker import Desktop


@pytest.mark.parametrize('copied,expected', [
    ('+1 (202) 555-0123', '+12025550123'),
    ('+1\u202f202\u202f555\u202f0123', '+12025550123'),
    ('0123456789', '0123456789'),
])
def test_menu_identity_is_phone_not_display_name(copied, expected):
    d = Desktop.__new__(Desktop)
    d.profile = {'identity_mode': 'clipboard_menu', 'points': {'identity_menu': [10, 10], 'copy_number': [20, 20]}}
    state = {}
    d.clipboard = lambda: nullcontext()
    d.clipboard_set = lambda value: state.update(value=value)
    d.clipboard_get = lambda: state['value']
    def click(point, button=1):
        if button == 1:
            state['value'] = copied.encode()
    d.click = click
    d.guard = lambda: None
    d.key = lambda key: state.update(last_key=key)
    assert d.identity() == expected
    assert 'last_key' not in state  # Copy number closes the menu; no extra key on success.


def test_wrong_context_menu_copy_is_rejected_and_closed():
    d = Desktop.__new__(Desktop)
    d.profile = {'identity_mode': 'clipboard_menu', 'points': {'identity_menu': [10, 10], 'copy_number': [20, 20]}}
    d.clipboard = lambda: nullcontext()
    d.clipboard_set = lambda value: None
    d.clipboard_get = lambda: b'https://example.invalid/group'
    d.click = lambda *a, **kw: None
    closed = []
    d.key = closed.append
    with pytest.raises(SafetyError, match='identity_not_visible'):
        d.identity()
    assert closed == ['Escape']


def desktop_with_template(current_color):
    d = Desktop.__new__(Desktop)
    b = io.BytesIO(); Image.new('RGB', (36, 36), 'white').save(b, format='PNG')
    d.geometry = (0, 0, 100, 100)
    d.profile = {'regions': {'send_button': [0, 0, 36, 36]}, 'points': {'send': [18, 18]},
                 'send_button_template': base64.b64encode(b.getvalue()).decode()}
    d.capture = lambda region: Image.new('RGB', (36, 36), current_color)
    return d


def test_send_button_must_match_calibrated_pixels():
    desktop_with_template('white').assert_send_button()
    with pytest.raises(SafetyError, match='send_button_changed'):
        desktop_with_template('black').assert_send_button()


def test_send_coordinate_must_be_template_center():
    d = desktop_with_template('white')
    d.profile['points']['send'] = [50, 50]
    with pytest.raises(SafetyError, match='profile_invalid'):
        d.assert_send_button()


def test_shifted_button_never_clicked():
    d = desktop_with_template('black')
    d.preflight_send = lambda: None
    d.verify = lambda recipient: None
    d.draft = lambda: 'Synthetic test'
    d.click = lambda *a, **kw: pytest.fail('Clicked a changed button')
    with pytest.raises(SafetyError, match='send_button_changed'):
        d.send('+12025550123', 'Synthetic test')


def test_native_handoff_requires_exact_identity_and_has_no_captured_pipes(tmp_path, monkeypatch):
    import x11_worker
    import subprocess
    launcher = tmp_path / 'viber'; launcher.write_text('#!/bin/sh\n'); launcher.chmod(0o700)
    d = Desktop.__new__(Desktop)
    d.profile = {'viber_launcher': str(launcher)}
    d.guard = lambda **kw: None
    d.identity = lambda: '+12025550123'
    calls = []
    monkeypatch.setattr(x11_worker.subprocess, 'run', lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(x11_worker.time, 'sleep', lambda duration: None)
    assert d.navigate_phone('+12025550123')['recipient_verified'] is True
    assert calls[0][0][0] == [str(launcher), 'viber://chat?number=%2B12025550123']
    assert calls[0][1]['stdout'] == subprocess.DEVNULL
    assert calls[0][1]['stderr'] == subprocess.DEVNULL
    d.identity = lambda: '+12025550999'
    ticks = iter(range(20))
    monkeypatch.setattr(x11_worker.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(SafetyError, match='recipient_changed'):
        d.navigate_phone('+12025550123')
    assert len(calls) == 2  # One URI launch per operation, never auto-relaunch.
