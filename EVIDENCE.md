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

### GitHub verification

- Private repository confirmed via GitHub API. Draft PR:
  https://github.com/vivajarvis777-dev/viber-mcp-linux/pull/1 .
- Source commit `a33e42b3f1f65f38d239a1beec5452ac2fdec599` verified on remote branch.
- GitHub Actions run 39099935772 succeeded for both jobs: Debian Bookworm container
  with Python 3.11 (unit + real MCP stdio), and Ubuntu 24.04 isolated X11 fixture.
- Господар confirmed the same Viber account works on the phone. Desktop remains
  offline; clean desktop re-pairing requires separate approval and manual QR scan.

## Clean-profile approval and Hermes compatibility probe — 2026-10-18

Господар explicitly approved closing desktop Viber, preserving the current
`.ViberPC` in a private backup, and preparing a fresh profile/QR for manual phone
pairing. That operation completed; the preserved profile is under the existing
private reinstall rollback root. New Viber displayed phone/scan instructions,
with no connection-error marker observed on the activation screen. QR contents,
activation strings and screenshots were not saved or printed. This does not
prove a paired or online messaging session; manual activation is pending.

An isolated process used the actual installed Hermes runtime and its committed
Python 3.14 dependency environment. Production config was not loaded/changed;
HERMES_HOME was temporary, no model was called, only health/read_visible were
registered. Metadata discovery succeeded but `trust:untrusted` blocked health:
wire `readOnlyHint:true` became an internal false hint. Actual SDK v2 exposes
`read_only_hint`, while Hermes checks only the SDK v1 camelCase attribute.
The approval prompt was not accepted and the RPC did not execute.

Prepared `compat/hermes-sdk2-readonly.patch`; did not patch production or weaken
trust. 15 fail-closed compatibility cases passed, plus actual installed SDK2
reader/writer classification against the proposed pure function. Patch applies
cleanly to a copy of the installed module. See compat/README.md.

Also moved the X11 send preflight ahead of navigation/drafting. An offline or
uncalibrated attempt now returns blocked before any clipboard/UI write; the
worker rechecks immediately before clicking. 106 tests pass after this change.

## Activated read-only deployment and bounded input investigation — 2026-10-18

This section supersedes earlier pending-activation/deployment statements above.
The owner confirmed QR activation and explicitly authorized the SDK2 runtime
patch, read-only configuration, gateway restart, then AT-SPI/Viber restart.

### Verified operational state

- Backed up runtime module and complete private config before changing either.
  SDK2 patched module SHA256:
  `01c79a0eb4dfc8eac6a08fce5e428b70a99044ed9385abaafa0ae5dcf2b37028`.
  Unrelated config values were semantically preserved.
- Hermes includes only health/read_visible/list_chats/list_contacts, with
  trust=untrusted, parallel calls disabled, INPUT=0 and SEND=0. Actual installed
  Hermes registry successfully called health/read_visible after the patch.
  This was an isolated process using the real runtime/config, not an LLM turn
  or proof of discovery inside the gateway process.
- Latest service checks: hermes-hannelora.service PID3151056 active/running;
  Viber PID3182753 active/running; user at-spi-dbus-bus.service PID3175755
  active/running. Hermes dashboard was not restarted.
- AT-SPI's old socket was stale. After the approved restart GetAddress returned
  a connectable display-specific socket. Do not hardcode the old socket path.
  Viber exposes Text but not EditableText for its composer. The new bounded
  helper validates PID/frame/geometry/visible point before reading only that
  element; static Atspi.Text.get_text avoids GI method shadowing.
- The VPS network is managed by networkd while NetworkManager reports
  disconnected for unmanaged interfaces. Qt's bundled networkmanager backend
  therefore reported offline. Moving only Viber's networkmanager plugin into a
  private rollback folder and selecting GLib's netlink monitor removed the
  offline banner. Process maps confirmed libqglib; no host network changes.
  See docs/VPS-TROUBLESHOOTING.md. This does not establish message delivery.
- Latest read-only MCP status calls: 1094/997/973 ms, median997 ms, one line each,
  no offline marker in that region, no private text printed. Native composer
  read confirmed length0. These timings exclude model/provider latency.

### What remains unverified

- Exact test-contact identity was obtained through Copy number and native URI
  navigation passed once (~3742 ms). That is not evidence of reliable input.
