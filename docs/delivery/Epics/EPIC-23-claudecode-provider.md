# EPIC-23 — Claude Code CLI Provider

**Status:** 🟡 In Progress — Tasks 1–4 done; Flutter Settings (T5) next
**Priority:** P1
**Last updated:** 2026-07-03

---

## Context

Career Agent uses `LLM_PROVIDER=claude_api|ollama_api|claude_cli` (see `core/llm_client.py`). Anthropic API = real money per run. Ollama = free but lower quality. Gap: no way to run full Claude-quality pipeline locally without spending API credits.

Claude Code CLI (`claude` command) is available as subprocess — it uses the Claude Code subscription, not API credits. This enables full-quality pipeline testing at zero marginal cost during Flutter MVP development phase.

Security rule in effect: Anthropic API called only when Flutter MVP is 100% complete. Claude Code provider fills this gap.

---

## Problem

Testing the full pipeline (Phase 1+2+3+3.5+4) on real vacancies requires either:
- Anthropic API spend (~$0.33/vacancy) — blocked until Flutter MVP done
- Ollama — free but output quality too low for real testing

No middle path exists. Can't validate pipeline quality cheaply.

---

## Goal

Add `LLM_PROVIDER=claude_cli` — a third provider that routes LLM calls through the Claude Code CLI subprocess. Same Claude model quality, zero API cost, local-only execution.

---

## User Story

```
As a developer testing the Career Agent pipeline
I want to run full Phase 1–4 analysis using Claude Code CLI
So that I can validate pipeline quality without spending Anthropic API credits
```

---

## Acceptance Criteria

### Given / When / Then

**Given** `LLM_PROVIDER=claude_cli` in `.env`  
**When** any pipeline phase calls `LLMClient.complete()`  
**Then** the request is routed via `subprocess` to `claude -p <prompt> --output-format json`  
**And** the response is parsed and returned in the same format as `ClaudeProvider`

**Given** `ClaudeCodeProvider` in use  
**When** the `claude` CLI is not found in PATH  
**Then** pipeline raises `LLMProviderError` with clear message — no silent fallback

**Given** any pipeline tool (cv_analyze, cv_generate, cv_cover)  
**When** `LLM_PROVIDER=claude_cli`  
**Then** all tools work without code changes — provider is transparent

**Given** prompt caching markers in the prompt  
**When** `ClaudeCodeProvider` processes the request  
**Then** caching markers are stripped silently (CLI does not support caching)

---

## Edge Cases

- `claude` not installed or not in PATH → fail fast with clear error
- Subprocess timeout (long Phase 3.5 run) → configurable timeout, raise on exceed
- CLI output not valid JSON → parse error surfaced, not swallowed
- Rate limit from Claude Code subscription → subprocess returns error, propagate to caller
- Model flag: `--model` passed from `LLM_PROVIDER` config or falls back to `claude-sonnet-4-6`

---

## Out of Scope

- Prompt caching (not supported by CLI)
- Streaming responses
- Extended Thinking via CLI (may not be supported)
- Production use — this provider is for local development/testing only
- `llm_usage` DB cost tracking (cost = $0, but token counts may not be available from CLI)

---

## Notes for Engineering

**Implementation sketch:**

```python
# core/llm_client.py — new provider

class ClaudeCodeProvider(LLMClient):
    """Routes LLM calls via Claude Code CLI subprocess. Dev/testing only."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model

    async def complete(self, system: str, user: str, **kwargs) -> str:
        prompt = f"{system}\n\n{user}"
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--model", self.model,
            "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise LLMProviderError(f"claude CLI error: {stderr.decode()}")
        return stdout.decode()
```

**Provider selection in `core/llm_client.py`:**
```python
match settings.llm_provider:
    case "claude":      return ClaudeProvider(...)
    case "ollama":      return OllamaProvider(...)
    case "claude_cli":  return ClaudeCodeProvider(model=settings.claude_model)
```

**Prompt caching:** `ClaudeProvider` wraps blocks with `cache_control`. `ClaudeCodeProvider` must strip or ignore these markers before passing to CLI — CLI does not understand them.

**Async:** CLI call is blocking I/O — must use `asyncio.create_subprocess_exec`, not `subprocess.run`, to avoid blocking the event loop.

**Token tracking:** CLI does not return token counts in parseable form. `llm_usage` insert should be skipped or record `cost_usd=0`, `input_tokens=None` for claude_cli runs.

---

## Dependencies

- `core/llm_client.py` — add `ClaudeCodeProvider` class
- `core/settings.py` — `LLM_PROVIDER` already supports string values, no schema change needed
- Claude Code CLI installed and authenticated on dev machine
- EPIC-22 Phase C (Flutter MVP) — this provider exists to unblock testing while API spend is frozen

---

## Analytics / Events

- Log provider name in `llm_usage.model` field as `claude_cli/claude-sonnet-4-6`
- No cost tracking (cost = $0 by definition)
- Pipeline phases, latency, output length — still trackable

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | `ClaudeCodeProvider` class in `core/llm_client.py` | ✅ Done 2026-07-03 |
| 2 | Provider wiring in `agent.py` (`LLM_PROVIDER=claude_cli` branch) | ✅ Done 2026-07-03 |
| 3 | Tests — 5 unit tests (mocked subprocess) | ✅ Done 2026-07-03 |
| 4 | `GET /api/config` — expose active provider + model to Flutter | ✅ Done 2026-07-03 |
| 5 | Flutter Settings screen — show active LLM provider | 🟡 Next |

**Activate:** set `LLM_PROVIDER=claude_cli` in `.env`. All pipeline tools work unchanged.

---

## Effort Estimate

| Task | Size |
|------|------|
| `ClaudeCodeProvider` class | S |
| Provider selection wiring | XS |
| Tests (mock subprocess) | S |
| `GET /api/config` endpoint | XS |
| Flutter Settings display | XS |
| **Total** | **~1 day** |
