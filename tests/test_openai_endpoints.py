"""End-to-end tests for the OpenAI-compatible code paths in AITranslator.

Covers each provider that flows through ``client.chat.completions.create``:
  * OpenAI GPT
  * OpenRouter
  * Custom (OpenAI-Compatible)
  * Local Models (LM Studio)

Also covers the new param-swap behaviour for reasoning models:
  * ``max_tokens`` → ``max_completion_tokens`` retry on 400
  * ``temperature`` dropped on 400
  * Pre-emptive detection from model name prefix (o1, o3, o4, gpt-5)
"""
from __future__ import annotations

import pytest

from ai_translator import AITranslator, _is_reasoning_model


# ---------- model detection ----------------------------------------------

@pytest.mark.parametrize(
    "name",
    ["o1", "o1-preview", "o1-mini", "o3", "o3-mini", "o4-mini", "gpt-5", "GPT-5", "o1-2024-12-17"],
)
def test_is_reasoning_model_positive(name):
    assert _is_reasoning_model(name) is True


@pytest.mark.parametrize(
    "name",
    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "claude-3-haiku", "llama-3-8b", "", None],
)
def test_is_reasoning_model_negative(name):
    assert _is_reasoning_model(name) is False


# ---------- programmable fake client -------------------------------------

class _FakeMsg:
    def __init__(self, content): self.content = content


class _FakeChoice:
    def __init__(self, content): self.message = _FakeMsg(content)


class _FakeUsage:
    def __init__(self, p=10, c=20):
        self.prompt_tokens = p
        self.completion_tokens = c


class _FakeResp:
    def __init__(self, content="ok"):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class ProgrammableClient:
    """Fake openai.OpenAI() whose ``create`` either succeeds or raises a
    canned error based on the kwargs it receives."""

    def __init__(self, *, api_key=None, base_url=None, reject=None, content="ok"):
        self.api_key = api_key
        self.base_url = base_url
        self.calls = []
        self._reject = reject or set()
        self._content = content
        outer = self

        class _Completions:
            def create(self, **kwargs):  # noqa: D401 - mirrors openai shape
                outer.calls.append(kwargs)
                # Reject calls that contain a forbidden parameter
                if "max_tokens" in outer._reject and "max_tokens" in kwargs:
                    raise RuntimeError(
                        "Error code: 400 - {'error': {'message': "
                        "\"Unsupported parameter: 'max_tokens' is not supported "
                        "with this model. Use 'max_completion_tokens' instead.\", "
                        "'type': 'invalid_request_error', 'param': 'max_tokens', "
                        "'code': 'unsupported_parameter'}}"
                    )
                if "temperature" in outer._reject and "temperature" in kwargs:
                    raise RuntimeError(
                        "Error code: 400 - {'error': {'message': "
                        "\"Unsupported value: 'temperature' does not support 0.1 "
                        "with this model. Only the default (1) value is supported.\", "
                        "'type': 'invalid_request_error', 'param': 'temperature', "
                        "'code': 'unsupported_value'}}"
                    )
                return _FakeResp(outer._content)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


@pytest.fixture
def install_programmable(monkeypatch):
    """Returns a function that patches openai.OpenAI to construct a
    ProgrammableClient with caller-supplied options."""
    constructed: list[ProgrammableClient] = []

    def _install(reject=None, content="ok"):
        def _factory(api_key=None, base_url=None, **_kw):
            c = ProgrammableClient(
                api_key=api_key, base_url=base_url, reject=reject, content=content,
            )
            constructed.append(c)
            return c

        import openai
        monkeypatch.setattr(openai, "OpenAI", _factory)
        return constructed

    return _install


# ---------- OpenAI GPT ----------------------------------------------------

