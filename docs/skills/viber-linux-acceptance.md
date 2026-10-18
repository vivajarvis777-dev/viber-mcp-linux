---
name: viber-linux-acceptance
description: "Use when validating Linux Viber MCP desktop compatibility."
---

# Linux Viber MCP acceptance

## Operating the live MCP

- Discover current tool schemas before use; reconnects can change capabilities. A missing tool or suppressed/duplicate tool output is not a negative lookup result: obtain a fresh explicit response.
- Use `find_contact(query)` for saved names/aliases. `found: false` describes that lookup only, not Viber registration. If direct-number navigation is supported, use the exact full user-authorized number; never infer missing digits or assume a historical allowlist still applies.
- Serialize the entire open → read → draft → approved send → read-back sequence across the shared desktop. Do not parallelize chat mutations; other agents and n8n need the same queue/lock before concurrent use is safe.
- Pass the intended recipient explicitly to read/draft/send where supported. Require actual recipient evidence; an echoed request or `ok` alone is weaker than a verified header. Record missing header verification rather than inventing it.
- Show the complete final draft to Господар and wait for approval of that text and recipient before send. Draft-only requests must never invoke send. Use the current send schema, not a remembered approval-token convention.
- After send, read the exact chat back and compare the text. Report separately: tool send status, visible history, delivery/read receipt, and human confirmation. Never resend merely because verification is uncertain.
- Treat `messages` string arrays as visible text, not structured sender/time/direction evidence or complete history. Do not claim latest inbound author/time unless available and verified. Do not persist private texts, contact numbers, screenshots, or chat dumps in skills/shared notes.
- Test draft persistence separately after leaving and reopening a chat; creation verification does not prove persistence.
- Keep n8n/IBAN coupling a proposal until transport compatibility, serialization, business-event deduplication, ambiguous-send handling and explicit automation authorization are verified. Desktop MCP is not an official messaging API and does not require an LLM in principle.


- Read the project's README, EVIDENCE and PARITY plus the canonical desktop note before live probes; inherited platform instructions may describe macOS rather than Linux.
- For launcher repair, inspect AppRun and its wrapped hooks, fresh XFCE environment, `xdg-user-dir DESKTOP`, executable/trust metadata and icon-theme resolution before attributing failure to cwd. Install both the XDG applications entry and actual Desktop entry; use the bundled absolute icon and inherit session DISPLAY/D-Bus. Validate actual `gio launch`/`gtk-launch` activation against window class/PID, visible Normal state and same-PID singleton reuse; desktop-file-validate alone proves no usability. Do not read window/chat contents or restart an existing process for this check.
- Separate domain mocks, real MCP disabled-path tests, real AT-SPI on isolated GTK, and actual Viber E2E. None of the first three proves Qt/Viber EditableText or operational parity.
- Discover the current desktop from targeted process metadata and login-session state, not historical DISPLAY values. Check X11 and accessibility socket availability before loading GI Atspi: a stale accessibility launcher may remain while its socket is gone, and libatspi can abort with SIGTRAP instead of raising a Python exception.
- Verify the socket returned by org.a11y.Bus.GetAddress even when X11/Viber is live: stale bus registration can return a nonexistent path. Stop before loading libatspi; do not restart services without approval.
- Treat a Viber established TCP socket and successful website HTTPS as transport evidence only, never proof of messaging/authentication. When the user reports a failed manual message, pause GUI automation and never retry a potentially queued message. Inspect only status/network metadata or redacted errors; do not consume a running process stderr pipe.
- Use cropped header OCR only as non-authorizing calibration evidence. Never infer national-to-international recipient equivalence or turn an OCR match into verified identity; exclude screenshots/raw OCR from repository and shared notes.
- Treat loginctl Active=yes together with State=closing as insufficient proof of usable desktop. Do not restart services, launch applications, or install persistent drivers to bypass this blocker without concrete approval.
- Keep discovery read-only and content-minimal: roles/interfaces/selector structure only; no screenshots, sidebar/history scraping or private text unless separately authorized. Never invent a calibrated profile from synthetic GTK selectors.
- Preserve the exact authorized recipient literal, including leading zeroes; no country inference or implicit My Notes authorization. Sending needs separate exact-text approval.
- Verify asynchronous sends through bounded cancelable observation only, rechecking recipient and protected draft around bubble reads. Never repeat the send action to improve certainty. An empty composer alone is insufficient evidence, and UI evidence never proves delivery.
- Distinguish per-token replay suppression from business-event idempotency: a fresh approval token can resend identical text. Test and document that boundary.
- Expose a closed set of diagnostic reason codes for selector/interface failures. Never forward arbitrary worker exceptions, invalid JSON contents, UI strings, or private payloads.
- If an instruction-file write is denied, do not bypass via shell or another tool; report that file unchanged and record accurate operational status in ordinary project documentation.
