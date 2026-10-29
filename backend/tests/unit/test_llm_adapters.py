import asyncio
import json

import httpx
import httpx2
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from src.adapters.output.llm.anthropic_adapter import AnthropicLLMAdapter
from src.adapters.output.llm.openai_compat_adapter import (
    OpenAICompatLLMAdapter,
    parse_json_object,
)
from src.domain.exceptions import InvalidLLMOutputException, LLMException

SCHEMA = {"type": "object", "properties": {"clips": {"type": "array"}}, "required": ["clips"]}


@pytest.mark.parametrize(
    "reply",
    [
        '{"clips": []}',
        '```json\n{"clips": []}\n```',
        '<think>{"draft": true} hmm</think>Here you go: {"clips": []} Enjoy!',
    ],
)
def test_parse_json_object_tolerates_wrappers(reply):
    assert parse_json_object(reply) == {"clips": []}


@pytest.mark.parametrize("reply", ["no json here", "{not json}", "[1, 2]"])
def test_parse_json_object_rejects_garbage(reply):
    with pytest.raises(InvalidLLMOutputException):
        parse_json_object(reply)


def openai_adapter(handler):
    client = AsyncOpenAI(
        base_url="http://ollama.test/v1",
        api_key="unused",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return OpenAICompatLLMAdapter(client, "qwen2.5:14b", asyncio.Semaphore(2))


def chat_response(content):
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen2.5:14b",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


async def test_openai_compat_sends_schema_and_parses_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=chat_response('{"clips": [1]}'))

    result = await openai_adapter(handler).complete_json("sys", "usr", SCHEMA)

    assert result == {"clips": [1]}
    assert seen["path"] == "/v1/chat/completions"
    body = seen["body"]
    assert body["model"] == "qwen2.5:14b"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA


async def test_openai_compat_connection_failure_is_an_llm_error():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LLMException, match="LLM request failed"):
        await openai_adapter(handler).complete_json("sys", "usr", SCHEMA)


def anthropic_adapter(handler):
    client = AsyncAnthropic(
        api_key="k",
        base_url="http://claude.test",
        max_retries=0,
        # The Anthropic SDK v2 is built on httpx2, not httpx.
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicLLMAdapter(client, "claude-sonnet-5-5", asyncio.Semaphore(2))


def message_response(content):
    return {
        "id": "m1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


async def test_anthropic_forces_the_result_tool():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json=message_response(
                [{"type": "tool_use", "id": "t1", "name": "submit_result", "input": {"clips": []}}]
            ),
        )

    result = await anthropic_adapter(handler).complete_json("sys", "usr", SCHEMA)

    assert result == {"clips": []}
    body = seen["body"]
    assert body["system"] == "sys"
    assert body["tools"][0]["input_schema"] == SCHEMA
    assert body["tool_choice"] == {"type": "tool", "name": "submit_result"}


async def test_anthropic_without_tool_call_is_invalid_output():
    def handler(request):
        return httpx2.Response(200, json=message_response([{"type": "text", "text": "Sure!"}]))

    with pytest.raises(InvalidLLMOutputException):
        await anthropic_adapter(handler).complete_json("sys", "usr", SCHEMA)