- Later guarded drafting failed intermittently with ui_command_failed. Failures
  include xdotool getwindowpid/getactivewindow and a composer mouse command.
  strace localized one read query to XOpenDisplay's initial socket reply wait;
  the three-second timeout happened before its window-property query.
- Isolated CLIPBOARD and PRIMARY ownership probes returned a new X connection
  in 14/8 ms; twelve plain active-window queries also passed. Neither proves
  a root cause for the intermittent Viber sequence. PRIMARY paste and an added
  click delay did not produce a verified draft and were removed from the patch.
- Native draft read was still empty after failed input. No test send was invoked;
  the actual MCP approval ledger contained zero rows. No human token was issued.
- The owner approved an isolated Remmina clipboard-sync test. A private profile
  backup was created; only disableclipboard changed 0→1 on disk. A new connection
  prompted for a password, so that prompt and pending close were cancelled and
  the established session was preserved. No credentials were read or injected.
  The new setting has NOT been demonstrated in the active RDP connection.
- Need manual RDP authentication before one draft-only test. Production remains
  pinned to the verified read-only release. Do not infer a successful reconnect
  from a file setting or remmina command exit code.

### Current code validation

- 125 unit/regression tests passed in10.16s (Python3.12). Includes failed focus,
  clipboard and UI command at Service send level: blocked, attempted=false,
  sends=0, and same-token replay still sends0; plus exact scoped AT-SPI reads,
  hidden/ambiguous/wrong-PID rejection and changed send-button pixels.
- New 36×36 send-button template guard prevents clicking a reflowed toolbar or
  microphone. No live send template is calibrated. Synthetic fixtures can
  exercise the button independently of any real account.
- Synthetic test identifiers were replaced with fictional NANP555 numbers.
  Historical Git commits may still contain the previously used test identifier;
  history was not rewritten.
- Latest production code remains at52e7ef2 until later explicit deployment of
  the input work. New GitHub CI must be checked against the new PR head.

Final independent checks of this working tree: `git diff --check` clean; actual
MCP stdio protocol2025-11-25, all14 tools, disabled-send/stop checks passed.
On the VPS an isolated Xvfb/GTK display passed OCR identity, exact Ukrainian/emoji/
newline clipboard readback, clipboard restoration, scoped reads and one synthetic
button callback. It did not interact with Viber or send network messages.

Final metadata review: read_open_chat is conservatively marked non-read-only
because the optional Copy number identity path opens a contact menu and changes
then restores clipboard ownership. The protocol smoke asserts that annotation;
read_visible/list_chats/list_contacts/health retain read-only metadata. Production
already excludes read_open_chat, so its four-tool filter is unchanged.

After that annotation change:125 tests passed in9.98s and MCP protocol smoke
passed, including the new annotation assertion. Previous code commit4a5bea6
passed both Debian and X11 CI (runs39110323044/39110321066); the final metadata
commit requires its own current-head CI confirmation.

## Post-reconnect acceptance attempt — 2026-10-18, 10:11 server time

The owner directly confirmed a new login with Viber chats visible. The saved
Remmina profile had disableclipboard=1. Initial guard correctly rejected the
desktop background as foreground; the operator activated the observed Viber
window, then verified unchanged PID3182753, geometry459,94,1085,780 and native
draft length0. No worker auto-focus or safety guard was disabled.

Exactly one subsequent MCP put_draft returned isError=true/ui_command_failed
in4221ms, with SEND=0. No write retry was made. A separate native read afterwards
confirmed draft length0 and the actual approval ledger still had zero rows.
Production read_visible(status) then passed in987ms with no offline marker.
The comparison did not fix input and does not establish clipboard/RDP as cause.
Saved Remmina disableclipboard was restored to0, preserving other current fields;
the established session was not interrupted again, so the setting takes effect
on the next connection. The private backup remains outside Git.

Code commit07320d8d7df6352881a0506fa30276a2a8d3c2af passed Debian and X11 CI
on both push and PR runs39110425842/39110428835. Subsequent changes only update
this acceptance record. Production checkout remains52e7ef2, read-only.

## Narrow diagnostic repair, no further live input

Six baseline and six actual-MCP-environment read-only X11 queries all returned0.
MCP DISPLAY=:10.0/XDG session settings matched the live session; its private
OCR library directory contains no libX11/libxcb/libxdo overrides. The first
baseline query took695ms, later queries9–22ms; MCP queries10–16ms. This does not
identify the intermittent XOpenDisplay failure or attribute it to clipboard.

