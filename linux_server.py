"""Backward-compatibility decorator delegating to viber_mcp_service.

Canonical single server: server.py -> viber_mcp_service.py.
Hermes (stdio) and n8n (HTTP) both run against the unified 8-tool service.
"""
from __future__ import annotations

import asyncio
from linux_domain import Service
from viber_mcp_service import (
    mcp,
    run_server,
    create_http_app,
    BearerAuthMiddleware,
    health,
    list_contacts,
    find_contact,
    save_contact,
    open_chat,
    read_open_chat,
    put_draft,
    send_message,
)

service = Service()


async def invoke(function, *args):
    try:
        return await asyncio.to_thread(function, *args)
    except asyncio.CancelledError:
        await asyncio.to_thread(service.stop)
        raise


if __name__ == '__main__':
    run_server()
