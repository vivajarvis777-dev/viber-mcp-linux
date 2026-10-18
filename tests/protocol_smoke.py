"""Real MCP client/server stdio test, no GUI and no private data."""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

UPSTREAM = {'send_message','open_chat','open_and_read','reply','search_and_open','list_chats',
            'put_draft','save_to_my_notes','open_my_notes','read_open_chat','list_contacts'}

async def smoke(state):
    env={**os.environ,'VIBER_ALLOW_GUI':'0','VIBER_ENABLE_SEND':'0','VIBER_STATE_DIR':state}
    env.pop('VIBER_CONTACTS_FILE',None)
    params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'server.py')],env=env)
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            result=await session.initialize()
            tools=await session.list_tools()
            names={t.name for t in tools.tools}
            assert names==UPSTREAM|{'health','stop','read_visible'},names
            health=await session.call_tool('health',{})
            assert not health.isError
            contacts=await session.call_tool('list_contacts',{})
            assert not contacts.isError
            blocked=await session.call_tool('send_message',{'to':'0981901991','text':'SYNTHETIC PROTOCOL TEST — NOT SENT'})
            assert blocked.isError
            disabled_calls = {
                'open_chat':{'to':'0981901991'}, 'open_and_read':{'to':'0981901991'},
                'reply':{'text':'SYNTHETIC'}, 'search_and_open':{'name':'0981901991'},
                'list_chats':{}, 'put_draft':{'text':'SYNTHETIC'},
                'save_to_my_notes':{'text':'SYNTHETIC'}, 'open_my_notes':{}, 'read_open_chat':{},
                'read_visible':{'region':'conversation'}}
            for name, arguments in disabled_calls.items():
                response = await session.call_tool(name,arguments)
                assert response.isError, name
            stop=await session.call_tool('stop',{})
            assert not stop.isError
            print(json.dumps({'protocolVersion':result.protocolVersion,'tools':sorted(names),
                              'upstream_parity':'11/11','health':'passed','contacts':'passed',
                              'send_disabled':'passed','stop':'passed','live_viber':False}))

if __name__=='__main__':
    import tempfile
    with tempfile.TemporaryDirectory(prefix='viber-mcp-protocol-') as state:
        asyncio.run(smoke(state))
