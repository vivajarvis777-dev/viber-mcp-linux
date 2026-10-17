"""Synthetic asynchronous render/cancellation tests, never Viber E2E."""
import json
import threading
import pytest
from linux_domain import Service, SafetyError
from linux_backend import LinuxBackend
from linux_errors import reason_code
from tests.test_domain import Fake, NUMBER, TEXT


class Delayed(Fake):
    def __init__(self, effect='appear'):
        super().__init__()
        self.effect = effect
        self.samples = 0
        self.observed = threading.Event()
    def send(self, recipient, text):
        self.sends += 1  # asynchronous fixture: nothing changes yet
    def messages(self):
        if self.sends:
            self.samples += 1
            self.observed.set()
            if self.samples == 3:
                if self.effect == 'appear':
                    self.rows.append({'id': 'new', 'text': TEXT, 'outgoing': True})
                    self.value = ''
                elif self.effect == 'identity':
                    self.recipient = '0981901992'  # fake only
                elif self.effect == 'draft':
                    self.value = 'PRIVATE unrelated draft'
        return super().messages()


def make(tmp_path, effect='appear', **kw):
    b = Delayed(effect)
    s = Service(b, tmp_path/'state', send_enabled=True,
                verification_timeout=kw.get('timeout', .15),
                poll_interval=kw.get('interval', .005))
    return s, b, s.store().approve(NUMBER, TEXT)


def test_delayed_bubble(tmp_path):
    s, b, token = make(tmp_path)
    r = s.send_message(NUMBER, TEXT, approval_token=token)
    assert r['status'] == 'sent' and b.samples == 3 and b.sends == 1


@pytest.mark.parametrize(('effect', 'reason'), [
    ('never', 'verification_timeout'), ('identity', 'recipient_changed'),
    ('draft', 'draft_changed'),
])
def test_unknown_no_resend(tmp_path, effect, reason):
    s, b, token = make(tmp_path, effect)
    r = s.send_message(NUMBER, TEXT, approval_token=token)
    assert r['status'] == 'unknown' and r['reason'] == reason
    assert r['sent'] is None and 'PRIVATE' not in json.dumps(r)
    again = s.send_message(NUMBER, TEXT, approval_token=token)
    assert again == {**r, 'replayed': True} and b.sends == 1


def test_cancel_wakes_wait_and_persists_unknown(tmp_path):
    s, b, token = make(tmp_path, 'never', timeout=5, interval=1)
    results = []
    thread = threading.Thread(target=lambda: results.append(
        s.send_message(NUMBER, TEXT, approval_token=token)))
    thread.start()
    try:
        assert b.observed.wait(1)
        s.stop()
        thread.join(.5)
        assert not thread.is_alive()
    finally:
        s.stop()
        thread.join(2)
    assert results[0]['reason'] == 'cancelled'
    assert results[0]['status'] == 'unknown' and b.sends == 1
    assert s.send_message(NUMBER, TEXT, approval_token=token)['replayed']
    assert b.sends == 1


def test_new_token_can_resend_same_text(tmp_path):
    b = Fake()
    s = Service(b, tmp_path/'state', send_enabled=True)
    for _ in range(2):
        token = s.store().approve(NUMBER, TEXT)
        assert s.send_message(NUMBER, TEXT, approval_token=token)['sent']
    assert b.sends == 2  # token replay protection != business-event idempotency


@pytest.mark.parametrize('message,code', [
    ('editable text unsupported', 'editable_text_unsupported'),
    ('text interface required', 'text_interface_missing'),
    ('missing or ambiguous accessible element', 'selector_missing_or_ambiguous'),
    ('PRIVATE UI text', 'operation_failed'),
])
def test_closed_reason_vocabulary(message, code):
    assert reason_code(RuntimeError(message)) == code


@pytest.mark.parametrize('payload,code', [
    ('PRIVATE UI invalid JSON', 'AT-SPI operation failed; no retry'),
    ('[]', 'AT-SPI operation failed; no retry'),
    ('{"error":"PRIVATE UI exception"}', 'operation_failed'),
    ('{"error":["PRIVATE"]}', 'operation_failed'),
    ('{"error":"editable_text_unsupported"}', 'editable_text_unsupported'),
])
def test_worker_diagnostics_sanitized(monkeypatch, payload, code):
    import subprocess
    class Process:
        returncode = 0
        def communicate(self, *a, **k): return payload, None
    monkeypatch.setenv('VIBER_ALLOW_GUI', '1')
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: Process())
    with pytest.raises(SafetyError) as exc:
        LinuxBackend('synthetic.json').identity()
    assert str(exc.value) == code


def test_blocked_reason_persisted_without_private_text(tmp_path):
    b = Fake()
    def fail(): raise SafetyError('editable_text_unsupported')
    b.draft = fail
    s = Service(b, tmp_path/'state', send_enabled=True)
    token = s.store().approve(NUMBER, TEXT)
    r = s.send_message(NUMBER, TEXT, approval_token=token)
    assert r['status'] == 'blocked' and not r['attempted']
    assert r['reason'] == 'editable_text_unsupported' and b.sends == 0
