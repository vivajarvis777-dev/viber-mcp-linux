# Verification evidence

Scope: `/home/hannelora/projects/viber-mcp-linux`; no live Viber interaction, private chat read, GUI input on user desktop or outbound send. All sending success assertions use synthetic fixtures only. MIT remains unchanged; upstream SHA `af1d0ed1b880dc28a18f2d5198a4d09b52047bd4`.

## Unit/domain and lifecycle

Command:

```sh
.venv/bin/python -m pytest --cov=linux_domain --cov=linux_backend --cov-report=term-missing -q
```

Initial baseline run (before the follow-up below):

```text
33 passed in 2.75s
linux_backend.py   59 statements   6 missed   90%
linux_domain.py   190 statements   4 missed   98%
TOTAL             249 statements  10 missed   96%
```

Coverage applies to these two modules only, NOT atspi_worker/GUI or the whole repository. Tests cover all domain tool paths, exact literal/Unicode, existing draft protection, approval mismatch/expiry, replay/restart/crash no resend, absent approval, sending disabled, timeout kill, cancellation, sanitized errors, private state permissions and mutex contention.

## Real stdio MCP

Command: `.venv/bin/python tests/protocol_smoke.py`

Actual result:

```json
{"protocolVersion":"2025-11-25","tools":["health","list_chats","list_contacts","open_and_read","open_chat","open_my_notes","put_draft","read_open_chat","reply","save_to_my_notes","search_and_open","send_message","stop"],"upstream_parity":"11/11","health":"passed","contacts":"passed","send_disabled":"passed","stop":"passed","live_viber":false}
```

Client initializes the real subprocess server, discovers schemas and calls every upstream tool. All GUI/send calls must return MCP errors with GUI/send disabled; this is protocol/safety verification, not successful Viber execution. State isolated in an automatically deleted scratch directory.

## Real AT-SPI on synthetic GTK

Command:

```sh
GI_TYPELIB_PATH=/home/hannelora/.local/opt/viber-mcp-atspi/usr/lib/x86_64-linux-gnu/girepository-1.0 \
  dbus-run-session -- /usr/bin/python3 tests/synthetic_desktop_smoke.py
```

Actual result:

```json
{"synthetic_real_atspi":true,"identity":"passed","unicode_readback":"passed","exact_search":"passed","scoped_reads":"passed","local_button_action":"passed","live_viber":false}
```

The fixture uses a new automatically allocated Xvfb display, private D-Bus, GTK application, Gtk.TextView composer with Cyrillic/emoji/newline input, and a local button that only modifies widgets. No Viber application or shared desktop is accessed. Subprocess worker performs real accessibility IPC. Fixture and Xvfb terminate in `finally`; private D-Bus exits. GVfs may emit a teardown bus-disconnection notice after successful exit 0.

Dependency discovered: system had GI/GTK/libatspi but no Atspi typelib. Downloaded Ubuntu `gir1.2-atspi-2.0` and extracted it user-locally to `/home/hannelora/.local/opt/viber-mcp-atspi`; no sudo/system package change. Scratch `.deb` is not in Git. `mcp>=1.28.1` initially selected incompatible 2.x; pinned `<2`, lock now uses 1.28.1. Real GTK test exposed GI `Accessible.get_text` shadowing; fixed using explicit `Atspi.Text.get_text` interface dispatch. SQLite connection lifecycle fixed; final pytest run has no ResourceWarnings.

## Compile / integrity / publishing

`python -m compileall -q` succeeds for all new entrypoints/backend/domain/tests. Git whitespace check is part of final precommit. Private repository was created through GitHub API after both SSH and API identified owner `vivajarvis777-dev`; exact repository readback confirmed `private:true`. Existing GitHub credential was fetched into process memory from the authorized vault only; no token printed, stored in repo or changed. Push uses SSH.

Private repository: https://github.com/vivajarvis777-dev/viber-mcp-linux

See Git commit and final remote SHA readback for the exact delivered revision. No public publishing, release, service activation, n8n/IBAN/production/Hermes runtime configuration change or Codex retry performed.

## Still unverified / not implemented

See PARITY.md. No real Viber profile, Qt EditableText, self marker, stable message ID or delivery evidence verified. Linux OCR fallback and clipboard fallback are not implemented; unavailable accessibility fails closed. A same-UID shell is outside the approval-ceremony trust boundary. Full live operational parity must NOT be claimed from these tests.

