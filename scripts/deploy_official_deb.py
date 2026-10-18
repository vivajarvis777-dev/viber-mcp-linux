"""User-scoped install from an already verified official Viber .deb.

No root, apt scripts, profile reset, download, autostart or message send.
Run only after the operator explicitly approves replacing this user's Viber.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import time


def deploy(deb, expected_sha256, backup, resume_staging=False, native_debs=()):
    home = Path.home()
    if os.getuid() == 0:
        raise RuntimeError('Run as the desktop user, not root')
    deb = Path(deb).resolve()
    backup = Path(backup).resolve()
    if home not in backup.parents:
        raise RuntimeError('Use a new private backup directory inside your home')
    if backup.exists() and not (resume_staging and backup.stat().st_uid == os.getuid()
                               and not backup.stat().st_mode & 0o077
                               and {p.name for p in backup.iterdir()} == {'package'}):
        raise RuntimeError('Backup exists; only an untouched package-only staging may be resumed')
    if hashlib.file_digest(deb.open('rb'), 'sha256').hexdigest() != expected_sha256:
        raise RuntimeError('Package checksum mismatch')
    fields = subprocess.check_output(['dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture'], text=True)
    values = dict(line.split(': ', 1) for line in fields.splitlines())
    if values['Package'] != 'viber' or values['Architecture'] != 'amd64':
        raise RuntimeError('Expected the official viber amd64 package')
    version = values['Version']
    if not all(c.isdigit() or c == '.' for c in version):
        raise RuntimeError('Unexpected version')
    prefix = home / '.local/opt' / ('viber-deb-' + version)
    if prefix.exists():
        raise RuntimeError('Target exists; inspect before retrying')
    allowed = {'libxcb-cursor0', 'libxcb-image0', 'libxcb-render-util0', 'libxcb-icccm4',
               'libxcb-keysyms1', 'libxcb-xkb1', 'libxkbcommon-x11-0', 'libxcb-util1'}
    for dependency in native_debs:
        name = subprocess.check_output(['dpkg-deb', '-f', dependency, 'Package'], text=True).strip()
        if name not in allowed:
            raise RuntimeError('Unexpected desktop dependency')
    backup.mkdir(mode=0o700, parents=True, exist_ok=resume_staging)
    extraction = backup / 'package'
    subprocess.run(['dpkg-deb', '-x', str(deb), str(extraction)], check=True)
    executable = extraction / 'opt/viber/Viber'
    if not executable.is_file():
        raise RuntimeError('Package layout differs')
    # Only signal this user's Viber processes. Never pgrep/kill other users.
    pids = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'Viber'], capture_output=True, text=True)
    for value in pids.stdout.split():
        pid = int(value)
        proc = Path('/proc') / value
        if proc.stat().st_uid != os.getuid() or (proc / 'comm').read_text().strip() != 'Viber':
            raise RuntimeError('Process ownership changed')
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
    while any((Path('/proc') / value).exists() for value in pids.stdout.split()):
        if time.monotonic() > deadline:
            raise RuntimeError('Viber did not exit; no forced kill or profile copy')
        time.sleep(.1)
    profile = home / '.ViberPC'
    if profile.is_dir():
        target = backup / 'profile.tar'
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream, tarfile.open(fileobj=stream, mode='w') as tar:
            tar.add(profile, arcname='.ViberPC')
    desktop = Path(subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip())
    if not desktop.is_absolute() or desktop == home:
        raise RuntimeError('Desktop path unavailable')
    targets = [home / '.local/share/applications/Viber.desktop', desktop / 'Viber.desktop']
    for index, target in enumerate(targets):
        if target.is_symlink():
            raise RuntimeError('Refusing launcher symlink')
        if target.exists():
            shutil.copy2(target, backup / f'launcher-{index}.desktop')
    shutil.move(str(extraction / 'opt/viber'), prefix)
    for dependency in native_debs:
        subprocess.run(['dpkg-deb', '-x', dependency, str(prefix / 'deps')], check=True)
    shutil.copy2(extraction / 'usr/share/pixmaps/viber.png', prefix / 'viber.png')
    launcher = prefix / 'launch-viber'
    launcher.write_text('#!/bin/sh\nset -eu\n'
                        'viber_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
                        'export LD_LIBRARY_PATH="$viber_dir/deps/usr/lib/x86_64-linux-gnu:$viber_dir/lib"\n'
                        'export QT_PLUGIN_PATH="$viber_dir/plugins"\n'
                        'exec "$viber_dir/Viber" "$@"\n')
    launcher.chmod(0o755)
    content = ('[Desktop Entry]\nType=Application\nName=Viber\n'
               f'Exec="{launcher}" %u\nIcon={prefix}/viber.png\n'
               f'Path={prefix}\nTerminal=false\nCategories=Network;InstantMessaging;\n'
               'MimeType=x-scheme-handler/viber;\nStartupWMClass=Viber\n')
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        target.chmod(0o755)
    old = home / '.local/opt/viber'
    if old.exists():
        shutil.move(str(old), backup / 'previous-appimage')
    subprocess.run(['update-desktop-database', str(targets[0].parent)], check=True)
    result = {'version': version, 'sha256': expected_sha256, 'prefix': str(prefix),
              'backup': str(backup), 'profile_preserved': profile.is_dir(),
              'package_manager_registered': False, 'started': False}
    (backup / 'deployment.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deb', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--resume-staging', action='store_true')
    parser.add_argument('--native-debs', nargs='*', default=[])
    args = parser.parse_args()
    deploy(args.deb, args.sha256, args.backup, args.resume_staging, args.native_debs)