def test_openai_gpt_endpoint_never_sends_max_tokens(install_programmable):
    """max_tokens / max_completion_tokens are blockers on reasoning models
    (rejected outright or cause truncated JSON). The translator must never
    send either parameter to OpenAI-compatible endpoints."""
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini", temperature=0.5)
    t._initialize_client()
    text, usage = t._execute_prompt_with_usage("sys", "user")
    call = clients[0].calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert "max_tokens" not in call
    assert "max_completion_tokens" not in call
    assert call["temperature"] == 0.5
    assert text == "ok"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 20}


def test_openai_gpt_reasoning_models_omit_max_tokens_and_temperature(install_programmable):
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-5")
    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    call = clients[0].calls[0]
    assert "max_tokens" not in call
    assert "max_completion_tokens" not in call
    # Reasoning models also reject custom temperature pre-emptively.
    assert "temperature" not in call


def test_openai_gpt_drops_temperature_on_400(install_programmable):
    clients = install_programmable(reject={"temperature"})
    t = AITranslator("OpenAI GPT", "sk-x", "future-reasoner-1", temperature=0.7)
    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    # First call had temperature, second call dropped it.
    assert "temperature" in clients[0].calls[0]
    assert "temperature" not in clients[0].calls[1]
    # Decision is sticky.
    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    assert "temperature" not in clients[0].calls[2]


# ---------- truncation detection -----------------------------------------

class _TruncatedResp:
    class _Msg:
        content = '{"translated_texts": ["...'  # deliberately mid-string
    class _Choice:
        def __init__(self, reason):
            self.message = _TruncatedResp._Msg()
            self.finish_reason = reason
    class _Usage:
        prompt_tokens = 10
        completion_tokens = 8192

    def __init__(self, reason="length"):
        self.choices = [_TruncatedResp._Choice(reason)]
        self.usage = _TruncatedResp._Usage()

    def model_dump_json(self):
        return '{"finish_reason":"' + self.choices[0].finish_reason + '"}'


@pytest.mark.parametrize("reason", ["length", "MAX_TOKENS", "max_tokens"])
def test_truncation_raises_clear_error(install_programmable, monkeypatch, reason):
    """When finish_reason indicates truncation, we must raise a clear
    error instead of returning half-written JSON to the parser."""
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr(
        clients[0].chat.completions, "create",
        lambda **_kw: _TruncatedResp(reason),
    )
    with pytest.raises(ValueError, match="truncated"):
        t._execute_prompt_with_usage("sys", "user")


def test_normal_finish_reason_does_not_raise(install_programmable, monkeypatch):
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr(
        clients[0].chat.completions, "create",
        lambda **_kw: _TruncatedResp("stop"),
    )
    # Must NOT raise — stop is a normal successful completion.
    text, _ = t._execute_prompt_with_usage("sys", "user")
    assert "translated_texts" in text


def test_missing_finish_reason_does_not_raise(install_programmable):
    """The default FakeOpenAIResponse has no finish_reason — that must be
    treated as 'unknown' and not trigger the truncation error."""
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    text, _ = t._execute_prompt_with_usage("sys", "user")
    assert text == "ok"


# ---------- raw response capture -----------------------------------------

def test_raw_response_logged_on_success(install_programmable, monkeypatch):
    clients = install_programmable()
    captured: list[str] = []
    monkeypatch.setattr(
        "ai_translator._log_raw_response",
        lambda tag, body, **_kw: captured.append((tag, body)),
    )
    # Make the fake response's model_dump_json() return something specific
    # so we can assert it reaches the logger.

    class _R:
        class _Choice:
            message = type("M", (), {"content": "hi"})()
        choices = [_Choice()]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2})()
        @staticmethod
        def model_dump_json():
            return '{"id":"resp-1","choices":[{"message":{"content":"hi"}}]}'

    def _fake_create(**_kw):
        return _R()

    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr(clients[0].chat.completions, "create", _fake_create)
    t._execute_prompt_with_usage("sys", "user")

    assert captured, "raw response was never logged"
    tag, body = captured[0]
    assert tag.startswith("OK ")
    assert "gpt-4o-mini" in tag
    assert '"resp-1"' in body


