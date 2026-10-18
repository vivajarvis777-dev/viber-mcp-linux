"""Platform entrypoint; Linux loads viber_mcp_service for native X11 + AT-SPI + visual verification."""
import sys
import os
from pathlib import Path

# MCP hosts may start in an inaccessible or unrelated working directory.
# Resolve the project directory before FastMCP's dotenv settings initialization.
os.chdir(Path(__file__).resolve().parent)

for p in ('/usr/lib/python3/dist-packages', '/usr/local/lib/python3.12/dist-packages'):
    if p not in sys.path and os.path.exists(p):
        sys.path.append(p)

if sys.platform.startswith('linux'):
    from viber_mcp_service import mcp
else:
    from upstream_server import mcp

if __name__ == '__main__':
    mcp.run(transport='stdio')
