import subprocess
import threading
import time
import pytest
from linux_backend import LinuxBackend, SafetyError


def test_unconfigured_no_process(monkeypatch):
    monkeypatch.delenv('VIBER_ALLOW_GUI',raising=False)
    def forbidden(*a,**k): raise AssertionError('process started')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    b=LinuxBackend()
    assert b.health()['live_chat_read'] is False
    with pytest.raises(SafetyError): b.identity()
    assert b.stop()['input_grabs'] is False

class Process:
    def __init__(self,*args,**kwargs): self.returncode=None;self.killed=False;self.calls=0
    def communicate(self,*args,**kwargs):
        self.calls+=1
        if self.calls==1: raise subprocess.TimeoutExpired('synthetic',.01)
        return '',None
    def poll(self): return self.returncode
    def kill(self): self.killed=True;self.returncode=-9

def test_timeout_kills_worker(monkeypatch):
    monkeypatch.setenv('VIBER_ALLOW_GUI','1')
    p=Process();monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:p)
    b=LinuxBackend('synthetic.json',timeout=.01)
    with pytest.raises(SafetyError,match='timeout'): b.identity()
    assert p.killed and p.calls==2 and b.process is None

def test_cancellation_kills_and_prevents_next_action(monkeypatch):
    monkeypatch.setenv('VIBER_ALLOW_GUI','1')
    b=LinuxBackend('synthetic.json');p=Process();b.process=p
    b.stop()
    assert p.killed
    with pytest.raises(SafetyError,match='cancelled'): b.identity()

def test_invalid_worker_output_is_not_success(monkeypatch):
    monkeypatch.setenv('VIBER_ALLOW_GUI','1')
    p=Process();p.returncode=1
    p.communicate=lambda *a,**k:('SENSITIVE UI DATA',None)
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:p)
    with pytest.raises(SafetyError,match='operation failed') as err: LinuxBackend('synthetic.json').identity()
    assert 'SENSITIVE' not in str(err.value)

def test_cross_process_mutex(tmp_path):
    from linux_domain import Service
    from tests.test_domain import Fake
    import fcntl,os
    s=Service(Fake(),tmp_path/'state');s.store()
    fd=os.open(s.root/'desktop.lock',os.O_CREAT|os.O_RDWR,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        with pytest.raises(SafetyError,match='busy'): s.put_draft('synthetic')
    finally: os.close(fd)
    assert s.put_draft('synthetic')['drafted']
