"""Fail-closed Linux domain; all desktop operations serialized across processes."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from linux_backend import configured_backend, SafetyError
from linux_errors import reason_code


def digest(recipient, text):
    return hashlib.sha256(json.dumps([recipient, text], ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def phone(value):
    # Literal national identifiers remain literal, including leading zeroes.
    if not isinstance(value, str) or not re.fullmatch(r'(?:\+[1-9][0-9]{7,14}|[0-9]{8,15})', value):
        raise SafetyError('Exact phone identifier required; no normalization performed')
    return value


class Ledger:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077:
            raise SafetyError('State directory must be owner-only')
        self.path = self.root / 'ledger.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS approvals (token TEXT PRIMARY KEY, digest TEXT, expires REAL, state TEXT, result TEXT)')
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()
    def approve(self, recipient, text, ttl=300):
        token = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO approvals VALUES (?,?,?,?,NULL)',
                       (token, digest(recipient, text), time.time()+ttl, 'approved'))
        return token
    def claim(self, token, recipient, text):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT digest,expires,state,result FROM approvals WHERE token=?', (token,)).fetchone()
            if not row or row[0] != digest(recipient, text):
                raise SafetyError('Missing approval or exact recipient/text mismatch')
            if row[2] != 'approved':
                return json.loads(row[3]) if row[3] else {'status': 'unknown', 'attempted': True, 'sent': None, 'delivered': None, 'verified': False}
            if row[1] < time.time(): raise SafetyError('Approval expired')
            db.execute("UPDATE approvals SET state='claimed' WHERE token=?", (token,))
        return None
    def finish(self, token, result):
        with self.connect() as db:
            db.execute("UPDATE approvals SET state='terminal',result=? WHERE token=?", (json.dumps(result), token))


class Service:
    def __init__(self, backend=None, state=None, contacts=None, send_enabled=None,
                 verification_timeout=3.0, poll_interval=0.1):
        if not 0 < verification_timeout <= 30 or not 0 < poll_interval <= 1:
            raise ValueError('Invalid verification timing bounds')
        self.verification_timeout = verification_timeout
        self.poll_interval = poll_interval
        self.cancelled = threading.Event()
        self.backend = backend or configured_backend()
        self.root = Path(state or os.getenv('VIBER_STATE_DIR', str(Path.home()/'.local/state/viber-mcp-linux')))
        self.contacts_path = contacts or os.getenv('VIBER_CONTACTS_FILE')
        self.send_enabled = os.getenv('VIBER_ENABLE_SEND') == '1' if send_enabled is None else send_enabled
        self.lock = threading.Lock()
        self.ledger = None  # No filesystem/UI side effects at construction.
    def store(self):
        if self.ledger is None: self.ledger = Ledger(self.root)
        return self.ledger
    @contextmanager
    def transaction(self):
        if not self.lock.acquire(timeout=2): raise SafetyError('busy')
        fd = None
        try:
            self.store()
            fd = os.open(self.root/'desktop.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            deadline = time.monotonic()+2
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline: raise SafetyError('desktop busy')
                    time.sleep(.05)
            self.cancelled.clear()
            self.backend.reset()
            yield
        finally:
            if fd is not None: os.close(fd)
            self.lock.release()
    def list_contacts(self):
        data = json.loads(Path(self.contacts_path).read_text()) if self.contacts_path else {}
        if not isinstance(data, dict) or any(not isinstance(k, str) for k in data):
            raise SafetyError('Invalid contact map')
        return {'contacts': {k: phone(v) for k,v in data.items()}}
    def resolve(self, to):
        aliases = self.list_contacts()['contacts']
        return phone(aliases.get(to, to))
    def identity(self):
        value = self.backend.identity()
        return value if value == 'self:my-notes' else phone(value)
    def verify(self, recipient):
        if self.identity() != recipient: raise SafetyError('Exact recipient identity not verified')
    def navigate(self, recipient, query=None):
        result = self.backend.navigate(query or recipient)
        self.verify(recipient)
        return {'opened': recipient, **result}
    def open_chat(self, to):
        recipient = self.resolve(to)
        with self.transaction(): return self.navigate(recipient)
    def open_and_read(self, to):
        recipient = self.resolve(to)
        with self.transaction():
            result = self.navigate(recipient)
            result.update(self.backend.read('conversation'))
            self.verify(recipient)
            return result
    def search_and_open(self, name):
        if not isinstance(name,str) or not name or len(name)>200 or '\x00' in name:
            raise SafetyError('Exact nonempty search query required')
        aliases = self.list_contacts()['contacts']
        expected = phone(aliases[name]) if name in aliases else None
        with self.transaction():
            result = self.backend.navigate(name)
            # Read the phone from contact details, never infer it from the name.
            observed = self.identity()
            if expected is not None: self.verify(expected)
            result.update(self.backend.read('conversation'))
            self.verify(observed)
            return {**result, 'opened': observed, 'identity_observed': observed,
                    'recipient_verified': expected is not None,
                    'send_authorized': False}
    def open_my_notes(self):
        with self.transaction(): return self.navigate('self:my-notes', 'My Notes')
    def read_open_chat(self):
        with self.transaction():
            recipient = self.identity()
            result = self.backend.read('conversation')
            self.verify(recipient)
            return {**result, 'recipient': recipient}
    def list_chats(self):
        with self.transaction(): return self.backend.read('sidebar')
    def read_visible(self, region='conversation'):
        if region not in ('conversation', 'sidebar', 'header', 'status'):
            raise SafetyError('Invalid visible region')
        with self.transaction():
            result = self.backend.read(region)
            return {**result, 'recipient_verified': False, 'send_authorized': False}
    @staticmethod
    def validate_text(text):
        if not isinstance(text, str) or not text or len(text)>10000 or '\x00' in text:
            raise SafetyError('Nonempty text up to 10000 characters required')
    def draft(self, recipient, text):
        self.validate_text(text)
        self.verify(recipient)
        old = self.backend.draft()
        if old and old != text: raise SafetyError('Existing draft protected; clear manually first')
        if old != text: self.backend.write(text, recipient)
        self.verify(recipient)
        if self.backend.draft() != text: raise SafetyError('Exact Unicode draft verification failed')
        return {'drafted': True, 'sent': False, 'verified': True, 'recipient': recipient}
    def put_draft(self, text):
        self.validate_text(text)
        with self.transaction(): return self.draft(self.identity(), text)
    def wait_for_send(self, recipient, text, before):
        """Observe only; never repeat the send, write, or navigation action.

        Deadline bounds starting new observations; an in-flight backend call
        has its own bounded timeout and is interrupted by stop().
        """
        deadline = time.monotonic() + self.verification_timeout
        while True:
            if self.cancelled.is_set(): raise SafetyError('cancelled')
            if time.monotonic() >= deadline:
                raise SafetyError('Send verification deadline exceeded')
            self.verify(recipient)
            draft = self.backend.draft()
            if draft not in ('', text):
                raise SafetyError('Draft changed during verification')
            after = self.backend.messages()
            self.verify(recipient)
            final_draft = self.backend.draft()
            if final_draft not in ('', text):
                raise SafetyError('Draft changed during verification')
            if self.cancelled.is_set(): raise SafetyError('cancelled')
            if time.monotonic() >= deadline:
                raise SafetyError('Send verification deadline exceeded')
            if final_draft == '' and any(
                m['id'] not in before and m['text'] == text and
                m.get('outgoing') is True for m in after
            ):
                return True
            self.cancelled.wait(min(self.poll_interval, max(0, deadline-time.monotonic())))
    def send(self, recipient, text, token, navigate=False):
        self.validate_text(text)
        if not self.send_enabled: raise SafetyError('Sending disabled')
        if not token: raise SafetyError('Independent human approval token required')
        with self.transaction():
            previous = self.store().claim(token, recipient, text)
            if previous is not None: return {**previous, 'replayed': True}
            attempted = False
            result = {'status': 'blocked', 'attempted': False, 'sent': False, 'delivered': None, 'verified': False}
            try:
                preflight = getattr(self.backend, 'preflight_send', None)
                if preflight is not None:
                    preflight()
                if navigate: self.navigate(recipient, 'My Notes' if recipient=='self:my-notes' else None)
                self.draft(recipient, text)
                before = {m['id'] for m in self.backend.messages()}
                self.verify(recipient)
                if self.backend.draft() != text: raise SafetyError('Draft changed before send')
                attempted = True
                self.backend.send(recipient, text)
                if getattr(self.backend, 'stable_message_ids', True) is False:
                    raise SafetyError('no_stable_message_ids')
                verified = self.wait_for_send(recipient, text, before)
                result = {'status': 'sent' if verified else 'unknown', 'attempted': True,
                          'sent': True if verified else None, 'delivered': None, 'verified': verified}
            except Exception as error:
                result = {'status': 'unknown' if attempted else 'blocked', 'attempted': attempted,
                          'sent': None if attempted else False, 'delivered': None, 'verified': False,
                          'reason': reason_code(error)}
            finally:
                self.store().finish(token, result)
            return result
    def send_message(self, to, text, dry_run=False, approval_token=None):
        recipient = self.resolve(to)
        self.validate_text(text)
        if dry_run:
            with self.transaction():
                self.navigate(recipient)
                return {**self.draft(recipient,text), 'dry_run': True}
        return self.send(recipient,text,approval_token, navigate=True)
    def reply(self, text, approval_token=None, to=None):
        # Explicit identity is mandatory for sends: never infer authorization from open UI.
        if to is None: raise SafetyError('reply requires exact to and independent approval')
        return self.send(self.resolve(to),text,approval_token)
    def save_to_my_notes(self, text, approval_token=None):
        return self.send('self:my-notes',text,approval_token,navigate=True)
    def health(self): return self.backend.health()
    def stop(self):
        self.cancelled.set()
        return self.backend.stop()
