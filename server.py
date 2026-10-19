"""Platform entrypoint; Linux loads viber_mcp_service for native X11 + AT-SPI + visual verification."""
import sys
import os
from pathlib import Path

# MCP hosts may start in an inaccessible or unrelated working directory.
# Resolve the project directory before FastMCP's dotenv settings initialization.
os.chdir(Path(__file__).resolve().parent)

_dist_paths = [p for p in ('/usr/lib/python3/dist-packages', '/usr/local/lib/python3.12/dist-packages') if os.path.exists(p)]
for p in _dist_paths:
    if p not in sys.path:
        sys.path.append(p)

if sys.platform.startswith('linux'):
    from viber_mcp_service import mcp, run_server
else:
    from upstream_server import mcp
    def run_server():
        mcp.run(transport='stdio')

for p in _dist_paths:
    if p in sys.path:
        sys.path.remove(p)

if __name__ == '__main__':
    run_server()