Confirmed code-level diagnostic defects: command() discarded timeout/exit kind,
and clipboard restoration/menu cancellation could replace the original error.
The narrow patch adds opt-in, owner-only, bounded JSONL fixed categories and
preserves the first exception when cleanup also fails. No raw argv/stdin/stderr,
private text, phone, token, or exception strings are recorded. FIFO logging is
nonblocking and symlinks/public destinations are rejected. No input retry added.

Final local suite:133 passed in10.15s. Protocol smoke passed (14 tools and
annotation guards). Isolated VPS Xvfb fixture passed exact Unicode/clipboard/
button verification after the cleanup change. The final O_NONBLOCK guard only
affects opt-in diagnostics and is additionally tested with a FIFO subprocess.
Development read-only MCP probe with diagnostics enabled succeeded in1005ms;
no diagnostic file was created because there was no failure. No further live
input or send was performed. Production remains on its read-only release.
The repair makes the next failure diagnosable; it is NOT a verified input fix.

## Diagnostic acceptance attempt and corrected harness

The owner explicitly authorized one further put_draft with diagnostics. Before
that call native draft length0, PID3182753 and geometry459,94,1085,780 were
verified. The single call returned ui_command_failed after11428ms; SEND=0.
No diagnostic event was recorded. Investigation confirmed the selected review/
private directory was UID1003/mode0775, so the owner-only logger correctly
refused it. This was an acceptance setup mistake, not an identified X11 cause.
Afterwards native draft length0 and actual approval rows0 were reverified.

The existing ~/.local/state/viber-mcp-linux directory is UID1003/mode0700.
An intentionally failing read-only xwininfo command wrote a real0600 diagnostic
there: setup/window_geometry/exit/returncode1. It did not input into the UI.
No existing access rights were changed. UID1003, the Viber process owner and
.Xauthority owner1003/mode0600/readable were checked without reading cookies;
Hermes service User=hannelora remained active.

Prepared scripts/draft_acceptance.py. It refuses BEFORE put_draft if an actual
probe record cannot be written and read, if the diagnostic path was already
used, if the supplied environment is not draft-only, or if actual MCP health
does not return literal send_enabled=false. The caller must use bounded backend
readers for current expected phone and empty composer. The RPC includes the
new optional expected_recipient; Service verifies it before backend.write,
preventing a chat switch after the earlier client precheck from selecting a
different current chat. Success also requires exact recipient and native text.
The put_draft RPC has a30s ceiling; timeout/error causes no retries/post-write UI.

149 tests passed in10.25s, including insecure diagnostic destination blocking
before RPC, one-call behavior, wrong actual health, RPC timeout, current number/
draft mismatch, changed server-side recipient and exact successful readback.
Real MCP protocol smoke passed and confirms the optional input schema. No live
input has been performed with this corrected acceptance helper.

## Approved guarded trial — 2026-10-18

The owner explicitly approved the next single draft test. Before it, the review
source hashes matched commit121edf3, effective UID/state-directory owner were1003,
state directory mode0700, native composer enabled, send calibration disabled,
and the sole visible Viber window54525982 was foreground.

The corrected acceptance helper wrote/read its diagnostic probe and called actual
MCP health once. It then stopped during the bounded recipient precheck:
`clipboard_failed`,4694ms total, **put_draft calls0**, health calls1, SEND=0.
Recorded event: phase=identity, command_kind=clipboard, failure_kind=timeout,
timeout_seconds=3. The protected diagnostic file was present in the state dir.
A separate native read afterwards confirmed draft length0; approval ledger rows0.
No write retry or send was performed.

Read-only investigation afterwards: CLIPBOARD owner window2097153 advertised
TARGETS/TIMESTAMP/MULTIPLE/STRING/UTF8_STRING; it exposed no _NET_WM_PID or WM_CLASS,
so no owner process was attributed. An xsel read returned0 bytes after1606ms;
xclip UTF8 read returned exit1 after1830ms with0 bytes; a subsequent bounded
xsel read exceeded3s. Clipboard contents were not printed. These probes establish
unstable/unavailable clipboard retrieval, not the identity of the faulty process
or the cause of previous X11 connection failures. No timeout limit was increased and no
fallback converted a failed read into an empty clipboard.

