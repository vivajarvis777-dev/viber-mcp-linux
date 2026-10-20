"""Контракт send_message: кожна відповідь мусить містити idempotency_key.

Потрібно, щоб n8n міг завжди зв'язати результат із бізнес-подією.
"""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "viber_mcp_service.py"


def _send_message_returns():
    tree = ast.parse(SOURCE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "send_message":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Dict):
                    yield inner
            return
    raise AssertionError("send_message not found")


def test_every_send_response_carries_idempotency_key():
    missing = []
    for ret in _send_message_returns():
        keys = []
        for key in ret.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.append(key.value)
        if "idempotency_key" not in keys:
            missing.append(ret.lineno)
    assert not missing, f"returns without idempotency_key at lines: {missing}"


def test_send_message_exposes_idempotency_key_parameter():
    tree = ast.parse(SOURCE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "send_message":
            names = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
            assert "idempotency_key" in names
            return
    raise AssertionError("send_message not found")