## Independent follow-up — 2026-10-18 CEST

Starting revision: `68e7431eb9bc79a47270a93691b95cefea42af98`;
`git ls-remote origin refs/heads/main` matched before editing. RTK mode remained
`rewrite`. No production/configuration/credential restart or persistent driver.

### Actual desktop evidence (read-only, no private contents)

- Read canonical `Infrastructure/Henelora-Desktop.md`; its historical `:11.0`
  session and earlier Viber/clipboard tests were not assumed to be live.
- Targeted `/proc/*/comm` discovery found no Viber or XFCE process for any UID;
  only a root-owned Xorg among the queried desktop executable names. Own process
  environment contained no DISPLAY; session bus was `/run/user/1003/bus`.
- `loginctl show-session c7 -p State -p Active -p Type -p Display -p Remote`:
  `Display=:11`, `Remote=no`, `Type=x11`, `Active=yes`, **`State=closing`**.
  Active=yes alone does not prove an operational desktop.
- `/tmp/.X11-unix` existed but contained no X sockets. Read-only Unix socket
  connect to `/tmp/.X11-unix/X11` returned errno 2 (absent).
- `/run/user/1003/at-spi/bus` absent. Existing old at-spi launcher/registry process
  names did not prove usable IPC. A timeout-bound GI Atspi registry probe failed
  before obtaining a tree: `Failed to connect to socket /run/user/1003/at-spi/bus:
  No such file or directory`; libatspi terminated with SIGTRAP. No app text was
  read or persisted. Do not repeat full tree probes until session IPC is restored.
- Consequently Qt EditableText **support remains unknown**, not proven absent.
  No Viber roles/interfaces/selectors were available to calibrate. No screenshots,
  sidebar/history reads, input, navigation, clipboard mutation or actual sends.
  OCR/clipboard fallbacks remain unimplemented rather than built around invented
  UI coordinates/semantics. This is a bounded blocker report, not full adaptation.

### Changes and verification

- Post-send observation now polls without resending, with repeated identity and
  protected-draft checks, bounded wait and cancellation. Async render, timeout,
  cancellation, recipient/draft change and replay tested against fake backend.
- Closed reason codes expose missing interfaces/selectors without raw UI/errors;
  malformed/untrusted worker error output is sanitized. Per-token replay is
  explicitly not business-event idempotency; fresh approval may resend same text.
- `.venv/bin/python -m pytest --cov=linux_domain --cov=linux_backend --cov=linux_errors --cov-report=term-missing -q`:
  **49 passed in 9.17s**. Module coverage: backend 94%, domain 97%, errors 78%,
  combined 96% (295 statements, 13 missed). Excludes actual Viber/Qt compatibility.
- `.venv/bin/python tests/protocol_smoke.py`: exit 0, upstream 11/11,
  health/contacts/send_disabled/stop passed, `live_viber:false`.
- `GI_TYPELIB_PATH=/home/hannelora/.local/opt/viber-mcp-atspi/usr/lib/x86_64-linux-gnu/girepository-1.0 dbus-run-session -- /usr/bin/python3 tests/synthetic_desktop_smoke.py`:
  exit 0, real AT-SPI identity/Unicode/exact-search/scoped-read/local-button checks
  passed on private GTK/Xvfb only; `live_viber:false`. Expected GVfs bus teardown
  notice followed completion. No shared desktop attached.
- Authenticated official GitHub GET `/repos/vivajarvis777-dev/viber-mcp-linux`
  returned `private:true`, `default_branch:main`, exact full_name. Existing
  authorized BWS `GITHUB_TOKEN` held only in process memory, never printed;
  `gh` CLI unavailable, official API used instead. No credential changes.
- `git diff --check` and compileall of changed Python modules/tests completed
  successfully. Fixture Python PIDs were absent after completion. One pre-existing
  own Xvfb process started 2026-09-28 was observed and left untouched; it is not
  evidence of a usable shared Viber session.
- Updating inherited `CLAUDE.md` was explicitly denied by the protected
  instruction-file write guard. No bypass or second write attempted; it remains
  inaccurate. README now points to current Linux status and this exact blocker.
