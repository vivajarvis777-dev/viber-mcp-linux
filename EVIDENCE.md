# Verification evidence

## Desktop/menu repair — 2026-10-18

- Fresh own XFCE process environment: DISPLAY `:10.0`, D-Bus
  `unix:path=/run/user/1003/bus`; `xdg-user-dir DESKTOP` returned
  `/home/hannelora/Desktop`. No Viber process/window existed at initial check.
- Read upstream AppRun, both deploy hooks, AppRun.wrapped and viber.desktop.
  AppRun already resolves APPDIR independently of cwd; no environment defect
  demonstrated. Old desktop entry was executable and metadata::trusted=true.
  Actual `gio launch` of that OLD entry succeeded, starting PID 3094654 and
  visible window 54525982. Thus the reported prior launch failure did not
  reproduce; do not invent a cwd/trust diagnosis or claim it was fixed by Path.
- Confirmed integration defects: no user application-menu entry; Gtk theme
  `has_icon("viber")` false. Repaired both entries with absolute bundled icon,
  deterministic Path, executable mode and trust; no fixed DISPLAY/DBus values.
- Installed/read back `/home/hannelora/Desktop/Viber.desktop` and
  `/home/hannelora/.local/share/applications/Viber.desktop`. Both validate.
  Desktop access::can-execute=true, metadata::trusted=true. Gio DesktopAppInfo
  resolves Viber.desktop from the menu directory and should_show()=true.
- Actual repaired menu `gtk-launch Viber` exit 0: before/after PID 3094654
  unchanged, exactly one visible Viber window 54525982, class Viber/ViberPC,
  WM_STATE Normal, geometry 950x780 at 464,123. _NET_ACTIVE_WINDOW 0x340001e
  matches that window. Repaired desktop `gio launch` also exit 0; same visible
  window and PID. This verifies real entry activation, not only validation.
  No mouse grab, screenshot, chat read, clipboard, typing or message send.
- No existing process terminated/restarted; account/services/credentials untouched.
  Prior offline problem remains unresolved, not retested as messaging success.
  Stale accessibility socket warning still observed during icon-theme query.
- Installer defaults to both XDG locations, preserves existing files unless
  explicit --replace, rejects symlinks, validates bundled icon before writes.
  Four added regression tests failed before implementation; full suite afterward:
  **76 passed in 9.09s**. Protected CLAUDE.md untouched.

## Live follow-up — 2026-10-18, after desktop restoration

This section supersedes the historical no-desktop blocker below, not the absence
of operational parity. Starting revision: `76a1868ebcd20ea193e018a280942a42ef457a8d`.

- Live DISPLAY `:10.0`, own XFCE and Viber process present; visible Viber window
  initially found with WM_CLASS `Viber`, `ViberPC`, size 950x780. A tightly cropped
  top/header image showed an authenticated view, not a QR/login prompt. No chat
  history, draft, other conversation or My Notes was intentionally inspected.
- `org.a11y.Bus.GetAddress` returned `/run/user/1003/at-spi/bus` but socket connect
  raised ENOENT. Probe stopped before importing libatspi. Thus a live X11 session
  does NOT fix stale accessibility registration; actual Qt interfaces remain
  unverified. No service or Viber restart attempted.
- Actual cropped header OCR with locally extracted Tesseract 5.3.4 returned:
  `phone_candidates:1`, `literal_match_observed:false`,
  `international_form_observed:true`, `recipient_verified:false`,
  `send_authorized:false`. No normalization/mapping inferred, raw OCR and screenshots
  excluded from Git/docs. This proves image-to-OCR, not recipient authorization.
- Before the new pause instruction, a foreground request failed with BadWindow;
  subsequent class searches found no Viber window, while the same process remained.
  The new `x11_probe.py` CLI's guarded capture path was NOT live-verified end-to-end.
  It is isolated read-only calibration, not an operational OCR/clipboard backend.
- User then reported Viber offline / failed manual self-message. All UI automation
  paused immediately; no retry of the user's potentially queued message. No message
  contents, account database contents or raw private logs read for diagnosis.
- At 04:29 UTC, own Viber process remained sleeping in poll with 62 threads, and one
  established TCP connection to `52.0.252.3:443`, send/receive queues both zero.
  TCP counters showed 850 bytes sent and 5601 received, last data traffic roughly
  329 seconds earlier. No process proxy environment variables found; no open log
  files; stderr is a pipe and was NOT consumed. HTTPS www.viber.com returned 200.
  **This rules out a total host Internet outage, not an app/session failure.**
  An established (possibly idle) socket proves neither Viber authentication nor
  successful message delivery. Root cause not determined; no invented proxy/TLS fix.
- Parent independently inspected the user-provided screenshot: exact red banner
  **No internet connection**, empty central pane. This is verified application-level
  offline, not merely an inference from a failed send. Screenshot not copied to Git.
- Static installed-binary domain discovery followed by bounded parallel DNS/TCP443/
  verified TLS probes to `connect.viber.com`, `core.viber.com`, `chats.viber.com`,
  `conf.viber.com`, `account.viber.com`: all five resolved and completed verified
  TLS 1.3. No HTTP payload, authentication or messages sent. These are candidate
  service domains from binary strings, NOT proven current messaging destinations.
  Their reachability does not establish Viber's own Qt TLS/auth/session state;
  selective service/port failure or app-level fault remains unresolved.
- Safe next diagnostic: once the user's manual testing is finished, inspect only
  the application's offline/status banner or a narrowly redacted error source.
  Restart/relink/reset, proxy/firewall changes require separate concrete approval.
  Also obtain explicit mapping authorization before using an international number
  for the exact allowed national literal; never retry any queued message.

