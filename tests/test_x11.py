import os
import pytest
from linux_backend import SafetyError, X11Backend, configured_backend
from linux_domain import Service
from x11_worker import Desktop, observed_phone, parse_tsv, dispatch, normalized
from tests.test_domain import Fake


def line(text, confidence=95):
    return {'text': text, 'confidence': confidence, 'box': [0, 0, 30, 10]}


def test_exact_phone_no_country_guess():
    assert observed_phone([line('+380 (98) 190-19-91')]) == '+380981901991'
    assert observed_phone([line('0981901991')]) == '0981901991'
    assert observed_phone([line('0981901991')]) != '+380981901991'
    for lines in ([line('Юрій')], [line('+380981901991', 84)],
                  [line('+380981901991'), line('+380111111111')],
                  [line('Type a message')], [line('Call +380981901991')]):
        with pytest.raises(SafetyError, match='identity_not_visible'):
            observed_phone(lines)


def test_tsv_unicode_and_quoted_text():
    tsv = ('level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
           '5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t96.0\t"Привіт\n'
           '5\t1\t1\t1\t1\t2\t42\t20\t20\t10\t90.0\tсвіте"\n')
    assert parse_tsv(tsv, 2) == [{'text': '"Привіт світе"', 'confidence': 90.0,
                                 'box': [5., 10., 26., 5.]}]
    assert normalized('  Привіт\nсвіте 👋 ') == 'привіт світе 👋'


def test_absolute_client_geometry_ignores_frame_offset(monkeypatch):
    import x11_worker
    monkeypatch.setattr(x11_worker, 'command', lambda *a, **kw: b'''
  Absolute upper-left X: 459
  Absolute upper-left Y: 94
  Relative upper-left X: 5
  Relative upper-left Y: 29
  Width: 950
  Height: 780
''')
    assert x11_worker.window_geometry('123') == (459, 94, 950, 780)


def test_clipboard_rejects_rich_data_without_mutation(monkeypatch):
    import x11_worker
    d = Desktop.__new__(Desktop)
    d.guard = lambda **kw: None
    monkeypatch.setattr(x11_worker, 'command', lambda *a, **kw: b'TARGETS\nUTF8_STRING\ntext/html')
    d.clipboard_set = lambda *a: pytest.fail('mutated rich clipboard')
    with pytest.raises(SafetyError, match='clipboard_unsupported'):
        with d.clipboard():
            pytest.fail('allowed unsupported clipboard')


def test_clipboard_restored_on_error(monkeypatch):
    import x11_worker
    d = Desktop.__new__(Desktop)
    d.guard = lambda **kw: None
    monkeypatch.setattr(x11_worker, 'command', lambda *a, **kw: b'TARGETS\nUTF8_STRING')
    d.clipboard_get = lambda: 'попередній текст'.encode()
    restored = []
    d.clipboard_set = restored.append
    with pytest.raises(SafetyError):
        with d.clipboard():
            raise SafetyError('cancelled')
    assert restored == ['попередній текст'.encode()]


def test_rect_and_geometry_validation():
    d = Desktop.__new__(Desktop)
    d.geometry = (50, 60, 950, 780)
    for value in ([0, 0, 951, 10], [0, 770, 10, 20], [-1, 0, 10, 10],
                  [0, 0, 1.5, 4], [0, 0, 0, 1], None):
        d.profile = {'regions': {'conversation': value}}
        with pytest.raises(SafetyError):
            d.rect('conversation')
    d.state = lambda: (51, 60, 950, 780)
    with pytest.raises(SafetyError, match='geometry'):
        d.guard()


def test_offline_never_clicks_send(monkeypatch):
    monkeypatch.setenv('VIBER_ENABLE_SEND', '1')
    d = Desktop.__new__(Desktop)
    d.profile = {'send_calibrated': True}
    d.ocr = lambda region: [line('No internet connection')]
    d.click = lambda *a: pytest.fail('clicked send offline')
    with pytest.raises(SafetyError, match='offline'):
        d.send('+380981901991', 'Привіт')


def test_changed_recipient_never_pastes():
    d = Desktop.__new__(Desktop)
    d.identity = lambda: '+380111111111'
    d.click = lambda *a: pytest.fail('clicked on wrong recipient')
    with pytest.raises(SafetyError, match='recipient_changed'):
        d.write('test', '+380981901991')


def test_backend_selection_explicit(monkeypatch):
    monkeypatch.setenv('VIBER_BACKEND', 'x11')
    assert isinstance(configured_backend(), X11Backend)
    monkeypatch.setenv('VIBER_BACKEND', 'typo')
    with pytest.raises(SafetyError):
        configured_backend()


def test_ocr_never_invents_stable_id():
    assert dispatch(None, {'action': 'messages'}) == []
    assert X11Backend.stable_message_ids is False


def test_read_visible_no_identity_claim(tmp_path):
    backend = Fake()
    backend.read = lambda region: {'text': 'синтетичний текст', 'region': region}
    service = Service(backend, tmp_path / 'state')
    result = service.read_visible()
    assert result['recipient_verified'] is False
    assert result['send_authorized'] is False
    with pytest.raises(SafetyError):
        service.read_visible('full_screen')


def test_ocr_send_unknown_and_same_token_never_repeats(tmp_path):
    from tests.test_domain import NUMBER, TEXT
    backend = Fake()
    backend.stable_message_ids = False
    service = Service(backend, tmp_path / 'state', send_enabled=True)
    token = service.store().approve(NUMBER, TEXT)
    first = service.reply(TEXT, token, NUMBER)
    assert first['status'] == 'unknown'
    assert first['reason'] == 'no_stable_message_ids'
    assert first['sent'] is None and first['delivered'] is None
    second = service.reply(TEXT, token, NUMBER)
    assert second['replayed'] is True
    assert backend.sends == 1
