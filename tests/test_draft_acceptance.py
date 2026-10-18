import asyncio
import json
import pytest
from scripts.draft_acceptance import checked_draft


class Session:
    def __init__(self): self.calls = []
    async def call_tool(self, name, args):
        if name == 'health':
            return {'isError': False, 'structuredContent': {'send_enabled': False}}
        self.calls.append((name, args))
        return {'isError': True, 'error': 'ui_command_failed'}


def env(path):
    return {'VIBER_ALLOW_GUI': '1', 'VIBER_ALLOW_INPUT': '1',
            'VIBER_ENABLE_SEND': '0', 'VIBER_DIAGNOSTICS_FILE': str(path)}


def run(session, path, *, recipient='+12025550123', draft='', configuration=None):
    return asyncio.run(checked_draft(session, 'SYNTHETIC', configuration or env(path),
        expected_recipient='+12025550123', recipient_reader=lambda: recipient,
        draft_reader=lambda: draft))


def test_bad_diagnostic_directory_blocks_before_draft_rpc(tmp_path):
    tmp_path.chmod(0o775)
    session = Session()
    with pytest.raises(ValueError, match='diagnostic_preflight_failed'):
        run(session, tmp_path / 'log')
    assert session.calls == []


def test_one_draft_only_after_real_probe_write_and_no_retry(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / 'log'
    session = Session()
    result = run(session, path)
    assert result['isError']
    assert session.calls == [('put_draft', {'text': 'SYNTHETIC', 'expected_recipient': '+12025550123'})]
    assert json.loads(path.read_text())['failure_kind'] == 'probe'
    assert 'SYNTHETIC' not in path.read_text()
    with pytest.raises(ValueError, match='diagnostic_preflight_failed'):
        run(session, path)
    assert len(session.calls) == 1


@pytest.mark.parametrize('key,value', [('VIBER_ENABLE_SEND', '1'), ('VIBER_ALLOW_INPUT', '0'),
                                      ('VIBER_ALLOW_GUI', '0')])
def test_wrong_environment_never_calls_tool(tmp_path, key, value):
    configuration = env(tmp_path / 'log'); configuration[key] = value
    session = Session()
    with pytest.raises(ValueError, match='draft_only_environment_required'):
        run(session, tmp_path / 'log', configuration=configuration)
    assert session.calls == [] and not (tmp_path / 'log').exists()


@pytest.mark.parametrize('recipient,draft,error', [
    ('+12025550199', '', 'acceptance_recipient_mismatch'),
    ('+12025550123', 'Existing draft', 'acceptance_draft_not_empty'),
])
def test_current_identity_and_empty_draft_required_before_rpc(tmp_path, recipient, draft, error):
    tmp_path.chmod(0o700)
    session = Session()
    with pytest.raises(ValueError, match=error):
        run(session, tmp_path / 'log', recipient=recipient, draft=draft)
    assert session.calls == []


@pytest.mark.parametrize('result_recipient,actual_draft,valid', [
    ('+12025550123', 'SYNTHETIC', True),
    ('+12025550199', 'SYNTHETIC', False),
    ('+12025550123', 'different', False),
])
def test_success_requires_exact_result_and_native_readback(tmp_path, result_recipient, actual_draft, valid):
    tmp_path.chmod(0o700)
    class Success(Session):
        async def call_tool(self, name, args):
            if name == 'health':
                return await super().call_tool(name, args)
            self.calls.append((name, args))
            return {'isError': False, 'structuredContent': {'drafted': True,
                    'verified': True, 'recipient': result_recipient}}
    session = Success()
    values = iter(['', actual_draft])
    operation = checked_draft(session, 'SYNTHETIC', env(tmp_path / 'log'),
        expected_recipient='+12025550123', recipient_reader=lambda: '+12025550123',
        draft_reader=lambda: next(values))
    if valid:
        assert asyncio.run(operation)['isError'] is False
    else:
        with pytest.raises(ValueError, match='draft_result_unverified_no_retry'):
            asyncio.run(operation)
    assert len(session.calls) == 1


@pytest.mark.parametrize('payload', [{'send_enabled': True}, {}, {'send_enabled': 0}])
def test_actual_session_health_must_confirm_send_disabled(tmp_path, payload):
    tmp_path.chmod(0o700)
    class WrongHealth(Session):
        async def call_tool(self, name, args):
            if name == 'health': return {'isError': False, 'structuredContent': payload}
            return await super().call_tool(name, args)
    session = WrongHealth()
    with pytest.raises(ValueError, match='actual_session_send_disabled_required'):
        run(session, tmp_path / 'log')
    assert session.calls == []


def test_rpc_timeout_never_retries_or_reads_after_uncertain_write(tmp_path):
    tmp_path.chmod(0o700)
    class Hangs(Session):
        async def call_tool(self, name, args):
            if name == 'health': return await super().call_tool(name, args)
            self.calls.append((name, args))
            await asyncio.Event().wait()
    session = Hangs()
    reads = []
    def draft(): reads.append(True); return ''
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(checked_draft(session, 'SYNTHETIC', env(tmp_path / 'log'),
            expected_recipient='+12025550123', recipient_reader=lambda: '+12025550123',
            draft_reader=draft, timeout=.02))
    assert len(session.calls) == 1 and len(reads) == 1
