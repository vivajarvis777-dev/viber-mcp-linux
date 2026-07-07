# Viber MCP (macOS)

Send and read Viber Desktop messages through an MCP server, driving your already-running,
logged-in Viber app. Viber has no local API and its message database is encrypted, so this works
by UI automation: **send** opens the chat via the `viber://` URL scheme, pastes the text, and clicks
the send button; **receive** captures the visible Viber window and runs Apple's Vision OCR over it.

Because Viber is a Qt app that ignores ordinary synthetic input, all clicks and keystrokes are
generated from a real **HID event source** (`CGEventSourceCreate(kCGEventSourceStateHIDSystemState)`)
— otherwise the events are silently dropped by Qt's input widgets.

## Tools

| Tool | What it does |
|------|--------------|
| `send_message(to, text, dry_run=False)` | Open the chat for `to`, confirm it, paste `text`, click send, and OCR-verify it landed. `dry_run` pastes into the box but does not click send. |
| `open_chat(to)` | Foreground a conversation without sending. |
| `read_open_chat()` | OCR the currently-visible Viber window and return its text. |
| `put_draft(text)` | Paste `text` into the currently-open chat's compose box — no navigation, no send. For drafting a reply to review. |
| `list_contacts()` | Return the name -> number aliases from `contacts.json`. |

`to` is either an E.164 number (`+639171234567`) or a name defined in `contacts.json`. Unknown
names error out rather than guess a recipient. `send_message` returns `verified: true` when the sent
message is confirmed on screen (`false` = not seen, `null` = couldn't check).

## One-time setup

1. **Contacts** - edit `contacts.json` to map names to E.164 numbers:
   ```json
   { "Me": "+639176289295", "Marianne": "+639987674893" }
   ```
2. **macOS permissions** - grant these to the app that launches the server (your terminal, e.g.
   iTerm/Terminal). System Settings -> Privacy & Security:
   - **Accessibility** - required for synthetic clicks/keystrokes (sending).
   - **Screen Recording** - required for window capture (reading + send confirmation).

   The first send/read fails with a clear message until these are granted. After granting, fully
   quit and reopen the host app so the permission binds. If you still get
   "not allowed to send keystrokes" while the toggle looks on, reset the stuck entry:
   `tccutil reset Accessibility com.googlecode.iterm2` (use your terminal's bundle id).

Note: "Send message with Enter" does **not** need to be enabled — we click the send button, so it
works either way.

## Test without Claude (standalone client)

```bash
cd ~/viber-mcp
uv run client.py list                              # advertise tools
uv run client.py contacts                          # show alias map
uv run client.py open "Marianne"                   # open a chat
uv run client.py send "Marianne" "hello" --dry-run # fill box, don't send
uv run client.py send "Marianne" "hello"           # actually send
uv run client.py draft "a reply to review"         # drop draft in open chat (not sent)
uv run client.py read                              # OCR the open chat
```

## Convenience: `/viber-reply` (Claude Code slash command)

A user-scope command at `~/.claude/commands/viber-reply.md` reads the currently-open chat, drafts a
reply in your voice, and pastes it into the compose box **without sending** — you review and send.

```
/viber-reply
/viber-reply keep it short and warm; say I'll call tonight
```

It uses `read_open_chat` for context and `put_draft` to place the reply; it never calls
`send_message`, so nothing is sent automatically.

## Register with Claude Code

Already registered at user scope with:

```bash
claude mcp add --transport stdio --scope user viber -- \
  uv --directory /Users/wawidelmundo/viber-mcp run server.py
```

Check with `claude mcp list` (should show `viber ... Connected`). The `send_message`, `open_chat`,
`read_open_chat`, and `list_contacts` tools are then available to the assistant. After editing the
server code, reconnect so Claude Code reloads it: `/mcp` in Claude Code (reconnect `viber`), or
restart Claude Code. To remove: `claude mcp remove viber`.

## How it works / limitations

- **Send**: `open viber://chat?number=<E164>` opens the chat (desktop navigation takes a few
  seconds, so we poll the window via OCR until the recipient's chat is confirmed — and refuse to
  send if the number "isn't on Viber"). Then: click the compose box, clear any draft, paste the
  clipboard text (emoji/unicode/newlines survive), click the send button, and OCR-verify the bubble
  appeared. Your clipboard is saved and restored around the paste. Compose-box and send-button
  positions are computed from the live window bounds, assuming the contact-info side panel is
  **closed**.
- **Receive**: the largest on-screen window owned by "Rakuten Viber" is captured with
  `screencapture -l <id>` and OCR'd by `VNRecognizeTextRequest`. It only sees what's on screen -
  scroll the chat to bring more history into view before reading.
- The message DB (`~/Library/Application Support/ViberPC/<number>/viber.db`) is Botan-encrypted with
  no public key-derivation recipe, so reading history from disk is not supported.
- UI automation is version-sensitive; a Viber layout/shortcut change may require small tweaks to the
  position fractions in `viber_send.py` (`_COMPOSE_FRAC`, `_SEND_BTN_FRAC`).
