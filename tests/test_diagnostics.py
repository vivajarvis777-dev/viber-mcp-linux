import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

import linux_diagnostics as diagnostics
import x11_worker
from linux_backend import SafetyError


@pytest.mark.parametrize('failure,expected', [
    (subprocess.TimeoutExpired(['PRIVATE'], 3, stderr=b'SECRET'), 'timeout'),
    (subprocess.CalledProcessError(7, ['PRIVATE'], stderr=b'SECRET'), 'exit'),
    (OSError('SECRET'), 'os'),
])
def test_private_diagnostic_identifies_failure_without_arguments(tmp_path, monkeypatch, failure, expected):
    tmp_path.chmod(0o700)
    log = tmp_path / 'diagnostic.jsonl'
    monkeypatch.setenv('VIBER_DIAGNOSTICS_FILE', str(log))
    def failing(*args, **kwargs):
        raise failure
    monkeypatch.setattr(x11_worker.subprocess, 'run', failing)
    with diagnostics.phase('identity'), pytest.raises(SafetyError, match='ui_command_failed'):
        x11_worker.command(['xdotool', 'getwindowpid', 'PRIVATE'], data=b'PRIVATE')
    raw = log.read_text()
    assert 'SECRET' not in raw and 'PRIVATE' not in raw
    event = json.loads(raw)
    assert event['phase'] == 'identity'
    assert event['command_kind'] == 'window_pid'
    assert event['failure_kind'] == expected
    assert log.stat().st_mode & 0o777 == 0o600
    assert set(event) <= {'time_ns', 'phase', 'command_kind', 'failure_kind',
                          'returncode', 'timeout_seconds'}


def test_logging_disabled_unless_explicit_and_rejects_public_or_symlink_paths(tmp_path, monkeypatch):
    monkeypatch.delenv('VIBER_DIAGNOSTICS_FILE', raising=False)
    diagnostics.record('pointer', 'timeout', timeout=3)
    assert not list(tmp_path.iterdir())
    log = tmp_path / 'log'
    monkeypatch.setenv('VIBER_DIAGNOSTICS_FILE', str(log))
    tmp_path.chmod(0o755)
    diagnostics.record('pointer', 'timeout', timeout=3)
    assert not log.exists()
    tmp_path.chmod(0o700)
    target = tmp_path / 'target'; target.write_text('unchanged')
    log.symlink_to(target)
    diagnostics.record('pointer', 'timeout', timeout=3)
    assert target.read_text() == 'unchanged'


def test_fifo_or_missing_parent_never_blocks_diagnostics(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo, 0o600)
    for destination in (fifo, tmp_path / 'missing' / 'log'):
        env = {**os.environ, 'VIBER_DIAGNOSTICS_FILE': str(destination)}
        result = subprocess.run(
            [sys.executable, '-c', "from linux_diagnostics import record; record('pointer', 'os')"],
            env=env, cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=2)
        assert result.returncode == 0


def test_cleanup_error_preserves_first_failure_and_logs_safely(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    log = tmp_path / 'log'
    monkeypatch.setenv('VIBER_DIAGNOSTICS_FILE', str(log))
    original = SafetyError('window_not_foreground')
    def cleanup():
        raise SafetyError('clipboard_failed')
    with pytest.raises(SafetyError) as caught:
        with diagnostics.restore_after(cleanup):
            raise original
    assert caught.value is original
    assert json.loads(log.read_text())['phase'] == 'cleanup'
    # Cleanup failure after a successful body must still block completion.
    with pytest.raises(SafetyError, match='clipboard_failed'):
        with diagnostics.restore_after(cleanup):
            pass


def test_failed_identity_cancel_does_not_hide_original():
    d = x11_worker.Desktop.__new__(x11_worker.Desktop)
    original = SafetyError('clipboard_unsupported')
    def fail_clipboard():
        raise original
    d.clipboard = fail_clipboard
    def fail_escape(key):
        raise SafetyError('ui_command_failed')
    d.key = fail_escape
    with pytest.raises(SafetyError) as caught:
        d.clipboard_identity()
    assert caught.value is original


def test_clipboard_restore_does_not_hide_failed_input(monkeypatch):
    d = x11_worker.Desktop.__new__(x11_worker.Desktop)
    d.guard = lambda **kwargs: None
    d.clipboard_owner = lambda: 1
    monkeypatch.setattr(x11_worker, 'command', lambda *a, **kw: b'TARGETS\nUTF8_STRING')
    d.clipboard_get = lambda: b'original'
    def fail_restore(value):
        raise SafetyError('clipboard_failed')
    d.clipboard_set = fail_restore
    original = SafetyError('window_not_foreground')
    with pytest.raises(SafetyError) as caught:
        with d.clipboard():
            raise original
    assert caught.value is original
