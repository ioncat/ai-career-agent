"""
tests/test_llm_client.py — contract tests for core/llm_client.py.

No real API calls — Anthropic client fully mocked.
Verifies: cache_control sent, system blocks structure, error mapping, stub behaviour.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from core.llm_client import (
    ClaudeCodeProvider,
    ClaudeProvider,
    LLMClient,
    LLMError,
    LLMUnavailableError,
    OllamaProvider,
)

FAKE_PROFILE = "# PROFILE\nName: Test User\nSkills: Python"
FAKE_API_KEY = "sk-ant-test-0000"
FAKE_MODEL = "claude-opus-4-5"


def _make_provider(**kwargs) -> ClaudeProvider:
    defaults = dict(api_key=FAKE_API_KEY, model=FAKE_MODEL, profile_md=FAKE_PROFILE)
    return ClaudeProvider(**(defaults | kwargs))


def _fake_response(text: str) -> MagicMock:
    """Build a mock anthropic.Message with one text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── Protocol check ────────────────────────────────────────────────────────────

def test_claude_provider_satisfies_protocol():
    provider = _make_provider()
    assert isinstance(provider, LLMClient)


FAKE_OLLAMA_URL = "http://localhost:11434"
FAKE_OLLAMA_MODEL = "qwen2.5:32b"


def _make_ollama(**kwargs) -> OllamaProvider:
    defaults = dict(base_url=FAKE_OLLAMA_URL, model=FAKE_OLLAMA_MODEL, profile_md=FAKE_PROFILE)
    return OllamaProvider(**(defaults | kwargs))


def test_ollama_provider_satisfies_protocol():
    assert isinstance(_make_ollama(), LLMClient)


# ── ClaudeProvider — happy path ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_sends_profile_as_cached_system_block():
    provider = _make_provider()
    fake_resp = _fake_response("Analysis result")

    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_resp)) as mock_create:
        result = await provider.complete("Analyse this JD")

    assert result == "Analysis result"
    call_kwargs = mock_create.call_args.kwargs
    system = call_kwargs["system"]

    # First block: profile with cache_control
    assert system[0]["text"] == FAKE_PROFILE
    assert system[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_complete_appends_task_system_as_second_block():
    provider = _make_provider()
    fake_resp = _fake_response("CV draft")

    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_resp)) as mock_create:
        await provider.complete("Write CV", system="Phase 3 prompt here")

    system = mock_create.call_args.kwargs["system"]
    assert len(system) == 2
    assert system[1]["text"] == "Phase 3 prompt here"
    # Task system block is also cached — phase prompts are static and reused
    assert system[1]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_complete_no_system_kwarg_sends_one_block():
    provider = _make_provider()
    fake_resp = _fake_response("ok")

    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_resp)) as mock_create:
        await provider.complete("Hello")

    system = mock_create.call_args.kwargs["system"]
    assert len(system) == 1


@pytest.mark.asyncio
async def test_complete_passes_model_and_max_tokens():
    provider = _make_provider(max_tokens=2048)
    fake_resp = _fake_response("ok")

    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_resp)) as mock_create:
        await provider.complete("test")

    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == FAKE_MODEL
    assert kwargs["max_tokens"] == 2048


# ── ClaudeProvider — error handling ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_status_error_raises_llm_error():
    provider = _make_provider()
    exc = anthropic.APIStatusError(
        message="bad request",
        response=MagicMock(status_code=400),
        body={},
    )

    with patch.object(provider._client.messages, "create", new=AsyncMock(side_effect=exc)):
        with pytest.raises(LLMError):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_rate_limit_raises_llm_unavailable():
    provider = _make_provider()
    exc = anthropic.APIStatusError(
        message="rate limited",
        response=MagicMock(status_code=429),
        body={},
    )

    with patch.object(provider._client.messages, "create", new=AsyncMock(side_effect=exc)):
        with pytest.raises(LLMUnavailableError):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_connection_error_raises_llm_unavailable():
    provider = _make_provider()
    exc = anthropic.APIConnectionError(request=MagicMock())

    with patch.object(provider._client.messages, "create", new=AsyncMock(side_effect=exc)):
        with pytest.raises(LLMUnavailableError):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_empty_content_raises_llm_error():
    provider = _make_provider()
    fake_resp = MagicMock()
    fake_resp.content = []

    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=fake_resp)):
        with pytest.raises(LLMError):
            await provider.complete("test")


# ── OllamaProvider ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_complete_returns_text():
    provider = _make_ollama()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"message": {"content": "Analysis result"}}
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = mock_client

        result = await provider.complete("Analyse this JD", system="Phase 1 prompt")

    assert result == "Analysis result"
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["model"] == FAKE_OLLAMA_MODEL
    assert payload["stream"] is False
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert FAKE_PROFILE in messages[0]["content"]
    assert "Phase 1 prompt" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Analyse this JD"}


