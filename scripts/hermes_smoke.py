"""Exercise an installed Hermes MCP registry in an isolated, disposable home.

No LLM, production config, credentials, gateway restart or write-capable tool call.
Run with the installed Hermes Python and explicitly selected dependency directory.
"""
import argparse
import json
import os
from pathlib import Path
import site
import sys
import tempfile
import time


def find_payload(value, key='source', expected='x11_tesseract'):
    if isinstance(value, str):
        try:
            return find_payload(json.loads(value), key, expected)
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict):
        if value.get(key) == expected:
            return value
        for item in value.values():
            result = find_payload(item, key, expected)
            if result is not None:
                return result
    if isinstance(value, list):
        for item in value:
            result = find_payload(item, key, expected)
            if result is not None:
                return result
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-root', type=Path, required=True)
    parser.add_argument('--site-packages', type=Path, required=True)
    parser.add_argument('--entry-json', type=Path, required=True,
                        help='Private JSON containing only this Viber MCP server entry')
    parser.add_argument('--read-status', action='store_true')
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.entry_json.read_text())
    config['env'] = {**config.get('env', {}), 'VIBER_ALLOW_INPUT': '0', 'VIBER_ENABLE_SEND': '0'}
    config['tools'] = {'include': ['health', 'read_visible']}
    config['supports_parallel_tool_calls'] = False
    config['trust'] = 'untrusted'
    with tempfile.TemporaryDirectory(prefix='viber-hermes-smoke-') as home:
        # Must happen before importing Hermes: all config/cache/log paths are isolated.
        os.environ['HERMES_HOME'] = home
        os.chdir(home)
        site.addsitedir(str(args.site_packages.resolve()))
        sys.path.insert(0, str(args.hermes_root.resolve()))
        try:
            from tools.mcp_tool_discovery import register_mcp_servers
            from tools.mcp_tool_lifecycle import shutdown_mcp_servers
        except ImportError:
            from tools.mcp_tool import register_mcp_servers, shutdown_mcp_servers
        from tools.registry import registry
        try:
            names = register_mcp_servers({'viber_acceptance': config})
            if args.inspect_only:
                from tools import mcp_tool as core
                metadata = []
                for server in core._servers.values():
                    for tool in server._tools:
                        if tool.name in ('health', 'read_visible'):
                            annotations = getattr(tool, 'annotations', None)
                            if hasattr(annotations, 'model_dump'):
                                annotations = annotations.model_dump(by_alias=True)
                            metadata.append({'name': tool.name, 'annotations': annotations,
                                             'type': type(tool).__name__})
                print(json.dumps({'tools': metadata, 'captured_hints': {str(k): v for k, v in core._tool_read_only_hints.items()}}))
                return
            health = [n for n in names if n.endswith('_health')]
            readers = [n for n in names if n.endswith('_read_visible')]
            assert len(health) == len(readers) == 1, 'Expected health and read_visible registry entries'
            assert not any(n.endswith(('_send_message', '_reply', '_put_draft')) for n in names)
            result = registry.dispatch(health[0], {})
            health_payload = find_payload(result, 'backend', 'x11-ocr')
            assert health_payload is not None and health_payload.get('send_enabled') is False, 'Hermes health dispatch failed'
            summary = {'hermes_registry': True, 'registered_tools': names, 'health_dispatch': 'passed',
                       'production_config_changed': False, 'model_called': False,
                       'write_tools_registered': False, 'live_read': False}
            if args.read_status:
                start = time.monotonic()
                result = registry.dispatch(readers[0], {'region': 'status'})
                data = find_payload(result)
                assert data is not None, 'Hermes status read failed; private output suppressed'
                summary.update(live_read=True, latency_ms=round((time.monotonic() - start) * 1000),
                               line_count=data.get('line_count'),
                               offline_observed='no internet connection' in data.get('text', '').casefold())
            print(json.dumps(summary))
        finally:
            shutdown_mcp_servers()


if __name__ == '__main__':
    main()
