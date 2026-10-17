"""Linux Viber MCP, stdio only. Human approval is intentionally not an MCP tool."""
from mcp.server.fastmcp import FastMCP
from linux_domain import Service

mcp = FastMCP('viber-linux')
service = Service()

@mcp.tool()
def send_message(to: str, text: str, dry_run: bool = False, approval_token: str | None = None) -> dict:
    """Send exact approved text/recipient, or safely place a draft. Disabled by default."""
    return service.send_message(to,text,dry_run,approval_token)

@mcp.tool()
def open_chat(to: str) -> dict:
    """Open exact phone/explicit alias, verifying contact-details identity."""
    return service.open_chat(to)

@mcp.tool()
def open_and_read(to: str) -> dict:
    """Open verified recipient and read visible conversation only."""
    return service.open_and_read(to)

@mcp.tool()
def reply(text: str, approval_token: str | None = None, to: str | None = None) -> dict:
    """Reply in current chat; exact recipient and independent approval required."""
    return service.reply(text,approval_token,to)

@mcp.tool()
def search_and_open(name: str) -> dict:
    """Search exact name with explicit contact alias; reject ambiguous identity."""
    return service.search_and_open(name)

@mcp.tool()
def list_chats() -> dict:
    """Read only visible sidebar names, previews, times and unread labels."""
    return service.list_chats()

@mcp.tool()
def put_draft(text: str) -> dict:
    """Place Unicode-verified draft without overwriting another draft or sending."""
    return service.put_draft(text)

@mcp.tool()
def save_to_my_notes(text: str, approval_token: str | None = None) -> dict:
    """Save approved text to independently verified self-chat."""
    return service.save_to_my_notes(text,approval_token)

@mcp.tool()
def open_my_notes() -> dict:
    """Open verified self-chat; label alone is not self identity proof."""
    return service.open_my_notes()

@mcp.tool()
def read_open_chat() -> dict:
    """Read visible conversation, not sidebar or offscreen history."""
    return service.read_open_chat()

@mcp.tool()
def list_contacts() -> dict:
    """Read configured private aliases; no contacts scraping."""
    return service.list_contacts()

@mcp.tool()
def health() -> dict:
    """Configuration-only health: no desktop read, focus or launch."""
    return service.health()

@mcp.tool()
def stop() -> dict:
    """Cancel bounded AT-SPI worker; never creates modifiers or input grabs."""
    return service.stop()

if __name__ == '__main__':
    mcp.run(transport='stdio')
