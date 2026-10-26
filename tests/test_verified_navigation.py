import contextlib
from unittest.mock import MagicMock
import asyncio
import pytest
import recipient_identity as identity

PHONE = '+12025550123'


def setup(monkeypatch, results):
    auto = MagicMock()
    auto.current_phone = PHONE
    verify = MagicMock(side_effect=results)
    monkeypatch.setattr(identity, 'verify_current_recipient', verify)
    return auto, verify


def mismatch():
    return RuntimeError('recipient_identity_mismatch')


def test_native_match_survives_stale_pixel_reference(monkeypatch):
    auto, verify = setup(monkeypatch, [True])
    auto.verify_header_contact.return_value = False
    assert identity.open_verified_recipient(auto, PHONE)
    auto.verify_header_contact.assert_not_called()
    auto.navigate_via_ui_search.assert_not_called()
    auto.put_draft.assert_not_called()
    auto.send.assert_not_called()


def test_stale_cache_reopens_and_verifies_correct_number(monkeypatch):
    auto, verify = setup(monkeypatch, [mismatch(), True])
    assert identity.open_verified_recipient(auto, PHONE)
    auto.navigate_via_ui_search.assert_called_once_with(PHONE)
    auto._navigate_via_uri.assert_not_called()
    assert auto.current_phone == PHONE
    assert verify.call_count == 2


def test_wrong_search_result_requires_uri_and_exact_proof(monkeypatch):
    auto, verify = setup(monkeypatch, [mismatch(), mismatch(), True])
    assert identity.open_verified_recipient(auto, PHONE)
    auto._navigate_via_uri.assert_called_once_with(PHONE)
    assert verify.call_count == 3


def test_both_navigation_paths_wrong_fail_closed(monkeypatch):
    auto, verify = setup(monkeypatch, [mismatch(), mismatch(), mismatch()])
    with pytest.raises(RuntimeError, match='recipient_identity_mismatch'):
        identity.open_verified_recipient(auto, PHONE)
    assert auto.current_phone is None
    auto.put_draft.assert_not_called()
    auto.send.assert_not_called()


@pytest.mark.parametrize('reason', [
    'window_not_foreground', 'recipient_identity_composer_changed',
    'recipient_identity_menu_ambiguous', 'clipboard_restore_failed',
    'recipient_identity_unavailable',
])
def test_safety_error_never_retries_navigation(monkeypatch, reason):
    auto, verify = setup(monkeypatch, [RuntimeError(reason)])
    with pytest.raises(RuntimeError, match=reason):
        identity.open_verified_recipient(auto, PHONE)
    auto.navigate_via_ui_search.assert_not_called()
    auto._navigate_via_uri.assert_not_called()


def test_false_verification_never_authorizes(monkeypatch):
    auto, verify = setup(monkeypatch, [False])
    with pytest.raises(RuntimeError, match='unavailable'):
        identity.open_verified_recipient(auto, PHONE)


def test_verified_send_recovers_cache_before_draft_then_rechecks(monkeypatch):
    import viber_mcp_service as service
    auto, verify = setup(monkeypatch, [mismatch(), True, True])
    auto.resolve_phone.return_value = PHONE
    auto.send.return_value = {'sent': True, 'verified': True}
    ledger = MagicMock()
    ledger.is_duplicate.return_value = False
    ledger.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
    @contextlib.asynccontextmanager
    async def mutex():
        yield
    monkeypatch.setattr(service, 'auto', auto)
    monkeypatch.setattr(service, 'get_shared_ledger', lambda: ledger)
    monkeypatch.setattr(service, 'viber_ui_mutex', mutex)
    monkeypatch.setenv('VIBER_ENABLE_SEND', '1')
    result = asyncio.run(service.send_message(PHONE, 'Synthetic', idempotency_key='synthetic', verify_recipient=True))
    assert result['recipient_verified'] is True
    assert verify.call_count == 3
    auto.open_chat_by_number.assert_not_called()
    auto.send.assert_called_once_with('Synthetic')


def test_second_identity_failure_prevents_dispatch(monkeypatch):
    import viber_mcp_service as service
    auto, verify = setup(monkeypatch, [True, mismatch()])
    auto.resolve_phone.return_value = PHONE
    ledger = MagicMock()
    ledger.is_duplicate.return_value = False
    ledger.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
    @contextlib.asynccontextmanager
    async def mutex():
        yield
    monkeypatch.setattr(service, 'auto', auto)
    monkeypatch.setattr(service, 'get_shared_ledger', lambda: ledger)
    monkeypatch.setattr(service, 'viber_ui_mutex', mutex)
    monkeypatch.setenv('VIBER_ENABLE_SEND', '1')
    result = asyncio.run(service.send_message(PHONE, 'Synthetic', idempotency_key='synthetic', verify_recipient=True))
    assert result['ok'] is False
    auto.send.assert_not_called()