Next proposed action, not performed: explicitly clear only this desktop's
CLIPBOARD selection, verify the reset once, then run one diagnostic draft-only
trial with the same expected recipient/text guards. Clearing may discard existing
copied content, so separate owner approval is required. No production/Remmina
changes, additional access, service restart, or send is proposed.

## Isolated selection-owner reproduction and narrow fixes

No real DISPLAY:10 or user clipboard operations were performed for this phase.
The test driver allocated a fresh Xvfb via -displayfd, removed DBUS/XAUTHORITY
from fixture clients and controlled a synthetic X11 SelectionRequest owner.

The installed VPS xsel reports1.2.1, binary SHA256
`3d8a4aff612177a1daca8c21740e258f1ebaf64aa74f93819829194a0af73d92`.
Upstream tag1.2.1 resolves to8c89a9225ea898b67c5a067d1a7f8e78f0a458aa. Its
get_selection_text/main behavior agrees with the observed binary; no claim of
byte-for-byte equivalence to distribution-patched source is made.

BEFORE FIX: a fake owner advertised UTF8_STRING but refused both UTF8 and STRING
conversion. xsel returned rc0 with0 bytes. Actual old Desktop.clipboard_get
accepted that as data, and the new regression stopped with
`AssertionError: Accepted failed conversion: refuse`. Source inspection also
confirms that both xsel and xclip may fall back from UTF8_STRING to STRING.
A plain CLI swap therefore would not provide strict UTF8 semantics. Output mode
is not xsel's daemon mode; inherited daemon output pipes are not established as
the cause of the observed live read timeout. Input writers already use DEVNULL
for stdout/stderr, so their detached owners cannot hold a captured output pipe.

AFTER FIX: clipboard_reader.py performs one exact GTK3 wait_for_contents target
request in a bounded helper, validates type/format/length/UTF8 and distinguishes
valid empty data from failure. Timeout remains3s; stdout is private protocol data,
not diagnostic text. The helper does not set/clear ownership, fork or daemonize.
Xvfb cases refuse/fallback/wrongtype/silent/empty/unicode/switch all passed.
On timeout and normal exit the driver verifies helper returncode, closed stdout/
stderr and ChildProcessError from a second waitpid (already reaped). The owner
switch case exercises Desktop.clipboard, not only the standalone byte reader.

A second reproduced defect was unconditional Escape after snapshot failure.
Fixed cleanup to act only when the contact menu might have opened. The regression
asserts no click/key/set/clear after failed snapshot, preserving the primary error.
Thus earlier evidence of no draft/send did not imply zero UI: the old cleanup
could issue Escape even before entering the clipboard body.

160 local tests passed in10.18s. Real MCP protocol smoke passed. Full isolated
GTK/Xvfb fixture with the installed xsel writer passed OCR identity, exact
Ukrainian/emoji/newline readback, clipboard restoration and local button callback.
CI now includes the hostile-owner fixture alongside the existing desktop fixture.
GTK3 GI is now an explicit X11-input dependency; it already existed on the VPS,
so no host packages, access rights or production services were changed.

The new reader is NOT claimed to restore an unresponsive real owner or to solve
all prior live X11 connection failures. Production remains on52e7ef2/read-only.
The previous guarded trial4694ms/put_draft0 is consumed; no repeat or clipboard
clearing occurred. Proposed next trial ID: VBR-20261018-STRICT-01, not authorized
or executed. It uses one fresh owner-only diagnostic path, actual health send0,
bounded identity/native draft readers and at most one expected-recipient
put_draft. No clearing of the original clipboard, restart or new access.

## VBR-20261018-STRICT-01 — consumed, no retry

A fresh approval was relayed with transcript reference
Sentinel_a643c9e1908c8191b0bf4d675974318e from source thread
01a118c3-ff1a-70f3-b53c-ef7b3ae670cb through coordinator
01a14b77-72b0-77f5-84c3-452944f34032. Before starting, the fixed trial marker
and diagnostic path were absent; source hashes matched exactly
3ef44c1232b6bc9245275c02e0374327ecf3f5ca; UID/owner1003 and state mode0700
were verified. A0600 exclusive trial marker was reserved before the attempt.
The source release and production configuration were not changed.

Actual result:11897ms, health calls1, put_draft calls0, SEND=0, approval rows0.
The actual-session health guard passed before recipient checking. The successful
initial clipboard snapshot allowed the identity-menu path to begin, but reading
the copied value then failed. Diagnostic sequence:

