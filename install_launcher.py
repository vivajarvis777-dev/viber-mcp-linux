"""Render a portable per-user launcher. Does not launch Viber or mark it trusted."""
import argparse
import os
from pathlib import Path


def render(app_run):
    path = Path(app_run).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('AppRun must be an existing executable')
    # Desktop Entry Exec quoting has its own rules, not shell quoting.
    value = str(path)
    if any(c in value for c in ('\n', '\r', '\x00')):
        raise ValueError('Invalid executable path')
    if any(c in value for c in ('\\', '"', '`', '$', '%')):
        raise ValueError('Unsupported Desktop Entry metacharacter in path')
    template = Path(__file__).with_name('desktop').joinpath('Viber.desktop.in').read_text()
    return template.replace('@APP_RUN@', '"' + value + '"')


def install(app_run, destination):
    content = render(app_run)
    destination = Path(destination).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite the user's existing launcher/destination.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-run', default='~/.local/opt/viber/squashfs-root/AppRun')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(install(args.app_run, args.output))