### Artifacts and executed checks

- `desktop/Viber.desktop.in`, `install_launcher.py`: portable template matching
  parent-created launcher, exclusive create, executable destination, input validation;
  no launch, trust setting or overwrite. Rendered real AppRun launcher in scratch
  and `desktop-file-validate` returned exit 0. Existing Desktop launcher unchanged.
- `x11_probe.py`: explicit GUI opt-in, narrow header geometry, foreground and UID/PID
  validation, bounded subprocesses, in-memory PNG to Tesseract, non-authorizing
  boolean-only output. No clipboard/write/send functionality. System Python Pillow
  already available; OCR debs extracted user-locally, no sudo/system install.
- `tests/test_calibration.py`: launcher validation/refusal/overwrite protection,
  header scope/geometry, exact literals, OCR ambiguity and non-authorization,
  missing accessibility transport, GUI-disabled and sanitized command failure.
- `.venv/bin/python -m pytest -q`: **72 passed in 9.60s**.
- Real MCP smoke: exit 0, all upstream 11 names, safe disabled calls passed,
  `live_viber:false`.
- Real isolated GTK/Xvfb/AT-SPI smoke: exit 0, identity, Unicode readback, exact
  search, scoped reads and local button action passed; `live_viber:false`.
- Protected `CLAUDE.md` untouched. No sends, drafts, clipboard changes, persistent
  grabs, cua-driver, service/model/credential changes. Full Linux operational
  port remains incomplete pending accessibility/session diagnosis and calibration.

## Historical baseline

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

## X11/OCR continuation and official package replacement — 2026-10-18

Base: `da06874c901521845575dd7c7eabc9524c5771ac`; working branch `codex/linux-ocr`.
The GitHub repository already existed and was confirmed private. No main rewrite.

### Implemented

- Added explicit X11 backend, local Tesseract TSV parsing, bounded region reads,
  strict phone observations, calibrated exact search, Unicode clipboard readback,
  guarded one-shot send path. No stable message IDs are invented: an X11 send
  remains unknown and cannot replay the same approval token.
- Added `read_visible`, annotations and async thread offload. FastMCP 1.x invokes
  synchronous functions inline, so the old tool wrappers prevented concurrent stop.
- Fixed startup from unrelated/inaccessible cwd: FastMCP dotenv initialization
  previously failed with `PermissionError: '.env'` when sudo inherited `/home/codex`.
- Live official Viber uses WM_CLASS ViberPC; AppImage discovery had used Viber.
  Exact matching now handles both while retaining process owner/name validation.
- XFCE demonstrated xdotool geometry double-counting the frame: 464,123 versus
  xwininfo absolute client 459,94, both 950×780. Capture and mouse positions now
  use absolute client geometry from xwininfo; regression test covers this case.

### Verification

- Local Python 3.12: **90 tests passed**, 9.34 seconds, before final documentation changes.
- True MCP stdio: protocol 2025-11-25, 14 tools, upstream names 11/11, health,
  empty contacts, stop and disabled-send behavior passed.
- On the Ubuntu 24.04 VPS, isolated Xvfb + synthetic GTK: actual X11 owner/window
  checks, Tesseract identity, Cyrillic/emoji/newline clipboard readback, preserved
  clipboard, scoped reads and one local synthetic button callback all passed.
  No actual Viber message was sent by this fixture.
- Live official Viber, **read-only MCP** (no screenshots/private text in report):
  status region: 3 calls, one line each, **867/997/891 ms**, median **891 ms**;
  sidebar: 3 calls, 22 lines each, **2012/2048/1764 ms**, median **2012 ms**.
  These are end-to-end tool-call timings in a warm MCP session, not full LLM turn
  latency and not a controlled comparison with upstream/macOS.
- Status OCR explicitly observed `No internet connection`. Sidebar's lack of this
  marker is NOT evidence of online status: it deliberately excludes the status area.
- No real search/draft/send/recipient verification, history pagination, or message
  delivery has been demonstrated. No production Hermes config/restart was performed.

### Official Viber replacement requested by Господар

Source: official https://www.viber.com/en/download/ → Ubuntu download,
https://download.cdn.viber.com/cdn/desktop/Linux/viber.deb .
Version **27.3.0.2 amd64**; downloaded file SHA256:
`961534dc0cb920006ec7ae8108b0e1ba09a476eef1e13b4b370a79cd52dd20f3`.
This records the downloaded bytes; it is not an independently published vendor signature.

The vendor preinst touches multiple users' profile ownership and Qt temporary files.
Used user-scoped extraction of official files instead of executing those scripts.
No dpkg registration or global package removal was performed. New executable:
`~/.local/opt/viber-deb-27.3.0.2/Viber`; live `/proc/<pid>/exe` matched it.
Both menu/desktop launchers point at the new wrapper. Original profile remained in
place; backup is private (profile.tar mode 0600, parent 0700). Old AppImage moved
into the private rollback directory, no longer used by launchers.

Old AppImage ignored SIGTERM. Its attempted ExitViber invocation created a second
instance instead of closing it; both exact owned executables were verified and
terminated before profile backup. No other user's processes were changed.
First new startup failed with Qt xcb plugin dependencies; missing libraries were
obtained from the configured Ubuntu apt repository and unpacked under this Viber's
private deps directory. Subsequent launch has a real visible Viber window.

Reinstallation **did not fix offline status**. Existing Viber TCP 443 connection
and absence of proxy environment variables do not prove working messaging.
Do not reset/deactivate the retained account or send a test without separate approval.
