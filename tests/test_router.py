"""
tests/test_router.py — tests for ToolRegistry and Router.

Router tests mock the PydanticAI Agent — no real API calls.
Settings tests use monkeypatching of os.environ.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tool_registry import ToolRegistry
from core.settings import ConfigError, load_settings


# ── ToolRegistry ──────────────────────────────────────────────────────────────

def test_register_decorator_stores_tool():
    registry = ToolRegistry()

    @registry.register
    async def my_tool(x: str) -> str:
        """Does something."""
        return x

    assert len(registry) == 1
    assert "my_tool" in registry.names()


def test_register_preserves_function():
    registry = ToolRegistry()

    @registry.register
    async def my_tool(x: str) -> str:
        """Does something."""
        return x

    # function still callable directly
    import asyncio
    result = asyncio.run(my_tool("hello"))
    assert result == "hello"


def test_as_pydantic_tools_returns_callables():
    registry = ToolRegistry()

    @registry.register
    async def tool_a(x: str) -> str:
        """Tool A."""
        return x

    @registry.register
    async def tool_b(y: int) -> str:
        """Tool B."""
        return str(y)

    tools = registry.as_pydantic_tools()
    assert len(tools) == 2
    assert all(callable(t) for t in tools)


def test_names_returns_function_names():
    registry = ToolRegistry()

    @registry.register
    async def cv_fetch_jd(url: str) -> str:
        """Fetch JD."""
        return url

    @registry.register
    async def cv_get_tracker() -> str:
        """Get tracker."""
        return ""

    assert registry.names() == ["cv_fetch_jd", "cv_get_tracker"]


def test_empty_registry():
    registry = ToolRegistry()
    assert len(registry) == 0
    assert registry.as_pydantic_tools() == []
    assert registry.names() == []


def test_repr():
    registry = ToolRegistry()

    @registry.register
    async def some_tool() -> str:
        """A tool."""
        return ""

    assert "some_tool" in repr(registry)


# ── Settings ──────────────────────────────────────────────────────────────────

def _env(**kwargs):
    """Build env dict with required vars + overrides."""
    base = {
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "TELEGRAM_BOT_TOKEN": "999:AAA",
        "TELEGRAM_CHAT_ID": "12345",
    }
    base.update(kwargs)
    return base


def test_load_settings_happy_path(monkeypatch):
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LLM_MODEL", raising=False)  # isolate from .env
    s = load_settings()
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.telegram_chat_id == 12345
    assert s.llm_model == "claude-opus-4-5"  # code default when LLM_MODEL unset


def test_load_settings_custom_model(monkeypatch):
    for k, v in _env(LLM_MODEL="claude-haiku-4-5").items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert s.llm_model == "claude-haiku-4-5"


def test_load_settings_missing_api_key(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:AAA")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_settings()


def test_load_settings_missing_multiple(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        load_settings()
    msg = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in msg
    assert "TELEGRAM_BOT_TOKEN" in msg


def test_load_settings_invalid_chat_id(monkeypatch):
    for k, v in _env(TELEGRAM_CHAT_ID="not_a_number").items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ConfigError, match="integer"):
        load_settings()


# ── Router ────────────────────────────────────────────────────────────────────

def _make_mock_deps():
    """Build a minimal mock AgentDeps (no real adapters needed)."""
    from core.deps import AgentDeps
    deps = MagicMock(spec=AgentDeps)
    deps.candidate_name = "Test_Candidate"
    return deps


@pytest.mark.asyncio
async def test_router_handle_returns_string():
    """Router.handle returns agent output as string."""
    from core.router import Router

    registry = ToolRegistry()
    deps = _make_mock_deps()

    fake_result = MagicMock()
    fake_result.output = "Отлично, обрабатываю!"

    with patch("core.router.AnthropicModel"), patch("core.router.AnthropicProvider"):
        with patch("core.router.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=fake_result)
            MockAgent.return_value = mock_agent_instance

            router = Router(api_key="sk-test", model="claude-opus-4-5", registry=registry, deps=deps)
            result = await router.handle("https://djinni.co/jobs/123/")

    assert result == "Отлично, обрабатываю!"


@pytest.mark.asyncio
async def test_router_passes_tools_to_agent():
    """Router constructs Agent with tools from registry."""
    from core.router import Router

    registry = ToolRegistry()
    deps = _make_mock_deps()

    @registry.register
    async def cv_fetch_jd(url: str) -> str:
        """Fetch JD."""
        return "markdown"

    with patch("core.router.AnthropicModel"), patch("core.router.AnthropicProvider"):
        with patch("core.router.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=MagicMock(output="ok"))
            MockAgent.return_value = mock_agent_instance

            Router(api_key="sk-test", model="claude-opus-4-5", registry=registry, deps=deps)

    call_kwargs = MockAgent.call_args.kwargs
    tools_passed = call_kwargs.get("tools", [])
    assert len(tools_passed) == 1
