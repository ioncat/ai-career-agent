"""
core/llm_client.py — LLM abstraction layer.

ClaudeProvider: Anthropic SDK with prompt caching.
  - PROFILE.md always sent as cache_control=ephemeral system block.
  - Task (phase) system prompt appended as second block, also cache_control=ephemeral
    (phase prompts are static and reused across vacancies).
  - Only the user turn (JD text + prior-phase output) is uncached.

OllamaProvider: local Ollama via httpx POST /api/chat. Switched via LLM_PROVIDER=ollama.

Usage:
    llm = ClaudeProvider(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        model="claude-opus-4-5",
        profile_md=Path("...PROFILE.md").read_text(),
    )
    text = await llm.complete(user="Analyse this JD:", system=phase1_prompt)
"""

import asyncio
import logging
import sys
import time
from typing import Protocol, runtime_checkable

import anthropic
import httpx

from core.network_guard import guard_external

log = logging.getLogger(__name__)

# ── Token pricing (USD per 1M tokens) ────────────────────────────────────────
# Source: https://anthropic.com/pricing (verified 2026-05-30)
# Opus 4.x: $5/$25, Sonnet 4.x: $3/$15, Haiku 4.5: $1/$5
_PRICING: dict[str, dict[str, float]] = {
    # Opus 4 family — $5/$25 input/output
    "claude-opus-4-5":   {"input": 5.0,  "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-opus-4":     {"input": 5.0,  "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    # Sonnet 4 family — $3/$15 input/output
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-sonnet-4-5": {"input": 3.0,  "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-sonnet-4":   {"input": 3.0,  "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    # Haiku 4.5 — $1/$5 input/output
    "claude-haiku-4-5":  {"input": 1.0,  "output": 5.0,  "cache_write": 1.25, "cache_read": 0.10},
    "claude-haiku-3-5":  {"input": 0.8,  "output": 4.0,  "cache_write": 1.00, "cache_read": 0.08},
}
_PRICING_FALLBACK = {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50}


def _normalize_model(model: str) -> str:
    """Strip date suffix from model name for pricing lookup.

    e.g. 'claude-opus-4-5-20251101' → 'claude-opus-4-5'
    """
    import re
    return re.sub(r"-\d{8}$", "", model)


def _calc_cost(model: str, inp: int, out: int, cw: int, cr: int) -> float:
    """Calculate USD cost for a single API call."""
    p = _PRICING.get(_normalize_model(model), _PRICING_FALLBACK)
    return (
        inp * p["input"]
        + out * p["output"]
        + cw * p["cache_write"]
        + cr * p["cache_read"]
    ) / 1_000_000


# ── Exceptions ────────────────────────────────────────────────────────────────


class LLMError(Exception):
    """Base exception for LLM client errors."""


class LLMUnavailableError(LLMError):
    """LLM provider is unreachable or overloaded (connection failure, timeout, quota)."""


# ── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface for an LLM completion provider.

    Implementations: ClaudeProvider, OllamaProvider (stub).
    Injected into router and CV tools — not instantiated directly there.
    """

    async def complete(self, user: str, *, system: str | None = None) -> str:
        """Return LLM text completion.

        Args:
            user:   User-turn message (JD text, task input, etc.).
            system: Optional task-level system prompt appended after PROFILE.md.
                    Changes per call — not cached.

        Returns:
            Plain text response from the model.

        Raises:
            LLMError: API error, network failure, or response parsing failure.
            LLMUnavailableError: Provider is unavailable (stub or quota exceeded).
        """
        ...


# ── ClaudeProvider ────────────────────────────────────────────────────────────


class ClaudeProvider:
    """Anthropic Claude completion provider with prompt caching.

    PROFILE.md is always the first system block and is marked
    cache_control=ephemeral so Anthropic caches it across calls.

    Args:
        api_key:    Anthropic API key (from ANTHROPIC_API_KEY env var).
        model:      Model identifier, e.g. "claude-opus-4-5".
        profile_md: Full text content of PROFILE.md. Sent as cached system block.
        max_tokens: Max tokens for each completion. Default 4096.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        profile_md: str,
        max_tokens: int = 4096,
        testing_mode: bool = False,
        auto_confirm: bool = False,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._profile_md = profile_md
        self._max_tokens = max_tokens
        self._testing_mode = testing_mode
        self._auto_confirm = auto_confirm
        # ── Session token counters (reset on each ClaudeProvider instance) ───
        self._sess_calls = 0
        self._sess_input = 0
        self._sess_output = 0
        self._sess_cache_write = 0
        self._sess_cache_read = 0
        self._sess_cost_usd = 0.0
        self._last_call_usage: dict | None = None

    async def _confirm_call(self, user: str, system: str | None) -> bool:
        """In testing mode: print warning and ask for confirmation.

        Returns True if call should proceed, False to skip.
        Runs input() in executor so it doesn't block the event loop.
        """
        if not self._testing_mode:
            return True

        preview = user[:200].replace("\n", " ")
        sys_preview = (system or "")[:100].replace("\n", " ")
        print(
            f"\n⚠️  [TESTING MODE] About to call Claude API ({self._model})\n"
            f"   system: {sys_preview!r}…\n"
            f"   user:   {preview!r}…\n"
            f"   user_len={len(user)} chars",
            flush=True,
        )
        if self._auto_confirm:
            print("   Auto-confirmed by pipeline orchestrator.", flush=True)
            return True
        answer = await asyncio.get_event_loop().run_in_executor(
            None, lambda: input("   Proceed? [y/N]: ").strip().lower()
        )
        if answer != "y":
            log.info("ClaudeProvider: call skipped by user in testing mode")
            return False
        return True

    async def complete(
        self,
        user: str,
        *,
        system: str | None = None,
        budget_tokens: int | None = None,
    ) -> str:
        """Call Claude with PROFILE.md cached + optional task system prompt.

        Args:
            user:          User-turn message.
            system:        Task-level system prompt (not cached).
            budget_tokens: Enable Extended Thinking with this token budget.
                           When set, max_tokens is automatically raised to
                           budget_tokens + 4096 (API requirement: max_tokens > budget_tokens).
        """
        guard_external("Claude API")
        if not await self._confirm_call(user, system):
            raise LLMError("LLM call cancelled by user (testing mode)")

        system_parts: list[dict] = [
            {
                "type": "text",
                "text": self._profile_md,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if system:
            system_parts.append({
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            })

        # Extended Thinking: max_tokens must exceed budget_tokens (API requirement)
        max_tok = self._max_tokens
        extra: dict = {}
        if budget_tokens:
            max_tok = max(max_tok, budget_tokens + 4096)
            extra["thinking"] = {"type": "enabled", "budget_tokens": budget_tokens}

        # Per-component token estimates (len // 4 ≈ ±10%)
        profile_tokens_est = len(self._profile_md) // 4
        prompt_tokens_est  = len(system) // 4 if system else 0
        user_tokens_est    = len(user) // 4

        log.debug(
            "ClaudeProvider.complete model=%s system_blocks=%d user_len=%d thinking=%s",
            self._model, len(system_parts), len(user), bool(budget_tokens),
        )

        t0 = time.monotonic()
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tok,
                system=system_parts,
                messages=[{"role": "user", "content": user}],
                **extra,
            )
        except anthropic.APIStatusError as exc:
            log.error("Claude API error %d: %s", exc.status_code, exc.message)
            if exc.status_code in (429, 529):
                raise LLMUnavailableError(
                    f"Claude quota/overload (HTTP {exc.status_code}): {exc.message}"
                ) from exc
            raise LLMError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            log.error("Claude connection error: %s", exc)
            raise LLMUnavailableError(f"Claude unreachable: {exc}") from exc

        # ── Token accounting ──────────────────────────────────────────────────
        u = response.usage
        inp = u.input_tokens
        out = u.output_tokens

        # cache_creation: SDK ≥0.40 returns CacheCreation object with per-TTL fields;
        # older SDK returns flat cache_creation_input_tokens int.
        cc = getattr(u, "cache_creation", None)
        if cc is not None:
            cw = (getattr(cc, "ephemeral_5m_input_tokens", 0) or 0) + \
                 (getattr(cc, "ephemeral_1h_input_tokens", 0) or 0)
        else:
            cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        # Thinking tokens estimate: sum thinking block text lengths // 4
        thinking_tokens_est = sum(
            len(getattr(block, "thinking", "") or "") // 4
            for block in response.content
            if block.type == "thinking"
        )

        actual_model = str(getattr(response, "model", None) or self._model)
        cost = _calc_cost(actual_model, inp, out, cw, cr)

        self._sess_calls += 1
        self._sess_input += inp
        self._sess_output += out
        self._sess_cache_write += cw
        self._sess_cache_read += cr
        self._sess_cost_usd += cost
        self._last_call_usage = {
            "model": self._model,
            "profile_tokens": profile_tokens_est,
            "prompt_tokens": prompt_tokens_est,
            "user_tokens": user_tokens_est,
            "input_tokens": inp,
            "output_tokens": out,
            "cache_write_tokens": cw,
            "cache_read_tokens": cr,
            "budget_tokens": budget_tokens or 0,
            "thinking_tokens": thinking_tokens_est,
            "elapsed_ms": elapsed_ms,
            "cost_usd": round(cost, 6),
        }

        log.info(
            "LLM call #%d [%s]: in=%d out=%d cache_write=%d cache_read=%d cost=$%.4f"
            " | session total: calls=%d cost=$%.4f",
            self._sess_calls, actual_model, inp, out, cw, cr, cost,
            self._sess_calls, self._sess_cost_usd,
        )

        # Extract text — skip thinking blocks (present when budget_tokens is set)
        text = next(
            (block.text for block in response.content if block.type == "text"),
            None,
        )
        if text is None:
            raise LLMError("Claude returned no text content")
        log.debug("ClaudeProvider.complete → %d chars", len(text))
        return text

    @property
    def model(self) -> str:
        return self._model

    @property
    def raw_client(self) -> anthropic.AsyncAnthropic:
        """Expose underlying client for PydanticAI router (EPIC-5)."""
        return self._client

    @property
    def session_summary(self) -> dict:
        """Cumulative token usage and cost since this provider was created."""
        return {
            "calls": self._sess_calls,
            "input_tokens": self._sess_input,
            "output_tokens": self._sess_output,
            "cache_write_tokens": self._sess_cache_write,
            "cache_read_tokens": self._sess_cache_read,
            "cost_usd": round(self._sess_cost_usd, 6),
        }

    @property
    def last_call_usage(self) -> dict | None:
        """Usage dict from the most recent complete() call. None if no calls yet."""
        return self._last_call_usage

    def log_session_summary(self) -> None:
        """Log cumulative session cost — call at agent shutdown."""
        s = self.session_summary
        log.info(
            "LLM session summary: calls=%d in=%d out=%d"
            " cache_write=%d cache_read=%d total_cost=$%.4f",
            s["calls"], s["input_tokens"], s["output_tokens"],
            s["cache_write_tokens"], s["cache_read_tokens"], s["cost_usd"],
        )


# ── OllamaProvider ───────────────────────────────────────────────────────────


class OllamaProvider:
    """Local Ollama LLM provider via httpx POST /api/chat.

    Implements the same LLMClient interface as ClaudeProvider.
    PROFILE.md + task system prompt are combined into a single system message
    (Ollama does not support prompt caching).

    Args:
        base_url:   Ollama server base URL, e.g. "http://localhost:11434".
        model:      Model tag, e.g. "qwen2.5:32b" or "llama3.3:70b".
        profile_md: Full text content of PROFILE.md — prepended to every system prompt.
        max_tokens: Max tokens for completion (passed as num_predict to Ollama).
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        profile_md: str,
        max_tokens: int = 4096,
        timeout: int = 600,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._profile_md = profile_md
        self._max_tokens = max_tokens
        read_timeout = None if timeout == 0 else float(timeout)
        self._timeout = httpx.Timeout(timeout=read_timeout, connect=10.0)
        self._last_call_usage: dict | None = None
        self._sess_calls = 0
        self._sess_input = 0
        self._sess_output = 0

    async def complete(self, user: str, *, system: str | None = None, **_kwargs) -> str:
        """Call Ollama /api/chat. system and user mirror ClaudeProvider.complete()."""
        sys_parts = [self._profile_md]
        if system:
            sys_parts.append(system)
        system_content = "\n\n".join(sys_parts)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": self._max_tokens},
        }

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.TimeoutException as exc:
                t_str = "∞" if self._timeout.read is None else f"{int(self._timeout.read)}s"
                raise LLMUnavailableError(
                    f"Ollama request timed out after {t_str} ({self._base_url})"
                ) from exc
            except httpx.RequestError as exc:
                raise LLMUnavailableError(
                    f"Ollama unreachable at {self._base_url}: {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                try:
                    err_msg = exc.response.json().get("error") or exc.response.text[:200]
                except Exception:
                    err_msg = exc.response.text[:200]
                raise LLMError(
                    f"Ollama HTTP {exc.response.status_code}: {err_msg}"
                ) from exc

        elapsed = time.monotonic() - t0
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(f"Ollama returned invalid JSON: {resp.text[:100]}") from exc
        text = (data.get("message") or {}).get("content") or ""
        if not text:
            raise LLMError("Ollama returned empty response")

        done_reason = data.get("done_reason") or data.get("finish_reason") or ""

        # Token counts from Ollama response (0 if model doesn't report them)
        inp = int(data.get("prompt_eval_count") or 0)
        out = int(data.get("eval_count") or 0)
        elapsed_ms = int(elapsed * 1000)

        self._sess_calls += 1
        self._sess_input += inp
        self._sess_output += out
        self._last_call_usage = {
            "model": self._model,
            "profile_tokens": len(self._profile_md) // 4,
            "prompt_tokens": len(system) // 4 if system else 0,
            "user_tokens": len(user) // 4,
            "input_tokens": inp,
            "output_tokens": out,
            "cache_write_tokens": 0,
            "cache_read_tokens": 0,
            "budget_tokens": 0,
            "thinking_tokens": 0,
            "elapsed_ms": elapsed_ms,
            "cost_usd": 0.0,
        }

        log.info(
            "OllamaProvider: model=%s elapsed=%.1fs in=%d out=%d tokens done_reason=%r"
            " | session: calls=%d in=%d out=%d",
            self._model, elapsed, inp, out, done_reason,
            self._sess_calls, self._sess_input, self._sess_output,
        )
        if done_reason == "length":
            raise LLMError(
                f"Ollama truncated output at token limit (model={self._model}, "
                f"num_predict={self._max_tokens}). Raise MAX_TOKENS or shorten input."
            )
        return text

    @property
    def model(self) -> str:
        return self._model

    @property
    def last_call_usage(self) -> dict | None:
        """Usage dict from the most recent complete() call. None if no calls yet."""
        return self._last_call_usage

    def log_session_summary(self) -> None:
        log.info(
            "OllamaProvider session: calls=%d in=%d out=%d tokens cost=$0.00 (model=%s)",
            self._sess_calls, self._sess_input, self._sess_output, self._model,
        )


# ── ClaudeCodeProvider ────────────────────────────────────────────────────────


class ClaudeCodeProvider:
    """LLM provider via Claude Code CLI subprocess. Dev/testing only — $0 cost.

    Routes LLM calls through `claude -p` subprocess using the Claude Code
    subscription quota instead of Anthropic API credits. No prompt caching,
    no streaming, no token counts available from CLI.

    Args:
        profile_md: Full text content of PROFILE.md — prepended to every prompt.
        model:      Model to pass via --model flag. Default: claude-sonnet-4-6.
        timeout:    Subprocess timeout in seconds. Default: 120.
    """

    def __init__(
        self,
        profile_md: str,
        model: str = "claude-sonnet-4-6",
        timeout: int = 120,
    ) -> None:
        self._profile_md = profile_md
        self._model = model
        self._timeout = timeout
        self._sess_calls = 0
        self._last_call_usage: dict | None = None

    async def complete(self, user: str, *, system: str | None = None, **_kwargs) -> str:
        """Call Claude Code CLI subprocess with profile + system + user prompt."""
        parts = [self._profile_md]
        if system:
            parts.append(system)
        parts.append(user)
        prompt = "\n\n---\n\n".join(parts)

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", prompt,
                "--model", self._model,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except FileNotFoundError:
            raise LLMUnavailableError("claude CLI not found in PATH — install Claude Code CLI")
        except asyncio.TimeoutError:
            proc.kill()
            raise LLMUnavailableError(f"claude CLI timed out after {self._timeout}s")

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:300]
            raise LLMError(f"claude CLI error (rc={proc.returncode}): {err}")

        text = stdout.decode(errors="replace").strip()
        if not text:
            raise LLMError("claude CLI returned empty response")

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        self._sess_calls += 1
        self._last_call_usage = {
            "model": f"claudecode/{self._model}",
            "profile_tokens": len(self._profile_md) // 4,
            "prompt_tokens": len(system) // 4 if system else 0,
            "user_tokens": len(user) // 4,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_write_tokens": 0,
            "cache_read_tokens": 0,
            "budget_tokens": 0,
            "thinking_tokens": 0,
            "elapsed_ms": elapsed_ms,
            "cost_usd": 0.0,
        }
        log.info(
            "ClaudeCodeProvider: model=%s elapsed=%dms session_calls=%d",
            self._model, elapsed_ms, self._sess_calls,
        )
        return text

    @property
    def model(self) -> str:
        return self._model

    @property
    def last_call_usage(self) -> dict | None:
        return self._last_call_usage

    def log_session_summary(self) -> None:
        log.info(
            "ClaudeCodeProvider session: calls=%d cost=$0.00 (model=%s)",
            self._sess_calls, self._model,
        )