def test_raw_response_logged_on_failure(install_programmable, monkeypatch):
    clients = install_programmable()
    captured: list[str] = []
    monkeypatch.setattr(
        "ai_translator._log_raw_response",
        lambda tag, body, **_kw: captured.append((tag, body)),
    )
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)

    class _FakeHttpResp:
        text = "<html>Bad Gateway</html>"

    err = RuntimeError("Error code: 502 - bad gateway")
    err.response = _FakeHttpResp()

    def _always_502(**_kw):
        raise err

    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr(clients[0].chat.completions, "create", _always_502)

    with pytest.raises(RuntimeError):
        t._execute_prompt_with_usage("sys", "user")

    # Expect one ERR entry from the retry attempt (transient) plus one from
    # the final surrender. At minimum the body we attached must appear.
    assert any(tag.startswith("ERR ") for tag, _ in captured)
    assert any("Bad Gateway" in body for _, body in captured)


def test_extract_error_body_prefers_response_text():
    from ai_translator import _extract_error_body

    class _Resp:
        text = "server-body"

    err = RuntimeError("boom")
    err.response = _Resp()
    assert _extract_error_body(err) == "server-body"


def test_extract_error_body_falls_back_to_str():
    from ai_translator import _extract_error_body
    err = RuntimeError("plain message")
    assert _extract_error_body(err) == "plain message"


def test_openai_retries_once_on_transient_jsondecode_error(
    install_programmable, monkeypatch
):
    """Malformed JSON bodies from the server (``Expecting value: ...``)
    should trigger a single retry with a short backoff."""
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()

    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)

    call_count = {"n": 0}
    real_create = clients[0].chat.completions.create

    def _flaky_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError("Expecting value: line 553 column 1 (char 3036)")
        return real_create(**kwargs)

    monkeypatch.setattr(clients[0].chat.completions, "create", _flaky_create)

    text, _ = t._execute_prompt_with_usage("sys", "user")
    assert text == "ok"
    assert call_count["n"] == 2  # one failure, one successful retry


def test_openai_retries_once_on_5xx(install_programmable, monkeypatch):
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)

    call_count = {"n": 0}
    real_create = clients[0].chat.completions.create

    def _flaky_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Error code: 503 - service unavailable")
        return real_create(**kwargs)

    monkeypatch.setattr(clients[0].chat.completions, "create", _flaky_create)
    text, _ = t._execute_prompt_with_usage("sys", "user")
    assert text == "ok"
    assert call_count["n"] == 2


def test_openai_does_not_retry_fatal_errors(install_programmable, monkeypatch):
    """Authentication, quota, and context-length errors are permanent —
    we must surface them immediately without wasting a retry."""
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)

    call_count = {"n": 0}

    def _bad_create(**_kw):
        call_count["n"] += 1
        raise RuntimeError("Error code: 401 - invalid_api_key")

    monkeypatch.setattr(clients[0].chat.completions, "create", _bad_create)

    with pytest.raises(RuntimeError, match="invalid_api_key"):
        t._execute_prompt_with_usage("sys", "user")
    assert call_count["n"] == 1  # no retry attempted


def test_openai_transient_retry_is_one_shot(install_programmable, monkeypatch):
    """Two transient failures in a row should surface the second one
    rather than spin indefinitely."""
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)

    call_count = {"n": 0}

    def _always_flaky(**_kw):
        call_count["n"] += 1
        raise ValueError(f"Expecting value: line {call_count['n']} column 1 (char 3036)")

    monkeypatch.setattr(clients[0].chat.completions, "create", _always_flaky)

    with pytest.raises(ValueError, match="Expecting value"):
        t._execute_prompt_with_usage("sys", "user")
    assert call_count["n"] == 2  # original + single retry, then give up


def test_openai_gpt_unrelated_400_propagates(install_programmable, monkeypatch):
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    t._initialize_client()  # binds self._client to clients[0]

    def _bad_create(**_kw):
        raise RuntimeError(
            "Error code: 400 - {'error': {'message': 'context_length_exceeded'}}"
        )

    monkeypatch.setattr(clients[0].chat.completions, "create", _bad_create)

    with pytest.raises(RuntimeError, match="context_length_exceeded"):
        t._execute_prompt_with_usage("sys", "user")


