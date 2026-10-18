"""Install per-user desktop and application-menu entries; never start Viber."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def render(app_run):
    path = Path(app_run).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('AppRun must be an existing executable')
    value = str(path)
    if any(c in value for c in ('\n', '\r', '\x00', '\t')):
        raise ValueError('Invalid executable path')
    if any(c in value for c in ('\\', '"', '`', '$', '%')):
        raise ValueError('Unsupported Desktop Entry metacharacter in path')
    icon = path.parent / 'viber.png'
    if not icon.is_file():
        raise ValueError('Bundled viber.png icon is missing')
    template = Path(__file__).with_name('desktop').joinpath('Viber.desktop.in').read_text()
    return (template.replace('@APP_RUN@', '"' + value + '"')
            .replace('@APP_DIR@', str(path.parent))
            .replace('@ICON@', str(icon)))


def install(app_run, destination, replace=False):
    content = render(app_run)
    destination = Path(destination).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Refusing launcher symlink')
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    flags |= os.O_TRUNC if replace else os.O_EXCL
    fd = os.open(destination, flags, 0o755)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
        os.fchmod(stream.fileno(), 0o755)
    return destination


def desktop_directory():
    result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True,
                            text=True, check=True, timeout=5)
    path = Path(result.stdout.strip())
    if not path.is_absolute() or path == Path.home():
        raise ValueError('Desktop directory unavailable or disabled')
    return path


def install_desktop_integration(app_run, replace=False):
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    if not data.is_absolute():
        raise ValueError('XDG_DATA_HOME must be absolute')
    targets = [data / 'applications/Viber.desktop', desktop_directory() / 'Viber.desktop']
    # Preflight both entries before writing either one.
    render(app_run)
    for target in targets:
        if target.is_symlink():
            raise ValueError('Refusing launcher symlink')
        if target.exists() and not replace:
            raise FileExistsError(target)
    return [install(app_run, target, replace=replace) for target in targets]


def refresh(entries):
    for entry in entries:
        # XFCE uses the executable bit; GVfs trust also covers other file managers.
        if shutil.which('gio'):
            result = subprocess.run(['gio', 'set', str(entry), 'metadata::trusted', 'true'],
                                    capture_output=True, timeout=5)
            if result.returncode:
                print(f'Warning: GVfs trust unavailable for {entry}; executable bit is set')
    if shutil.which('update-desktop-database'):
        for directory in {p.parent for p in entries if p.parent.name == 'applications'}:
            subprocess.run(['update-desktop-database', str(directory)], check=True, timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-run', default='~/.local/opt/viber/squashfs-root/AppRun')
    parser.add_argument('--output', help='Only install this entry instead of both XDG locations')
    parser.add_argument('--replace', action='store_true', help='Explicitly replace existing launcher files')
    args = parser.parse_args()
    entries = ([install(args.app_run, args.output, replace=args.replace)] if args.output
               else install_desktop_integration(args.app_run, replace=args.replace))
    refresh(entries)
    for entry in entries:
        print(entry)
