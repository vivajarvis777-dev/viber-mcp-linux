"""Real canonical MCP client/server stdio test, no live GUI or private data."""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CANONICAL = {'health', 'list_contacts', 'find_contact', 'save_contact',
             'open_chat', 'read_open_chat', 'put_draft', 'send_message'}

def payload(response):
    assert not response.isError, response
    return json.loads(next(item.text for item in response.content if item.type == 'text'))

async def smoke(state):
    env = {**os.environ, 'VIBER_ENABLE_SEND': '0', 'VIBER_AUTO_REPLY_ENABLED': '0',
           'VIBER_AUTO_APPROVE': '0', 'VIBER_STATE_DIR': state}
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve().parents[1] / 'server.py')], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert names == CANONICAL, names
            by_name = {tool.name: tool for tool in tools.tools}
            for name in ('health', 'list_contacts', 'find_contact', 'read_open_chat'):
                assert by_name[name].annotations.readOnlyHint is True, name
            for name in ('send_message', 'open_chat', 'put_draft', 'save_contact'):
                assert by_name[name].annotations.readOnlyHint is False, name
            assert by_name['send_message'].annotations.destructiveHint is True
            for field in ('approval_token', 'dry_run', 'idempotency_key', 'verify_recipient'):
                assert field in by_name['send_message'].inputSchema['properties'], field
            health = payload(await session.call_tool('health', {}))
            assert health['status'] == 'ok', health
            assert health['send_enabled'] is False, health
            assert health['auto_responder']['enabled'] is False, health
            contacts = payload(await session.call_tool('list_contacts', {}))
            assert isinstance(contacts['contacts'], dict), contacts
            assert isinstance(contacts['details'], dict), contacts
            blocked = payload(await session.call_tool('send_message', {
                'to': '+12025550123', 'text': 'SYNTHETIC PROTOCOL TEST — NOT SENT',
                'idempotency_key': 'protocol-send-disabled'}))
            assert blocked['ok'] is False, blocked
            assert blocked['code'] == 'send_disabled', blocked
            assert blocked['idempotency_key'] == 'protocol-send-disabled', blocked
            print(json.dumps({'protocolVersion': result.protocolVersion, 'tools': sorted(names),
                              'health': 'passed', 'contacts': 'passed',
                              'send_disabled': 'passed', 'live_viber': False}))

if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory(prefix='viber-mcp-protocol-') as state:
        asyncio.run(smoke(state))
