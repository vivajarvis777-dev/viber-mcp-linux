from types import SimpleNamespace
import pytest
from clipboard_reader import selection_bytes, MAX_BYTES
from linux_backend import SafetyError
from x11_worker import Desktop


def selection(data=b'', datatype='UTF8_STRING', format=8, length=None):
    return SimpleNamespace(get_length=lambda: len(data) if length is None else length,
        get_format=lambda: format, get_data_type=lambda: SimpleNamespace(name=lambda: datatype),
        get_data=lambda: data)


@pytest.mark.parametrize('data', [b'', 'Привіт 👋\nТочний текст'.encode()])
def test_exact_utf8_and_valid_empty(data):
    assert selection_bytes(selection(data)) == data


@pytest.mark.parametrize('value', [None, selection(b'', length=-1),
    selection(b'ASCII fallback', datatype='STRING'), selection(b'\xff'),
    selection(b'abc', length=2), selection(b'', format=32),
    selection(b'', length=MAX_BYTES + 1)])
def test_refusal_fallback_invalid_or_oversized_selection_rejected(value):
    with pytest.raises(ValueError): selection_bytes(value)


def test_failed_snapshot_never_inputs_or_changes_selection(monkeypatch):
    import x11_worker
    d = Desktop.__new__(Desktop)
    d.guard = lambda **kw: None
    d.clipboard_owner = lambda: 1
    monkeypatch.setattr(x11_worker, 'command', lambda *a, **kw: b'TARGETS\nUTF8_STRING')
    original = SafetyError('clipboard_failed')
    def fail(): raise original
    d.clipboard_get = fail
    effects = []
    d.key = lambda *a: effects.append('key')
    d.click = lambda *a, **kw: effects.append('click')
    d.clipboard_set = lambda *a: effects.append('set')
    d.clipboard_clear = lambda: effects.append('clear')
    with pytest.raises(SafetyError) as caught: d.clipboard_identity()
    assert caught.value is original and effects == []


def test_owner_switch_during_snapshot_never_overwrites_new_selection(monkeypatch):
    import x11_worker
    d = Desktop.__new__(Desktop)
    d.guard = lambda **kw: None
    owners = iter([1, 2]); d.clipboard_owner = lambda: next(owners)
    monkeypatch.setattr(x11_worker, 'command', lambda *a, **kw: b'TARGETS\nUTF8_STRING')
    d.clipboard_get = lambda: b'SYNTHETIC old clipboard'
    d.clipboard_set = lambda *a: pytest.fail('Overwrote changed owner')
    d.key = lambda *a: pytest.fail('Sent input after failed snapshot')
    with pytest.raises(SafetyError, match='clipboard_changed'):
        d.clipboard_identity()
