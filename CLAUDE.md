# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A macOS-only MCP server that sends and reads Viber Desktop messages by **automating the running,
signed-in Viber app** — Viber has no API, its message DB is encrypted, and its Qt accessibility tree
is unusable, so everything is done via the `viber://` URL scheme, synthetic HID input, and screen OCR.

## Commands

```bash
uv sync                                    # install deps (Python managed by uv)

# Standalone client = the way to test/run tools without Claude (spawns a fresh server each call,
# so it always uses the latest code). Subcommands map 1:1 to tools:
uv run client.py list                      # advertise tools
uv run client.py open|openread|search "<name-or-+E164>"
uv run client.py send  "<to>" "<text>" [--dry-run]
uv run client.py reply "<text>"            # into the currently-open chat
uv run client.py draft "<text>"            # paste into open chat, do NOT send
uv run client.py note  "<text>"            # save to My Notes
uv run client.py chats | read | contacts

# Register with Claude Code (user scope):
claude mcp add --transport stdio --scope user viber -- uv --directory "$(pwd)" run server.py
```

There is no test suite, linter, or build step. **Verify changes by driving the real app** with
`client.py` and screenshotting the Viber window (`viber_ocr.capture_window`) to confirm the outcome —
the returned `verified` flag is best-effort and gives false negatives.

After editing server code, the **registered** MCP server keeps running the old code until reconnected
(`/mcp` → reconnect `viber`, or restart Claude Code); `client.py` always runs fresh code.

## Architecture

- `server.py` — FastMCP stdio server; thin `@mcp.tool()` wrappers only. Tools: `send_message`,
  `reply`, `open_chat`, `open_and_read`, `read_open_chat`, `list_chats`, `put_draft`,
  `search_and_open`, `save_to_my_notes`, `open_my_notes`, `list_contacts`.
- `viber_send.py` — all write/navigation logic: recipient resolution (`contacts.json` alias → E.164),
  HID synthetic input, opening chats, sending. Raises `SendError`.
- `viber_ocr.py` — read side: find the Viber window, `screencapture` it, run Apple Vision
  (`VNRecognizeTextRequest`). `ocr_observations()` returns text with normalized (x,y) positions;
  `read_open_chat()` returns full-window text; `read_chat_list()` filters to the left sidebar.
- `client.py` — standalone MCP stdio client for testing.
- `contacts.json` — name→E.164 map, **git-ignored (real numbers)**; ship `contacts.example.json`.

Data flow for a send: resolve recipient → `viber://chat?number=` → poll OCR until the chat is
confirmed → click compose → clear draft → paste (clipboard, restored after) → click send → OCR-verify.

## Critical, non-obvious constraints (most bugs here come from violating these)

- **All synthetic input MUST come from a real HID event source**
  (`_SRC = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)`). Qt silently drops plain
  `CGEvent`s and System Events keystrokes. Use the `_click` / `_key` / `_type` helpers.
- **`_type` must zero modifier flags per event.** A Cmd leaking from a prior `Cmd+A` turns the next
  character into a shortcut (e.g. typing "My Notes" → **Cmd+M = minimize the window**).
- **Sidebar/search/send-button/panel-close are targeted by fixed PIXEL offsets from window edges**
  (`_send_point`, `_panel_close_point`, and the `b["X"]+175` search click), NOT fractions of the
  window. The sidebar and side panels have fixed pixel widths, so fraction-based clicks miss on
  wide/maximized windows. Only the compose box uses a fraction (`_COMPOSE_FRAC`) because the input is
  wide and forgiving.
- **Close any right-side panel before sending.** The chat-info and sticker "Settings" panels shift
  the send button left; `_ensure_panel_closed` (called inside `_paste_into_compose`) detects
  (`_side_panel_open` via OCR markers) and closes them.
- **Click the send button; do not press Return.** "Send message on Enter" may be off, in which case
  Return just inserts a newline.
- **`viber://chat?number=` navigation is slow (~seconds) and mobile-first.** Never assume the chat
  opened immediately — poll via OCR (`_wait_for_sendable_chat`). It also errors "isn't on Viber" for
  non-users and "cannot add yourself" for the user's own number (My Notes is separate).
- **Search results are substring-matched and alphabetically sorted**, so the first row is often wrong
  (searching "Ivy" lists "Divya" first). `_find_result_row` scores exact/prefix over substring and
  clicks the matched row's actual OCR position; excludes the search-bar text (y<0.12), section
  headers, phone numbers, and action rows.
- **`find_viber_window` ignores the tiny menu-bar window** (>200px filter) so captures aren't blank.
- **OCR interleaves the sidebar and the open conversation.** Use x-position filtering
  (`read_chat_list` keeps x<0.30) or headers to disambiguate; OCR also garbles small/emoji text.

## Environment requirements

- Viber running, signed in, and in a **normal window on the main desktop — not macOS fullscreen**
  (fullscreen puts it on a separate Space, causing window-ID churn and blank captures). Don't resize
  it mid-operation.
- macOS **Accessibility** (synthetic input) and **Screen Recording** (capture) granted to the process
  that launches the server (the terminal, e.g. iTerm). A stuck grant shows error 1002 ("not allowed
  to send keystrokes") despite the toggle being on — fix with
  `tccutil reset Accessibility <bundle-id>` (e.g. `com.googlecode.iterm2`) and relaunch.

## Slash command

`commands/viber-reply.md` (copy to `~/.claude/commands/`) reads the open chat and drafts a reply into
the compose box via `read_open_chat` + `put_draft` — it never sends.
