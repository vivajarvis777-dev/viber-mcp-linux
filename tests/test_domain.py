"""Synthetic domain fixtures only; NO Viber or desktop connection."""
import json
import pytest
from linux_domain import Service, SafetyError, phone

NUMBER = '2025550123'
TEXT = 'Привіт 👋\nЇжак є тут!'

class Fake:
    def __init__(self):
        self.recipient=NUMBER; self.value=''; self.rows=[]; self.sends=0; self.calls=[]; self.mode='ok'
    def reset(self): pass
    def stop(self): return {'stopped':True}
    def health(self): return {'synthetic':True}
    def identity(self): return self.recipient
    def draft(self): return self.value
    def write(self,text,recipient): self.value=text if self.mode!='bad_unicode' else '???'
    def navigate(self,query):
        self.calls.append(query)
        if query=='My Notes': self.recipient='self:my-notes'
        return {'matched':query,'low_confidence':False}
    def read(self,region): return {'lines':[region], 'line_count':1, 'text':region}
    def messages(self): return self.rows.copy()
    def send(self,recipient,text):
        self.sends+=1
        if self.mode=='crash': raise TimeoutError()
        if self.mode!='unknown':
            self.rows.append({'id':str(self.sends),'text':self.value,'outgoing':True})
            self.value=''

@pytest.fixture
def setup(tmp_path):
    b=Fake(); s=Service(b,tmp_path/'state',send_enabled=True)
    return s,b

def token(s,text=TEXT,to=NUMBER): return s.store().approve(to,text)

def test_all_read_and_navigation_tools(setup,tmp_path):
    s,b=setup
    path=tmp_path/'contacts.json'; path.write_text(json.dumps({'Test':NUMBER}))
    s.contacts_path=str(path)
    assert s.list_contacts()['contacts']['Test']==NUMBER
    assert s.open_chat(NUMBER)['opened']==NUMBER
    assert s.open_and_read(NUMBER)['text']=='conversation'
    assert s.search_and_open('Test')['matched']=='Test'
    assert s.read_open_chat()['text']=='conversation'
    assert s.list_chats()['text']=='sidebar'
    assert s.put_draft(TEXT)['verified']
    assert s.open_my_notes()['opened']=='self:my-notes'
    assert s.health()['synthetic']
    assert s.stop()['stopped']
    assert b.sends==0

@pytest.mark.parametrize('method',['send_message','reply','save_to_my_notes'])
def test_each_send_tool(setup,method):
    s,b=setup
    to='self:my-notes' if method=='save_to_my_notes' else NUMBER
    t=token(s,to=to)
    if method=='send_message': result=s.send_message(NUMBER,TEXT,approval_token=t)
    elif method=='reply': result=s.reply(TEXT,approval_token=t,to=NUMBER)
    else: result=s.save_to_my_notes(TEXT,approval_token=t)
    assert result=={'status':'sent','attempted':True,'sent':True,'delivered':None,'verified':True}
    assert b.sends==1

@pytest.mark.parametrize('value',[' 2025550123','2025550123 ','+02025550123','２０２５５５０１２３','Name','+1 2025550123',''])
def test_no_silent_normalization(value):
    with pytest.raises(SafetyError): phone(value)

def test_literal_preserved(): assert phone(NUMBER)==NUMBER

def test_default_send_disabled(setup):
    s,b=setup;s.send_enabled=False
    with pytest.raises(SafetyError): s.send_message(NUMBER,TEXT)
    assert b.calls==[] and b.sends==0

def test_requires_approval_before_navigation(setup):
    s,b=setup
    with pytest.raises(SafetyError): s.send_message(NUMBER,TEXT)
    assert b.calls==[]

def test_dry_run(setup):
    s,b=setup
    assert s.send_message(NUMBER,TEXT,True)['dry_run']
    assert b.value==TEXT and b.sends==0

def test_protect_draft(setup):
    s,b=setup;b.value='Existing private draft'
    with pytest.raises(SafetyError): s.put_draft(TEXT)
    assert b.value=='Existing private draft'

def test_expected_draft_recipient_blocks_chat_switch_after_precheck(setup):
    s,b=setup
    assert b.identity()==NUMBER  # Earlier client-side precheck.
    b.recipient='+12025550199'
    def forbidden_write(*args): pytest.fail('Wrote into changed chat')
    b.write=forbidden_write
    with pytest.raises(SafetyError, match='Exact recipient identity not verified'):
        s.put_draft(TEXT, expected_recipient=NUMBER)
    assert b.value=='' and b.sends==0

def test_expected_draft_recipient_validated_and_preserved(setup):
    s,b=setup
    result=s.put_draft(TEXT, expected_recipient=NUMBER)
    assert result['recipient']==NUMBER and result['verified'] is True
    assert b.value==TEXT and b.sends==0

def test_mismatch_recipient(setup):
    s,b=setup;b.recipient='2025550199'
    with pytest.raises(SafetyError): s.open_chat(NUMBER)
    assert b.sends==0

def test_unknown_alias(setup):
    s,b=setup
    result=s.search_and_open('Display name')
    assert result['identity_observed']==NUMBER
    assert result['recipient_verified'] is False
    assert result['send_authorized'] is False and b.sends==0

def test_unicode_mismatch(setup):
    s,b=setup;b.mode='bad_unicode'
    with pytest.raises(SafetyError): s.put_draft(TEXT)
    assert b.sends==0

@pytest.mark.parametrize('mode',['ok','unknown','crash'])
def test_replay_never_resends(setup,mode):
    s,b=setup;b.mode=mode;t=token(s)
    a=s.send_message(NUMBER,TEXT,approval_token=t)
    second=Service(b,s.root,send_enabled=True)
    r=second.send_message(NUMBER,TEXT,approval_token=t)
    assert r=={**a,'replayed':True} and b.sends==1
    if mode!='ok': assert a['status']=='unknown' and a['sent'] is None

def test_approval_bound_exact_text(setup):
    s,b=setup;t=token(s)
    with pytest.raises(SafetyError): s.send_message(NUMBER,TEXT+'!',approval_token=t)
    assert b.sends==0 and b.calls==[]

def test_approval_expired(setup):
    s,b=setup;t=s.store().approve(NUMBER,TEXT,ttl=-1)
    with pytest.raises(SafetyError): s.send_message(NUMBER,TEXT,approval_token=t)
    assert b.sends==0

def test_claim_crash_is_unknown(setup):
    s,b=setup;t=token(s)
    assert s.store().claim(t,NUMBER,TEXT) is None
    r=s.send_message(NUMBER,TEXT,approval_token=t)
    assert r['status']=='unknown' and b.sends==0

def test_no_reply_inferred_authority(setup):
    s,b=setup
    with pytest.raises(SafetyError): s.reply(TEXT)
    assert b.sends==0

def test_unchanged_bubble_not_proof(setup):
    s,b=setup;b.rows=[{'id':'1','text':TEXT,'outgoing':True}];t=token(s)
    assert s.send_message(NUMBER,TEXT,approval_token=t)['status']=='unknown'

def test_state_private(setup):
    s,b=setup; s.store()
    assert s.root.stat().st_mode & 0o077 == 0
    assert s.store().path.stat().st_mode & 0o077 == 0
