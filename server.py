"""Platform entrypoint; Linux never loads legacy macOS send heuristics."""
import sys
import os
from pathlib import Path

# MCP hosts may start in an inaccessible or unrelated working directory.
# Resolve the project directory before FastMCP's dotenv settings initialization.
os.chdir(Path(__file__).resolve().parent)
if sys.platform.startswith('linux'):
    from linux_server import mcp
else:
    from upstream_server import mcp

if __name__ == '__main__':
    mcp.run(transport='stdio')
