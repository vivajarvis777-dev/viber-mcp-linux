import os
from pathlib import Path
import pytest
import install_launcher as launcher


def app(tmp_path):
    root = tmp_path / 'extracted app'
    root.mkdir()
    run = root / 'AppRun'
    run.write_text('#!/bin/sh\nexit 0\n')
    run.chmod(0o755)
    (root / 'viber.png').write_bytes(b'fixture')
    return run


def test_absolute_icon_and_working_directory(tmp_path):
    run = app(tmp_path)
    text = launcher.render(run)
    assert f'Icon={run.parent}/viber.png\n' in text
    assert f'Path={run.parent}\n' in text
    assert 'DISPLAY=' not in text
    assert 'DBUS_SESSION_BUS_ADDRESS=' not in text


def test_both_xdg_locations_and_explicit_replace(tmp_path, monkeypatch):
    run = app(tmp_path)
    desktop = tmp_path / 'localized desktop'
    data = tmp_path / 'data'
    monkeypatch.setenv('XDG_DATA_HOME', str(data))
    monkeypatch.setattr(launcher, 'desktop_directory', lambda: desktop)
    targets = launcher.install_desktop_integration(run)
    assert targets == [data / 'applications/Viber.desktop', desktop / 'Viber.desktop']
    for target in targets:
        assert target.read_text() == launcher.render(run)
        assert os.access(target, os.X_OK)
    with pytest.raises(FileExistsError):
        launcher.install_desktop_integration(run)
    launcher.install_desktop_integration(run, replace=True)


def test_missing_icon_fails_before_writes(tmp_path):
    run = app(tmp_path)
    (run.parent / 'viber.png').unlink()
    with pytest.raises(ValueError, match='icon'):
        launcher.render(run)


def test_replace_refuses_symlink(tmp_path):
    run = app(tmp_path)
    original = tmp_path / 'user-file'
    original.write_text('preserve')
    target = tmp_path / 'Viber.desktop'
    target.symlink_to(original)
    with pytest.raises(ValueError, match='symlink'):
        launcher.install(run, target, replace=True)
    assert original.read_text() == 'preserve'
