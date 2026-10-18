"""Opt-in private diagnostics: fixed categories only, never UI text or argv."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import stat
import time

_phase = ContextVar('viber_ui_phase', default='setup')
PHASES = {'setup', 'identity', 'draft', 'write', 'navigate', 'send', 'read',
          'preflight_send', 'messages', 'cleanup', 'worker'}
COMMANDS = {'window_search', 'window_focus', 'window_pid', 'window_geometry',
            'pointer', 'keyboard', 'clipboard', 'native_text', 'other', 'worker'}
FAILURES = {'timeout', 'exit', 'os', 'cleanup', 'worker_exit'}


@contextmanager
def phase(name):
    token = _phase.set(name if name in PHASES else 'setup')
    try:
        yield
    finally:
        _phase.reset(token)


def record(command_kind, failure_kind, *, returncode=None, timeout=None):
    """Logging must neither expose arbitrary values nor change the UI outcome."""
    destination = os.getenv('VIBER_DIAGNOSTICS_FILE')
    if not destination or command_kind not in COMMANDS or failure_kind not in FAILURES:
        return
    fd = None
    try:
        path = Path(destination)
        parent = path.parent.stat()
        if (not path.is_absolute() or parent.st_uid != os.getuid()
                or parent.st_mode & 0o077):
            return
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
                     | os.O_NONBLOCK, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            return
        # Bound this optional diagnostic file; never rotate/delete user files.
        if info.st_size >= 65536:
            return
        event = {'time_ns': time.time_ns(), 'phase': _phase.get(),
                 'command_kind': command_kind, 'failure_kind': failure_kind}
        if type(returncode) is int:
            event['returncode'] = returncode
        if type(timeout) in (int, float) and 0 < timeout <= 60:
            event['timeout_seconds'] = timeout
        os.write(fd, (json.dumps(event) + '\n').encode())
    except OSError:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


@contextmanager
def restore_after(cleanup):
    """Always attempt cleanup, but preserve the initial operation's exception."""
    try:
        yield
    except BaseException:
        try:
            cleanup()
        except Exception:
            with phase('cleanup'):
                record('other', 'cleanup')
        raise
    else:
        cleanup()