@pytest.mark.asyncio
async def test_ollama_connect_error_raises_unavailable():
    import httpx
    provider = _make_ollama()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(LLMUnavailableError, match="unreachable"):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_ollama_timeout_raises_unavailable():
    import httpx
    provider = _make_ollama()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(LLMUnavailableError, match="timed out after"):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_ollama_model_not_found_raises_llm_error():
    import httpx
    provider = _make_ollama()
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.json.return_value = {"error": "model 'qwen2.5:99b' not found, try pulling it first"}
    fake_resp.text = '{"error": "model not found"}'
    http_exc = httpx.HTTPStatusError("not found", request=MagicMock(), response=fake_resp)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=http_exc)
        mock_client_cls.return_value = mock_client

        with pytest.raises(LLMError, match="not found"):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_ollama_invalid_json_raises_llm_error():
    provider = _make_ollama()
    fake_resp = MagicMock()
    fake_resp.json.side_effect = ValueError("invalid json")
    fake_resp.text = "not json at all"
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(LLMError, match="invalid JSON"):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_ollama_empty_response_raises_llm_error():
    provider = _make_ollama()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"message": {"content": ""}}
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(LLMError, match="empty"):
            await provider.complete("test")


# ── OllamaProvider.last_call_usage ───────────────────────────────────────────


def _make_ollama_response(content: str = "ok", inp: int = 50, out: int = 20) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "message": {"content": content},
        "prompt_eval_count": inp,
        "eval_count": out,
        "done_reason": "stop",
    }
    return resp


def _patch_ollama_client(fake_resp):
    from unittest.mock import patch, AsyncMock
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=fake_resp)
    return patch("httpx.AsyncClient", return_value=mock_client), mock_client


@pytest.mark.asyncio
async def test_ollama_last_call_usage_none_before_first_call():
    provider = _make_ollama()
    assert provider.last_call_usage is None


@pytest.mark.asyncio
async def test_ollama_last_call_usage_populated_after_complete():
    provider = _make_ollama()
    fake_resp = _make_ollama_response(content="result", inp=123, out=45)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_cls.return_value = mock_client

        await provider.complete("user msg", system="sys prompt")

    u = provider.last_call_usage
    assert u is not None
    assert u["model"] == FAKE_OLLAMA_MODEL
    assert u["input_tokens"] == 123
    assert u["output_tokens"] == 45
    assert u["cache_write_tokens"] == 0
    assert u["cache_read_tokens"] == 0
    assert u["cost_usd"] == 0.0
    assert u["elapsed_ms"] >= 0
    assert u["profile_tokens"] == len(FAKE_PROFILE) // 4
    assert u["prompt_tokens"] == len("sys prompt") // 4
    assert u["user_tokens"] == len("user msg") // 4


@pytest.mark.asyncio
async def test_ollama_last_call_usage_zero_tokens_when_not_reported():
    """Models that don't report eval counts → zeros, not crash."""
    provider = _make_ollama()
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"message": {"content": "answer"}}  # no eval counts

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_cls.return_value = mock_client

        await provider.complete("q")

    u = provider.last_call_usage
    assert u is not None
    assert u["input_tokens"] == 0
    assert u["output_tokens"] == 0


@pytest.mark.asyncio
async def test_ollama_last_call_usage_updates_on_second_call():
    provider = _make_ollama()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_client.post = AsyncMock(return_value=_make_ollama_response("first", 10, 5))
        mock_cls.return_value = mock_client
        await provider.complete("q1")
        assert provider.last_call_usage["input_tokens"] == 10

        mock_client.post = AsyncMock(return_value=_make_ollama_response("second", 99, 77))
        await provider.complete("q2")
        assert provider.last_call_usage["input_tokens"] == 99


# ── ClaudeCodeProvider ────────────────────────────────────────────────────────


def _make_proc(stdout: bytes, returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_claudecode_returns_text():
    provider = ClaudeCodeProvider(profile_md=FAKE_PROFILE, model="claude-sonnet-4-6")
    proc = _make_proc(b"Analysis result\n")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await provider.complete("user input", system="sys prompt")
    assert result == "Analysis result"


@pytest.mark.asyncio
async def test_claudecode_no_system():
    provider = ClaudeCodeProvider(profile_md=FAKE_PROFILE)
    proc = _make_proc(b"OK\n")
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        await provider.complete("user only")
    call_args = mock_exec.call_args[0]
    prompt = call_args[2]  # 'claude', '-p', <prompt>
    assert FAKE_PROFILE in prompt
    assert "user only" in prompt


@pytest.mark.asyncio
async def test_claudecode_cli_not_found():
    provider = ClaudeCodeProvider(profile_md=FAKE_PROFILE)
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with pytest.raises(LLMUnavailableError, match="not found in PATH"):
            await provider.complete("x")


@pytest.mark.asyncio
async def test_claudecode_nonzero_returncode():
    provider = ClaudeCodeProvider(profile_md=FAKE_PROFILE)
    proc = _make_proc(b"", returncode=1, stderr=b"some CLI error")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(LLMError, match="CLI error"):
            await provider.complete("x")


@pytest.mark.asyncio
async def test_claudecode_last_call_usage_zero_cost():
    provider = ClaudeCodeProvider(profile_md=FAKE_PROFILE)
    proc = _make_proc(b"result\n")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        await provider.complete("x")
    usage = provider.last_call_usage
    assert usage is not None
    assert usage["cost_usd"] == 0.0
    assert usage["input_tokens"] == 0
    assert usage["model"].startswith("claudecode/")
