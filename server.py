"""Viber MCP server — expose send/receive of Viber Desktop messages as MCP tools.

Transport: stdio. Register with Claude Code via `claude mcp add` (see README).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import viber_ocr
import viber_send

mcp = FastMCP("viber")


@mcp.tool()
def send_message(to: str, text: str, dry_run: bool = False) -> dict:
    """Send a Viber message.

    Args:
        to: recipient — an E.164 phone number (e.g. "+639171234567") or a contact name
            defined in contacts.json.
        text: the message body (emoji/unicode/newlines supported).
        dry_run: if true, open the chat and paste into the compose box but do NOT click
            send (nothing is sent). Useful for verifying the correct chat opened.

    Returns a dict with the resolved recipient, whether it was sent, and `verified`
    (true = the message was confirmed visible on screen after sending).
    """
    return viber_send.send_message(to=to, text=text, dry_run=dry_run)


@mcp.tool()
def open_chat(to: str) -> dict:
    """Open (foreground) a Viber conversation without sending anything.

    Args:
        to: an E.164 phone number or a contact name from contacts.json.
    """
    number = viber_send.open_chat(to)
    return {"opened": number}


@mcp.tool()
def open_and_read(to: str) -> dict:
    """Open a conversation and return its visible text in one step ("read my chat with X").

    Args:
        to: an E.164 phone number or a contact name from contacts.json.
    """
    number = viber_send.open_chat(to)
    result = viber_ocr.read_open_chat()
    result["opened"] = number
    return result


@mcp.tool()
def reply(text: str) -> dict:
    """Send `text` into the CURRENTLY OPEN chat (no navigation).

    Use after read_open_chat when the right chat is already on screen — avoids re-resolving
    or re-opening the recipient. Returns whether it sent and `verified` (seen on screen).

    Args:
        text: the message body (emoji/unicode/newlines supported).
    """
    return viber_send.reply(text)


@mcp.tool()
def search_and_open(name: str) -> dict:
    """[EXPERIMENTAL] Search Viber for `name` and open the top result; return its visible text.

    Types into Viber's search box and clicks the first result. Search-box automation is
    unreliable on this Qt build (text entry and result selection can miss), so ALWAYS check the
    returned text is the intended person before sending anything. Prefer open_chat with a number
    or a contacts.json name when possible.

    Args:
        name: the contact or chat name to search for.
    """
    return viber_send.search_and_open(name)


@mcp.tool()
def list_chats() -> dict:
    """List recent chats from the sidebar (names, previews, times, unread counts) via OCR.

    Reads only the left-hand chat list of whatever is currently on screen — a quick inbox
    overview. Reflects the sidebar's current filter/scroll position; scroll the list in Viber
    to see more.
    """
    return viber_ocr.read_chat_list()


@mcp.tool()
def put_draft(text: str) -> dict:
    """Paste `text` into the currently-open Viber chat's compose box WITHOUT sending.

    Does not navigate — it drafts into whatever chat is open right now, so the user can
    review, edit, and press send themselves. Pair with read_open_chat to draft a reply:
    read the visible conversation, compose a fitting reply, then put_draft it.

    Args:
        text: the drafted reply to place in the compose box.
    """
    return viber_send.paste_into_open_chat(text)


@mcp.tool()
def read_open_chat() -> dict:
    """Read the currently-open Viber conversation via screen OCR.

    Captures the visible Viber window and runs Apple Vision OCR over it. Returns the
    recognized lines (top-to-bottom) and the joined text. Only sees what is on screen —
    scroll the chat in Viber to bring more history into view before calling.
    """
    return viber_ocr.read_open_chat()


@mcp.tool()
def list_contacts() -> dict:
    """List the known contact name -> phone number aliases from contacts.json."""
    return {"contacts": viber_send.load_contacts()}


if __name__ == "__main__":
    mcp.run(transport="stdio")