# ---------- OpenRouter ----------------------------------------------------

def test_openrouter_endpoint_uses_correct_base_url(install_programmable):
    clients = install_programmable()
    t = AITranslator("OpenRouter", "sk-or", "anthropic/claude-3-haiku")
    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    assert clients[0].base_url == "https://openrouter.ai/api/v1"
    assert clients[0].api_key == "sk-or"
    assert clients[0].calls[0]["model"] == "anthropic/claude-3-haiku"


# ---------- Custom (OpenAI-Compatible) -----------------------------------

def test_custom_openai_endpoint_uses_supplied_base_url(install_programmable):
    clients = install_programmable()
    t = AITranslator(
        "Custom (OpenAI-Compatible)", "k", "llama-3",
        extra_settings={"base_url": "http://localhost:9000/v1"},
    )
    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    assert clients[0].base_url == "http://localhost:9000/v1"


def test_custom_openai_substitutes_blank_api_key(install_programmable):
    clients = install_programmable()
    t = AITranslator(
        "Custom (OpenAI-Compatible)", "", "llama-3",
        extra_settings={"base_url": "http://localhost:8080/v1"},
    )
    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    assert clients[0].api_key == "not-needed"


# ---------- Local Models (LM Studio) -------------------------------------

def test_local_models_lm_studio_uses_chat_completions(install_programmable, monkeypatch):
    clients = install_programmable()

    # The Llama.cpp branch hits LocalModelManager; the LM Studio branch
    # uses the OpenAI-compatible client we patched. We force the LM Studio
    # branch and short-circuit _create_local_client to return our fake.
    t = AITranslator("Local Models", None, "local-x", local_backend="LM Studio")

    def _fake_local(self, base_url="http://localhost:1234/v1"):
        # Fall through to the patched openai.OpenAI()
        import openai
        return openai.OpenAI(api_key=None, base_url=base_url)

    monkeypatch.setattr(AITranslator, "_create_local_client", _fake_local)

    t._initialize_client()
    t._execute_prompt_with_usage("sys", "user")
    assert clients[0].calls[0]["model"] == "local-x"


# ---------- Local Models (Llama.cpp) -------------------------------------

def test_local_models_llamacpp_omits_max_tokens(monkeypatch):
    """The Llama.cpp backend routes through LocalModelManager. Even there
    we must not pass max_tokens — the server's default is correct."""
    t = AITranslator("Local Models", None, "local-x", local_backend="Llama.cpp",
                     temperature=0.3)
    t._client_initialized = True  # bypass server-start side effects

    captured = {}

    def _fake_create(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }

    monkeypatch.setattr(t.local_model_manager, "create_chat_completion", _fake_create)
    t._execute_prompt_with_usage("sys", "user")
    assert "max_tokens" not in captured["kwargs"]
    assert captured["kwargs"].get("temperature") == 0.3


# ---------- _execute_single_prompt parity --------------------------------

def test_single_prompt_path_also_omits_max_tokens(install_programmable):
    clients = install_programmable()
    t = AITranslator("OpenAI GPT", "sk-x", "gpt-4o-mini")
    out, _ = t._execute_single_prompt("hi")
    assert out == "ok"
    assert "max_tokens" not in clients[0].calls[0]
    assert "max_completion_tokens" not in clients[0].calls[0]


def test_single_prompt_path_drops_temperature_on_400(install_programmable):
    clients = install_programmable(reject={"temperature"})
    t = AITranslator("OpenAI GPT", "sk-x", "future-reasoner-1", temperature=0.7)
    out, _ = t._execute_single_prompt("hi")
    assert out == "ok"
    assert "temperature" in clients[0].calls[0]
    assert "temperature" not in clients[0].calls[1]
