import subprocess
import pytest
import install_launcher as launcher
import x11_probe as probe


def executable(tmp_path, name='App Run'):
    path = tmp_path / name
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o755)
    (tmp_path / 'viber.png').write_bytes(b'fixture')
    return path


def test_launcher_matches_and_validates(tmp_path):
    app = executable(tmp_path)
    dest = launcher.install(app, tmp_path / 'Viber.desktop')
    content = dest.read_text()
    assert f'Exec="{app}"' in content
    assert 'StartupWMClass=Viber' in content
    assert dest.stat().st_mode & 0o111
    subprocess.run(['desktop-file-validate', str(dest)], check=True)
    with pytest.raises(FileExistsError):
        launcher.install(app, dest)


@pytest.mark.parametrize('name', ['evil%f', 'evil$HOME', 'evil"quote', 'evil\nline', 'evil`cmd', 'evil\\slash'])
def test_launcher_refuses_metacharacters(tmp_path, name):
    with pytest.raises(ValueError):
        launcher.render(executable(tmp_path, name))


def test_launcher_requires_executable(tmp_path):
    path = tmp_path / 'absent'
    with pytest.raises(ValueError):
        launcher.render(path)
    path.write_text('not executable')
    with pytest.raises(ValueError):
        launcher.render(path)


@pytest.mark.parametrize('crop', [[0, 0, 950, 780], [294, 170, 330, 50], [294, 0, -1, 50], [900, 0, 100, 50], [True, 0, 100, 50], None])
def test_crop_cannot_read_history(crop):
    with pytest.raises(probe.ProbeError):
        probe.rectangle({'window_size': [950, 780], 'header_rect': crop}, 950, 780)


def test_calibrated_header_and_geometry():
    p = {'window_size': [950, 780], 'header_rect': [294, 10, 326, 73]}
    assert probe.rectangle(p, 950, 780) == p['header_rect']
    with pytest.raises(probe.ProbeError):
        probe.rectangle(p, 951, 780)


class Image:
    width, height = 100, 20
    def resize(self, size):
        return self
    def save(self, stream, format):
        stream.write(b'synthetic image')


@pytest.mark.parametrize('text,match,international', [('2025550123', True, False), ('+12025550123', False, True), ('202 555 0123', False, False), ('2025550123\n2025550123', False, False), ('no phone', False, False)])
def test_ocr_never_authorizes_or_normalizes(monkeypatch, text, match, international):
    monkeypatch.setattr(probe, 'command', lambda *a, **k: text.encode())
    result = probe.phone_summary(Image(), '2025550123')
    assert result['literal_match_observed'] is match
    assert result['international_form_observed'] is international
    assert result['recipient_verified'] is False
    assert result['send_authorized'] is False
    assert text not in str(result)


def test_disabled_and_missing_bus(monkeypatch):
    monkeypatch.delenv('VIBER_ALLOW_GUI', raising=False)
    with pytest.raises(probe.ProbeError, match='gui_disabled'):
        probe.snapshot({})
    assert not probe.accessibility_socket('unix:path=/nonexistent-viber-probe-socket')
    assert not probe.accessibility_socket('tcp:host=localhost')


def test_invalid_literal():
    with pytest.raises(probe.ProbeError, match='invalid_literal'):
        probe.phone_summary(Image(), '2025550123 ')


def test_command_failure_sanitized():
    with pytest.raises(probe.ProbeError, match='^probe_command_failed$'):
        probe.command(['/nonexistent-viber-private-command'])
