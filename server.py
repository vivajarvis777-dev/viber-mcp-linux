"""Platform entrypoint; Linux never loads legacy macOS send heuristics."""
import sys
if sys.platform.startswith('linux'):
    from linux_server import mcp
else:
    from upstream_server import mcp

if __name__ == '__main__':
    mcp.run(transport='stdio')
