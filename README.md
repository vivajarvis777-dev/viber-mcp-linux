# Viber MCP (macOS)

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant (e.g. Claude) **send and
read Viber messages** by driving your already-running, signed-in **Viber Desktop** app on macOS.

Viber has no local/public API and its message database is encrypted, so this works entirely through
UI automation:

- **Send** — open the chat via the `viber://` URL scheme, paste the text, and click the send button.
- **Receive** — capture the visible Viber window and OCR it with Apple's Vision framework.

> ⚠️ **Unofficial.** Not affiliated with, endorsed by, or supported by Viber / Rakuten. It automates
> the desktop UI on your own machine and account. UI automation is inherently version-sensitive and
> may break when Viber updates. Use at your own risk and review your account's terms of service.

---

## Why it works this way

Three hard constraints shaped the design (all verified on Viber v28.2.0):

- **The message DB is unreadable.** `~/Library/Application Support/ViberPC/<number>/viber.db` is
  encrypted with a Botan page codec (random header, not `SQLite format 3`), with no public
  key-derivation recipe. So history can't be read from disk.
- **The accessibility tree is unusable.** Viber is a Qt app; AX queries hang, so there's no
  element tree to read or click.
- **Qt ignores ordinary synthetic input.** Every click/keystroke must be generated from a real HID
  event source (`CGEventSourceCreate(kCGEventSourceStateHIDSystemState)`) — plain `CGEvent`s and
  System Events keystrokes are silently dropped by Qt's input widgets.

What's left — and what this uses — is the `viber://` URL scheme, HID-sourced input, and screen OCR.

## Tools

| Tool | Description |
|------|-------------|
| `send_message(to, text, dry_run=False)` | Open the chat for `to`, confirm it, paste `text`, click send, and OCR-verify it landed. `dry_run` pastes into the box but doesn't send. |
| `reply(text)` | Send `text` into the **currently-open** chat — no navigation. Pair with `read_open_chat`. |
| `open_chat(to)` | Bring a conversation to the foreground without sending. |
| `open_and_read(to)` | Open a conversation and return its visible text in one step. |
| `read_open_chat()` | OCR the currently-visible Viber window and return its text. |
| `list_chats()` | List the sidebar chats (names, previews, times, unread counts) via OCR — a quick inbox overview. |
| `put_draft(text)` | Paste `text` into the currently-open chat's compose box — no navigation, no send. For drafting a reply to review. |
| `search_and_open(name)` | **[experimental]** Search Viber by name and open the top result. Search-box automation is flaky on this build — always verify the returned chat before sending. |
| `list_contacts()` | Return the name → number aliases from `contacts.json`. |

`to` is either an **E.164 number** (`+639171234567`) or a **name defined in `contacts.json`**.
Unknown names error out rather than guess a recipient. `send_message` returns `verified: true` when
the sent message is confirmed on screen (`false` = not seen, `null` = couldn't check).

## Requirements

- macOS (tested on macOS 15/26, Apple Silicon)
- Viber Desktop installed, running, and signed in
- [`uv`](https://docs.astral.sh/uv/) (Python is managed by `uv`)

## Install

```bash
git clone <your-fork-url> viber-mcp
cd viber-mcp
uv sync
cp contacts.example.json contacts.json   # then edit with your real contacts
```

### macOS permissions (required)

Grant these to the app that launches the server (your terminal — iTerm/Terminal — or Claude),
in **System Settings → Privacy & Security**:

- **Accessibility** — synthetic clicks/keystrokes (sending).
- **Screen Recording** — window capture (reading + send verification).

The first send/read fails with a clear message until these are granted. After granting, **fully quit
and reopen** the host app so the permission binds.

> If you get `not allowed to send keystrokes` (error 1002) while the toggle already looks on, reset
> the stuck TCC entry and relaunch:
> `tccutil reset Accessibility <your-terminal-bundle-id>` (e.g. `com.googlecode.iterm2`,
> `com.apple.Terminal`).

## Configure contacts

`contacts.json` maps friendly names to E.164 numbers (it is **git-ignored** — it holds real numbers):

```json
{
  "Me": "+639171234567",
  "Mom": "+639181234567"
}
```

Names that aren't in the file must be given as full E.164 numbers.

## Use it from Claude Code

Register the server (user scope):

```bash
claude mcp add --transport stdio --scope user viber -- \
  uv --directory "$(pwd)" run server.py
```

Check with `claude mcp list` (should show `viber … ✓ Connected`). After editing the server code,
reconnect so Claude reloads it (`/mcp` → reconnect `viber`, or restart Claude Code). Remove with
`claude mcp remove viber`.

### `/viber-reply` slash command (optional convenience)

Copy `commands/viber-reply.md` into `~/.claude/commands/` (user scope) or your project's
`.claude/commands/`. It reads the open chat, drafts a reply in your voice, and pastes it into the
compose box **without sending** — you review and send.

```
/viber-reply
/viber-reply keep it short and warm; say I'll call tonight
```

## Use it standalone (no Claude)

A small MCP client is included for testing:

```bash
uv run client.py list                              # advertise tools
uv run client.py contacts                          # show alias map
uv run client.py open "Mom"                        # open a chat
uv run client.py send "Mom" "hello" --dry-run      # fill box, don't send
uv run client.py send "Mom" "hello"                # actually send
uv run client.py draft "a reply to review"         # drop draft in open chat (not sent)
uv run client.py read                              # OCR the open chat
```

## How it works (details)

- **Send**: `open viber://chat?number=<E164>` opens the chat (desktop navigation takes a few
  seconds, so the window is polled via OCR until the recipient's chat is confirmed — and the send is
  refused if the number "isn't on Viber"). Then: click the compose box, clear any draft, paste the
  clipboard text (emoji/unicode/newlines survive), click the send button, and OCR-verify the bubble
  appeared. The clipboard is saved and restored around the paste.
- **Receive**: the largest on-screen window owned by "Rakuten Viber" is captured with
  `screencapture -l <id>` and OCR'd by `VNRecognizeTextRequest`. It only sees what's on screen.
- Compose-box and send-button positions are computed from the live window bounds, assuming the
  contact-info **side panel is closed**. If Viber's layout changes, adjust `_COMPOSE_FRAC` /
  `_SEND_BTN_FRAC` in `viber_send.py`.

## Project layout

| File | Purpose |
|------|---------|
| `server.py` | FastMCP stdio server; defines the tools |
| `viber_send.py` | recipient resolution, HID-sourced input, send/draft logic |
| `viber_ocr.py` | window discovery, capture, Apple Vision OCR |
| `client.py` | standalone MCP client for testing |
| `contacts.json` | your name → number map (git-ignored) |
| `contacts.example.json` | template to copy |
| `commands/viber-reply.md` | optional Claude Code slash command |

## Limitations & caveats

- **OCR sees only on-screen text** — scroll to bring older messages into view; it can garble text
  or interleave the sidebar's chat previews with the conversation.
- **No message history from disk** (encrypted DB).
- **Names** resolve from `contacts.json` — Viber's own contact list can't be read.
- **Version-sensitive**: a Viber UI/layout change can require small coordinate tweaks.
- Messaging your **own number** is blocked by Viber ("cannot add yourself"); "My Notes" is separate.

## Privacy & security

- Runs **entirely locally**; it does not send your messages or contacts anywhere except into Viber.
- `contacts.json` is git-ignored so real numbers don't get committed.
- Requires powerful macOS permissions (Accessibility, Screen Recording) for the host app — grant
  only if you understand and trust that.

## License

MIT — see [LICENSE](LICENSE).
