"""Swappable LLM provider interface.

DEMO (default)      — no network calls; every response in the app is produced by
                      deterministic rules and labelled as such. No API key needed.
anthropic           — Anthropic Messages API (needs ANTHROPIC_API_KEY; a Claude Pro
                      chat subscription does NOT include API access). The model ID is
                      configurable with NYAYASETU_ANTHROPIC_MODEL (default
                      "claude-sonnet-5-5", a current ID on the official models page,
                      checked 8 Nov 2026).
openai_compatible   — any OpenAI-style /chat/completions endpoint (OpenAI, Groq,
                      Together, a local Ollama server, Gemini's compatible endpoint…).

Notes for the Anthropic provider (from the official Claude Sonnet 5.5 migration guide):
  * sampling parameters (temperature, top_p, top_k) return a 400 error on current
    models, so they are never sent;
  * adaptive thinking is on by default and max_tokens covers thinking plus text, so
    a minimum token budget is enforced;
  * a response can start with thinking blocks, so only blocks of type "text" are read.

Legal retrieval and validation never depend on which provider is used. Every caller
catches provider errors and falls back to the deterministic output, saying so.

Check a configured provider from the command line:
    python -m core.llm_provider
"""
from __future__ import annotations

from dataclasses import dataclass

import config


class LLMUnavailable(RuntimeError):
    pass


class LLMEmptyResponse(RuntimeError):
    """The model returned no text block (e.g. its token budget was spent on thinking)."""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    live: bool = True


class LLMProvider:
    name = "base"
    model = ""
    is_live = False

    def complete(self, system: str, user: str, max_tokens: int = 800) -> LLMResponse:
        raise NotImplementedError

    def label(self) -> str:
        return f"{self.name} · {self.model}" if self.model else self.name


class DemoProvider(LLMProvider):
    """No model at all. Calling complete() is a programming error in demo mode."""

    name = "demo"
    is_live = False

    def __init__(self, reason: str = ""):
        self.reason = reason

    def complete(self, system: str, user: str, max_tokens: int = 800) -> LLMResponse:
        raise LLMUnavailable("Demo mode: no LLM configured")

    def label(self) -> str:
        return "Demo mode (deterministic rules, no AI API)"


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    is_live = True

    def __init__(self, api_key: str, model: str, effort: str = "", min_max_tokens: int = 4096, client=None):
        if not model:
            raise LLMUnavailable("NYAYASETU_ANTHROPIC_MODEL is empty")
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise LLMUnavailable("The 'anthropic' package is not installed (pip install anthropic)") from exc
            client = anthropic.Anthropic(api_key=api_key, timeout=config.LLM_TIMEOUT_SECONDS)
        self._client = client
        self.model = model
        self.effort = effort
        self.min_max_tokens = min_max_tokens

    def _request(self, system: str, user: str, max_tokens: int, effort: str):
        kwargs = {
            "model": self.model,
            "max_tokens": max(max_tokens, self.min_max_tokens),  # covers adaptive thinking + text
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if effort:
            # sent via extra_body so older SDK versions do not reject the field
            kwargs["extra_body"] = {"output_config": {"effort": effort}}
        return self._client.messages.create(**kwargs)

    def complete(self, system: str, user: str, max_tokens: int = 800) -> LLMResponse:
        try:
            msg = self._request(system, user, max_tokens, self.effort)
        except Exception as exc:
            # a model that does not support the effort setting: retry once without it
            detail = str(exc).lower()
            if self.effort and type(exc).__name__ == "BadRequestError" and ("effort" in detail or "output_config" in detail):
                msg = self._request(system, user, max_tokens, "")
            else:
                raise
        text = "".join(getattr(b, "text", "") or "" for b in msg.content if getattr(b, "type", "") == "text")
        if not text.strip():
            raise LLMEmptyResponse(f"No text in response (stop_reason={getattr(msg, 'stop_reason', '?')})")
        return LLMResponse(text=text, provider=self.name, model=self.model)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"
    is_live = True

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float | None = None):
        if not model:
            raise LLMUnavailable("NYAYASETU_OPENAI_MODEL is not set")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature  # only sent when explicitly configured (some models reject it)

    def complete(self, system: str, user: str, max_tokens: int = 800) -> LLMResponse:
        import requests

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        r = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=config.LLM_TIMEOUT_SECONDS)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        if not text.strip():
            raise LLMEmptyResponse("No text in response")
        return LLMResponse(text=text, provider=self.name, model=self.model)


def get_provider() -> LLMProvider:
    """Build the provider from environment variables; fall back to demo mode on any problem."""
    choice = config.LLM_PROVIDER
    try:
        if choice == "anthropic":
            if not config.ANTHROPIC_API_KEY:
                return DemoProvider("NYAYASETU_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set — running in demo mode")
            return AnthropicProvider(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL, config.ANTHROPIC_EFFORT,
                                     config.ANTHROPIC_MIN_MAX_TOKENS)
        if choice in ("openai", "openai_compatible"):
            return OpenAICompatibleProvider(config.OPENAI_BASE_URL, config.OPENAI_API_KEY, config.OPENAI_MODEL,
                                            config.OPENAI_TEMPERATURE)
        if choice not in ("", "demo"):
            return DemoProvider(f"Unknown NYAYASETU_LLM_PROVIDER '{choice}' — running in demo mode")
    except LLMUnavailable as exc:
        return DemoProvider(str(exc) + " — running in demo mode")
    return DemoProvider("")


def check_connection() -> int:
    """Command-line check: shows the configured provider and, if live, sends one tiny request."""
    p = get_provider()
    print("Provider:", p.label())
    if not p.is_live:
        print("Demo mode — no API call needed." + (f" ({p.reason})" if getattr(p, "reason", "") else ""))
        return 0
    try:
        r = p.complete(system="Reply with exactly the word OK.", user="Connection test.", max_tokens=50)
    except Exception as exc:  # report the API error verbatim so the user can fix the key/model
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"OK — live response from {r.provider} / {r.model}: {r.text.strip()[:60]!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(check_connection())
