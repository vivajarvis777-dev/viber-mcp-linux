import asyncio
import hmac
import json
import pytest
import uvicorn
import httpx
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

import linux_server
from linux_domain import Service, SafetyError

TEST_TOKEN = "test-secret-bearer-token-12345"


@pytest.fixture
def http_app(monkeypatch):
    monkeypatch.setenv("VIBER_MCP_HTTP_TOKEN", TEST_TOKEN)
    return linux_server.create_http_app(TEST_TOKEN)


def test_health_endpoint_auth(http_app):
    client = TestClient(http_app)

    # 1. Without token -> 401
    r_none = client.get("/health")
    assert r_none.status_code == 401
    assert r_none.json()["error"] == "Unauthorized"

    # 2. With invalid token -> 401
    r_bad = client.get("/health", headers={"Authorization": "Bearer invalid-token"})
    assert r_bad.status_code == 401
    assert r_bad.json()["error"] == "Unauthorized"

    # 3. With valid token -> 200
    r_ok = client.get("/health", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    assert r_ok.status_code == 200
    data = r_ok.json()
    assert data["platform"] == "linux"
    assert "viber_window_found" in data
    assert "read_available" in data
    assert "send_enabled" in data


@pytest.mark.anyio
async def test_streamable_http_e2e_tools():
    app = linux_server.create_http_app(TEST_TOKEN)
    port = 19876
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.3)

    try:
        # 1. Unauthenticated request must fail
        with pytest.raises(Exception):
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

        # 2. Authenticated request succeeds and lists tools
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        async with httpx.AsyncClient(headers=headers) as http_client:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {t.name for t in tools.tools}
                    assert "health" in names
                    assert "list_contacts" in names
                    assert "open_chat" in names
                    assert "send_message" in names

                    health_res = await session.call_tool("health", {})
                    assert not health_res.isError
    finally:
        server.should_exit = True
        await server_task


@pytest.mark.anyio
async def test_sse_e2e_tools():
    app = linux_server.create_http_app(TEST_TOKEN)
    port = 19877
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.3)

    try:
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        async with sse_client(f"http://127.0.0.1:{port}/sse", headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "health" in names
                assert "list_contacts" in names

                health_res = await session.call_tool("health", {})
                assert not health_res.isError
    finally:
        server.should_exit = True
        await server_task


class FakeBackend:
    def __init__(self, recipient="2025550123"):
        self.recipient = recipient
        self.value = ""
        self.rows = []
        self.sends = 0
        self.not_on_viber = False

    def reset(self):
        pass

    def stop(self):
        return {"stopped": True}

    def health(self):
        return {"platform": "linux", "read_available": True, "send_enabled": True, "viber_window_found": False}

    def identity(self):
        return self.recipient

    def draft(self):
        return self.value

    def write(self, text, recipient):
        self.value = text

    def navigate(self, query):
        if query == "My Notes":
            self.recipient = "self:my-notes"
        return {"matched": query}

    def read(self, region):
        if self.not_on_viber:
            return {"lines": ["The user isn't on Viber", "Invite to Viber"], "text": "The user isn't on Viber"}
        return {"lines": [region], "text": region}

    def messages(self):
        return self.rows.copy()

    def send(self, recipient, text):
        self.sends += 1
        self.rows.append({"id": str(self.sends), "text": self.value, "outgoing": True})
        self.value = ""


def test_ledger_duplicate_blocked(tmp_path):
    backend = FakeBackend()
    service = Service(backend, tmp_path / "state", send_enabled=True, auto_approve=True)

    # First send succeeds
    res1 = service.send_message("2025550123", "Hello unique text")
    assert res1["status"] == "sent"
    assert backend.sends == 1

    # Second send with same text and recipient is blocked by ledger
    with pytest.raises(SafetyError, match="Duplicate message to recipient blocked by ledger"):
        service.send_message("2025550123", "Hello unique text")
    assert backend.sends == 1

    # Different text to same recipient is allowed
    res2 = service.send_message("2025550123", "Different text")
    assert res2["status"] == "sent"
    assert backend.sends == 2


def test_recipient_gate_not_on_viber(tmp_path):
    backend = FakeBackend()
    backend.not_on_viber = True
    service = Service(backend, tmp_path / "state", send_enabled=True, auto_approve=True)

    with pytest.raises(SafetyError, match="Recipient is not a Viber user"):
        service.open_chat("2025550123")

    res = service.send_message("2025550123", "Should never send")
    assert res["status"] == "blocked"
    assert res["sent"] is False
    assert res["attempted"] is False
    assert res["reason"] == "recipient_not_on_viber"
    assert backend.sends == 0
