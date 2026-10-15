import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend import orchestrator


def response(content="", calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls))])


def tool(name, arguments="{}"):
    return SimpleNamespace(
        id="call-1", function=SimpleNamespace(name=name, arguments=arguments),
        model_dump=lambda: {"id": "call-1", "type": "function", "function": {"name": name, "arguments": arguments}},
    )


class FakeClient:
    def __init__(self, replies):
        self.create = AsyncMock(side_effect=replies)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


def setup(monkeypatch, replies):
    client = FakeClient(replies)
    monkeypatch.setattr(orchestrator, "_client", lambda: client)
    pool = SimpleNamespace(call=AsyncMock(return_value={}), transport="test")
    monkeypatch.setattr(orchestrator, "_ambient_pool", lambda: pool)
    return client, pool


def test_output_cap_is_passed_to_the_provider_and_client_is_closed(monkeypatch):
    client, _ = setup(monkeypatch, [response("A short answer")])
    result = asyncio.run(orchestrator.run([{"role": "user", "content": "Question"}], max_output_tokens=123))
    assert result["reply"] == "A short answer"
    assert client.create.call_args.kwargs["max_completion_tokens"] == 123
    assert client.closed


def test_model_call_budget_is_shared_with_specialists(monkeypatch):
    client, _ = setup(monkeypatch, [response(calls=[tool("consult_data_analyst", '{"question":"Lebanon"}')])])
    with pytest.raises(orchestrator.ChatBudgetExceeded):
        asyncio.run(orchestrator.run([{"role": "user", "content": "Question"}], max_model_calls=1))
    assert client.create.await_count == 1
    assert client.closed


def test_tool_call_budget_includes_lead_and_specialist_tools(monkeypatch):
    client, pool = setup(monkeypatch, [
        response(calls=[tool("consult_data_analyst", '{"question":"Lebanon"}')]),
        response(calls=[tool("data__list_indicators")]),
    ])
    with pytest.raises(orchestrator.ChatBudgetExceeded):
        asyncio.run(orchestrator.run([{"role": "user", "content": "Question"}], max_tool_calls=1))
    assert client.create.await_count == 2
    pool.call.assert_not_awaited()
    assert client.closed
