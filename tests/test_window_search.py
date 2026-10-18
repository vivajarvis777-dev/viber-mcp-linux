import subprocess
import pytest
import x11_worker
from linux_backend import SafetyError


@pytest.mark.parametrize('failure,reason', [
    (OSError('synthetic executable unavailable'), 'ui_command_failed'),
    (subprocess.TimeoutExpired('synthetic', 3), 'ui_command_failed'),
    (subprocess.CalledProcessError(1, 'synthetic', output=b'', stderr=b'Cannot open display'), 'ui_command_failed'),
    (subprocess.CalledProcessError(2, 'synthetic', output=b'', stderr=b''), 'ui_command_failed'),
    (subprocess.CalledProcessError(1, 'synthetic', output=b'', stderr=b''), 'window_missing_or_ambiguous'),
])
def test_search_failure_is_not_evidence_of_missing_window(monkeypatch, failure, reason):
    monkeypatch.setenv('VIBER_ALLOW_GUI', '1')
    monkeypatch.setenv('DISPLAY', ':synthetic')
    monkeypatch.setenv('XDG_SESSION_TYPE', 'x11')
    def fail(*args, **kwargs): raise failure
    monkeypatch.setattr(x11_worker.subprocess, 'run', fail)
    with pytest.raises(SafetyError) as caught:
        x11_worker.Desktop({})
    assert str(caught.value) == reason


def test_no_match_exception_never_applies_to_input_commands(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'synthetic', output=b'', stderr=b'')
    monkeypatch.setattr(x11_worker.subprocess, 'run', fail)
    with pytest.raises(SafetyError, match='ui_command_failed'):
        x11_worker.command(['xdotool', 'key', 'Escape'], allow_no_match=True)
