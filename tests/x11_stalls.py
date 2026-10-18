"""Compare local selection silence and X-server stalls on a fresh Xvfb only."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def expect_failure(call, reason):
    from linux_backend import SafetyError
    try:
        call()
    except SafetyError as error:
        assert str(error) == reason, str(error)
    else:
        raise AssertionError('Expected bounded failure')


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
                          NO_AT_BRIDGE='1', GTK_MODULES='', GDK_BACKEND='x11',
                          VIBER_ALLOW_GUI='1', XDG_SESSION_TYPE='x11')
        os.environ.pop('DBUS_SESSION_BUS_ADDRESS', None)
        os.environ.pop('XAUTHORITY', None)
        from tests.clipboard_x11 import fixture
        from x11_worker import Desktop, command
        from linux_diagnostics import phase
        for mode in ('silent', 'grab_init', 'grab_convert'):
            with tempfile.TemporaryDirectory(prefix='viber-stall-') as temporary:
                log = Path(temporary) / 'diagnostic.jsonl'
                os.environ['VIBER_DIAGNOSTICS_FILE'] = str(log)
                with fixture(mode):
                    with phase('identity_copy'):
                        expect_failure(Desktop.clipboard_get, 'clipboard_failed')
                    events = [json.loads(line) for line in log.read_text().splitlines()]
                    checkpoints = [e['command_kind'] for e in events if e['failure_kind'] == 'checkpoint']
                    expected = ['clipboard_init_start']
                    if mode != 'grab_init':
                        expected += ['clipboard_init_ready', 'clipboard_convert_start']
                    assert checkpoints == expected, (mode, checkpoints)
                    assert all(e['phase'] == 'identity_copy' for e in events), events
                    assert events[-1]['failure_kind'] == 'timeout'
                    assert events[-1]['timeout_seconds'] == 3
                    if mode == 'silent':
                        # Selection silence alone does not block new X connections or ownership.
                        command(['xwininfo', '-root'])
                        Desktop.clipboard_set(b'SYNTHETIC restore')
                        assert Desktop.clipboard_get() == b'SYNTHETIC restore'
                        observed = {'new_x_connection': 'responsive', 'writer': 'success'}
                    else:
                        with phase('clipboard_restore'):
                            expect_failure(lambda: Desktop.clipboard_set(b'SYNTHETIC restore'), 'clipboard_failed')
                        with phase('identity'):
                            expect_failure(lambda: command(['xdotool', 'getactivewindow']), 'ui_command_failed')
                        with phase('setup'):
                            expect_failure(lambda: Desktop({}), 'ui_command_failed')
                        failures = [json.loads(line) for line in log.read_text().splitlines()
                                    if json.loads(line)['failure_kind'] == 'timeout']
                        assert [(e['command_kind'], e['timeout_seconds']) for e in failures] == [
                            ('clipboard', 3), ('clipboard', 2), ('window_focus', 3), ('window_search', 3)]
                        observed = {'new_x_connection': 'stalled', 'writer': 'timeout',
                                    'focus': 'timeout', 'search': 'ui_command_failed'}
                # Killing only the fixture owner releases its grab. No live DISPLAY involved.
                command(['xwininfo', '-root'])
                expect_failure(lambda: Desktop({}), 'window_missing_or_ambiguous')
                print(json.dumps({'mode': mode, 'checkpoints': checkpoints, **observed,
                                  'released_after_owner_exit': True, 'live_viber': False}), flush=True)
    finally:
        xvfb.terminate(); xvfb.wait(timeout=3)


if __name__ == '__main__':
    main()
