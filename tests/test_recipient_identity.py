import contextlib
from unittest.mock import MagicMock
import pytest
import recipient_identity as identity


@pytest.mark.parametrize('observed,expected,result', [
 ('+380 (50) 111-22-33','+380501112233',True),
 ('380501112233','+380501112233',True),
 ('0501112233','+380501112233',False),
 ('+380501112234','+380501112233',False),
 ('User +380501112233','+380501112233',False),
 ('','+380501112233',False),
])
def test_exact_whole_phone_required(observed, expected, result):
    assert identity.same_phone(observed,expected) is result


def fixture(monkeypatch, copied):
    desktop=MagicMock()
    clipboard={'value':b'operator draft clipboard', 'saved':None}
    @contextlib.contextmanager
    def preserve():
        clipboard['saved']=clipboard['value']
        try:yield
        finally:clipboard['value']=clipboard['saved']
    desktop.clipboard.side_effect=preserve
    desktop.clipboard_set.side_effect=lambda v:clipboard.update(value=v)
    desktop.clipboard_get.side_effect=lambda:clipboard['value']
    monkeypatch.setattr(identity,'Desktop',lambda p:desktop)
    obj=MagicMock();obj.GetRoleName.return_value='menu item';obj.Get.return_value='Copy number'
    obj.DoAction.side_effect=lambda *a,**k:(clipboard.update(value=copied) or True)
    auto=MagicMock();auto.get_window_geometry.return_value=(0,0,950,780)
    auto._walk_accessible.return_value=[(obj,'menu')];auto._obj_extents.return_value=(400,100,100,30)
    return auto,desktop,clipboard


def test_native_copy_restores_clipboard_without_composer_input(monkeypatch):
    auto,desktop,clipboard=fixture(monkeypatch,b'+380501112233')
    assert identity.verify_current_recipient(auto,'+380501112233')
    assert clipboard['value']==b'operator draft clipboard'
    desktop.key.assert_called_once_with('Escape')
    desktop.click.assert_called_once_with([430,65],button=3)
    auto.put_draft.assert_not_called();auto.send.assert_not_called()


def test_wrong_recipient_restores_clipboard_and_fails_closed(monkeypatch):
    auto,desktop,clipboard=fixture(monkeypatch,b'+380501112244')
    with pytest.raises(RuntimeError,match='mismatch'):
        identity.verify_current_recipient(auto,'+380501112233')
    assert clipboard['value']==b'operator draft clipboard'
    desktop.key.assert_called_once_with('Escape')

@pytest.mark.parametrize('identity_ok', [False, True])
def test_native_send_requires_identity_before_draft_and_dispatch(monkeypatch, identity_ok):
    import asyncio
    import viber_mcp_service as service
    auto=MagicMock();auto.resolve_phone.return_value='+380501112233';auto.current_phone='+380501112233'
    auto.send.return_value={'sent':True,'verified':True}
    ledger=MagicMock();ledger.is_duplicate.return_value=False
    ledger.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=None
    @contextlib.asynccontextmanager
    async def mutex():yield
    verify=MagicMock(return_value=True,side_effect=None if identity_ok else RuntimeError('unverified'))
    monkeypatch.setattr(service,'auto',auto);monkeypatch.setattr(service,'get_shared_ledger',lambda:ledger)
    monkeypatch.setattr(service,'viber_ui_mutex',mutex);monkeypatch.setattr(identity,'verify_current_recipient',verify)
    monkeypatch.setenv('VIBER_ENABLE_SEND','1')
    result=asyncio.run(service.send_message('+380501112233','Synthetic',idempotency_key='synthetic',verify_recipient=True))
    if identity_ok:
        assert result['recipient_verified'] is True
        assert verify.call_count==2
        auto.send.assert_called_once()
    else:
        assert result['code']=='recipient_identity_unverified'
        auto.put_draft.assert_not_called();auto.send.assert_not_called()