- setup / diagnostic_probe / probe
- identity_copy / clipboard / timeout3s (primary failure)
- clipboard_restore / clipboard / timeout2s
- cleanup / other / cleanup
- identity / window_focus / timeout3s while trying to cancel the menu
- cleanup / keyboard / cleanup

The MCP stdio context surfaced an ExceptionGroup wrapper; its generic string is
not the root cause. The first fixed diagnostic identifies the failed clipboard
read; the snapshot-restore and menu-cleanup failures are subsequent events.
No put_draft RPC, text insertion, send, automatic retry or manual clearing was
performed. The transient clipboard mutations of the approved identity check did
occur. The original clipboard snapshot and post-attempt content were both
readable but **not equal**. No raw content or content hashes were printed or
saved. Restoration failed and was not retried.

The initial post-check's window search timed out, returning
window_missing_or_ambiguous; that did NOT establish that Viber was closed or
that the composer was empty. A separate read-only AT-SPI helper subsequently
validated the same owned Viber PID3182753/frame/geometry and read draft length0.
This independent result resolves the editor uncertainty: no exact test draft
was present. The clipboard remained changed; no additional input was attempted.

Durable private record: trial-VBR-20261018-STRICT-01.json; diagnostics:
acceptance-VBR-20261018-STRICT-01.jsonl, both in the existing owner-only state
directory. The marker records consumed=true/completed=true and the independent
post-check. Local review manifest is updated to executed=true. This trial and
its approval cannot authorize another attempt. Runtime/Remmina/access unchanged.

## Isolated STRICT-01 cascade analysis; no new live UI

Confirmed classification defect: Desktop.__init__ caught any window-search
SafetyError and reported window_missing_or_ambiguous. Fixed to preserve query
errors; only xdotool search exit1 with empty stdout/stderr is treated as no match.
Unit cases cover timeout, OSError, exit1+stderr, other exit codes and actual no match.
The special exit handling cannot suppress an input-command failure.

Added fixed private helper checkpoints: clipboard_init_start (before GI import),
clipboard_init_ready, clipboard_convert_start and clipboard_convert_done. Parent
phase is passed as a validated enum. init_start alone does NOT prove XOpenDisplay
is the blocked function; it includes GI/GTK initialization. convert_done only
means the request returned, not that its data were valid. No raw content is logged.

Fresh-Xvfb models passed:
- silent selection owner: helper reaches convert_start and times out3s, but a new
  X connection responds and the synthetic writer succeeds.
- owner holds XGrabServer before helper initialization: only init_start appears;
  reader3s, restore-writer2s, focus3s and search3s time out. Search now reports
  ui_command_failed rather than claiming a missing window.
- owner grabs the server on UTF8 request: helper reaches convert_start, followed
  by the same3/2/3/3 cascade.
Terminating only the fixture owner releases its grab; post-release root queries
work, and no-match search correctly reports no matching window. No real DISPLAY,
clipboard, editor, runtime service, access right or Remmina setting was touched.

These results show that broad X-server blocking can reproduce STRICT-01's
cascade; silence of a selection owner alone did not reproduce it in this model.
They do NOT establish that real Viber/RDP grabbed the server, identify a culprit
or prove the old strace's XOpenDisplay stall is the cause of STRICT-01. Existing
logs cannot distinguish initialization from conversion wait; new checkpoints
make that distinction testable in a separately approved future observation.
166 tests passed in10.22s plus real MCP protocol smoke. The three new isolated
models passed and are included in X11 CI. No timeout increase/retry or identity
guard reduction was introduced.

## Saved-address-book-only scope update

The owner narrowed recipients to actually saved Viber contacts (relayed reference
Sentinel_c602d0fc96f0819189bbc81c65593ba6). Code review confirms list_contacts is
manual aliases, not an address-book reader; neither alias/current chat/history
nor duplicate-capable display names can establish saved membership or binding.
Only metadata of already accessible profile files was examined: three .db files,
two with SQLite headers. Read-only immutable schema inspection shows config.db
account/settings tables and data.db generic Key/Category/Value; no row values
or credentials were read. The other file's lack of SQLite header does not prove
encryption. There is no verified saved-contactID→active-chat provider in the
current implementation/evidence. No unsupported adapter or alias allowlist was
substituted. See docs/SAVED-CONTACTS.md for the bounded next read-only research
proposal. Removing identity clipboard would still leave clipboard text paste.
