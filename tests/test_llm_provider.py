"""Checks the optional LLM integration without any API key or network access.

    python tests/test_llm_provider.py

A recording fake client stands in for anthropic.Anthropic, so the test verifies the
exact request NyayaSetu would send, how responses are read, and the fallbacks.
It does NOT prove a live call works — run `python -m core.llm_provider` with a real
key for that.

22 checks are defined. 16 need nothing beyond the core requirements. The last 6 drive
the real `anthropic` SDK (installed by `pip install -r requirements.txt`); if that
package is missing they are reported as NOT RUN — never counted as passed.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core import llm_provider  # noqa: E402

results: list[tuple[str, bool, str]] = []
not_run: list[tuple[str, str]] = []  # checks that could not execute in this environment (never counted as passed)

SDK_CHECKS = [
    "real SDK: POST /v1/messages",
    "real SDK: body has no sampling params",
    "real SDK: output_config.effort in body",
    "real SDK: model/max_tokens in body",
    "real SDK: api key + version headers",
    "real SDK: text parsed after thinking block",
]


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


class BadRequestError(Exception):
    """Same class name as anthropic.BadRequestError, which the provider recognises."""


class FakeMessages:
    def __init__(self, responses):
        self.calls = []
        self.responses = list(responses)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def msg(*blocks, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(**b) for b in blocks], stop_reason=stop)


def fake_client(responses):
    return SimpleNamespace(messages=FakeMessages(responses))


def reload_config(env: dict):
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update({k: v for k, v in env.items() if v is not None})
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
    importlib.reload(config)
    importlib.reload(llm_provider)
    return saved


def restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(config)
    importlib.reload(llm_provider)


# 1. default is demo mode, no key needed
saved = reload_config({"NYAYASETU_LLM_PROVIDER": None, "ANTHROPIC_API_KEY": None})
p = llm_provider.get_provider()
check("default provider is demo", p.name == "demo" and not p.is_live, p.label())
restore(saved)

# 2. anthropic selected without a key -> demo with an explanation
saved = reload_config({"NYAYASETU_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""})
p = llm_provider.get_provider()
check("anthropic without key falls back to demo", p.name == "demo" and "ANTHROPIC_API_KEY" in p.reason, p.reason)
restore(saved)

# 3. model identifier is configurable; default is the documented current ID
saved = reload_config({"NYAYASETU_ANTHROPIC_MODEL": None})
check("default model id", config.ANTHROPIC_MODEL == "claude-sonnet-5-5", config.ANTHROPIC_MODEL)
restore(saved)
saved = reload_config({"NYAYASETU_ANTHROPIC_MODEL": "claude-haiku-5-5"})
check("model id read from NYAYASETU_ANTHROPIC_MODEL", config.ANTHROPIC_MODEL == "claude-haiku-5-5", config.ANTHROPIC_MODEL)
restore(saved)

# 4. request shape: no sampling parameters, thinking-aware token budget, effort via output_config
client = fake_client([msg({"type": "thinking", "thinking": "", "signature": "x"}, {"type": "text", "text": "Hello"})])
prov = llm_provider.AnthropicProvider("test-key", "claude-sonnet-5-5", effort="low", min_max_tokens=4096, client=client)
r = prov.complete(system="S", user="U", max_tokens=400)
call = client.messages.calls[0]
check("no temperature/top_p/top_k sent", not any(k in call for k in ("temperature", "top_p", "top_k")), str(sorted(call)))
check("model sent as configured", call["model"] == "claude-sonnet-5-5", call["model"])
check("max_tokens raised to cover adaptive thinking", call["max_tokens"] == 4096, str(call["max_tokens"]))
check("effort sent as output_config", call.get("extra_body") == {"output_config": {"effort": "low"}}, str(call.get("extra_body")))
check("system + single user message", call["system"] == "S" and call["messages"] == [{"role": "user", "content": "U"}], "")
check("thinking blocks ignored, text read by type", r.text == "Hello" and r.live, repr(r.text))

# 5. a model that rejects the effort setting -> one retry without it
client = fake_client([BadRequestError("Error code: 400 - output_config.effort is not supported for this model"),
                      msg({"type": "text", "text": "OK"})])
prov = llm_provider.AnthropicProvider("k", "some-older-model", effort="low", client=client)
r = prov.complete("S", "U")
check("retries once without effort on a 400 about effort", r.text == "OK" and "extra_body" not in client.messages.calls[1],
      str([sorted(c) for c in client.messages.calls]))

# 6. other API errors are raised (callers then show the rule-based output and say why)
client = fake_client([BadRequestError("Error code: 400 - model: not found")])
prov = llm_provider.AnthropicProvider("k", "claude-does-not-exist", effort="low", client=client)
try:
    prov.complete("S", "U")
    check("unknown model error surfaces to caller", False, "no exception")
except BadRequestError as exc:
    check("unknown model error surfaces to caller", True, str(exc))

# 7. budget spent on thinking -> explicit empty-response error, never an empty 'AI answer'
client = fake_client([msg({"type": "thinking", "thinking": "", "signature": "x"}, stop="max_tokens")])
prov = llm_provider.AnthropicProvider("k", "claude-sonnet-5-5", client=client)
try:
    prov.complete("S", "U")
    check("no-text response raises LLMEmptyResponse", False, "no exception")
except llm_provider.LLMEmptyResponse as exc:
    check("no-text response raises LLMEmptyResponse", True, str(exc))

# 8. the app falls back to rule-based text, labelled, when the live call fails
from datetime import date  # noqa: E402

from core.intake import IntakeEngine, new_state  # noqa: E402
from core.pipeline import run_from_intake  # noqa: E402


class FailingLLM(llm_provider.LLMProvider):
    name, model, is_live = "anthropic", "claude-sonnet-5-5", True

    def complete(self, system, user, max_tokens=800):
        raise BadRequestError("Error code: 400 - simulated failure")


eng = IntakeEngine(new_state("en"), today=date(2026, 11, 7), llm=FailingLLM())
eng.start()
eng.handle_user_message("I bought a mixer grinder for ₹3,000 on ShopNest and it arrived broken.")
res = run_from_intake(eng.state, date(2026, 11, 7), llm=FailingLLM())
s = res["rights"]["summary"]
check("failed live call -> rule-based summary, labelled", s["generated_by"] == "rules" and "unavailable" in s["note"], s["note"])
check("failed extraction recorded, rules kept", any("skipped" in n for n in eng.state["llm_notes"]), str(eng.state["llm_notes"]))
check("drafts are always templates", all(d["generated_by"] == "template" for d in res["documents"].values()),
      str({k: d.get("generated_by") for k, d in res["documents"].items()}))

# 9. the REAL anthropic SDK against a local mock server: verifies the actual HTTP request body and
#    response parsing (thinking block first, then text) without a key or internet access
import json  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

captured: dict = {}


class MockMessagesAPI(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        captured.update(path=self.path, body=json.loads(body), headers={k.lower(): v for k, v in self.headers.items()})
        reply = {"id": "msg_mock", "type": "message", "role": "assistant", "model": captured["body"].get("model"),
                 "content": [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "OK from mock"}],
                 "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 3}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


try:
    import anthropic  # noqa: E402
except ImportError:
    anthropic = None
    not_run.extend((n, "anthropic package not installed") for n in SDK_CHECKS)

if anthropic is not None:
    try:
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockMessagesAPI)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        real = anthropic.Anthropic(api_key="test-key-not-real", base_url=f"http://127.0.0.1:{server.server_port}", max_retries=0)
        prov = llm_provider.AnthropicProvider("test-key-not-real", "claude-sonnet-5-5", effort="low", client=real)
        r = prov.complete("System prompt", "User prompt", max_tokens=400)
        server.shutdown()
        b = captured.get("body", {})
        h = captured.get("headers", {})
        key_sent = h.get("x-api-key") == "test-key-not-real" or h.get("authorization") == "Bearer test-key-not-real"
        check(SDK_CHECKS[0], captured.get("path") == "/v1/messages", captured.get("path", ""))
        check(SDK_CHECKS[1], not ({"temperature", "top_p", "top_k"} & set(b)), str(sorted(b)))
        check(SDK_CHECKS[2], b.get("output_config") == {"effort": "low"}, str(b.get("output_config")))
        check(SDK_CHECKS[3], b.get("model") == "claude-sonnet-5-5" and b.get("max_tokens") == 4096, "")
        check(SDK_CHECKS[4], key_sent and "anthropic-version" in h, "anthropic-version " + h.get("anthropic-version", ""))
        check(SDK_CHECKS[5], r.text == "OK from mock", repr(r.text))
    except Exception as exc:  # the SDK is installed but the run broke: every remaining SDK check is a FAIL
        done = {n for n, _, _ in results}
        for n in SDK_CHECKS:
            if n not in done:
                check(n, False, f"{type(exc).__name__}: {exc}")

print(f"Environment: Python {sys.version.split()[0]} · anthropic SDK "
      f"{anthropic.__version__ if anthropic is not None else 'NOT INSTALLED'}\n")
width = max(len(n) for n in [n for n, _, _ in results] + [n for n, _ in not_run])
for name, ok, detail in results:
    print(f"{'PASS   ' if ok else 'FAIL   '}  {name.ljust(width)}  {detail[:110]}")
for name, why in not_run:
    print(f"NOT RUN  {name.ljust(width)}  {why}")
failed = [n for n, ok, _ in results if not ok]
total = len(results) + len(not_run)
print(f"\n{len(results) - len(failed)}/{len(results)} LLM-integration checks executed and passed"
      + (f"; {len(failed)} FAILED" if failed else "")
      + (f"; {len(not_run)} of {total} NOT RUN (anthropic package not installed — run `pip install -r requirements.txt` "
         f"to execute all {total})" if not_run else f" (all {total} defined checks executed)"))
raise SystemExit(1 if failed else 0)
