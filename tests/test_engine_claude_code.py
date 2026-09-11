"""Testes de brand_dossier.engine_claude_code: motor via `claude -p`, sem chamar o binário real.

O subprocesso é substituído por um Popen falso que devolve, na stdout, as mesmas linhas
JSON (stream-json) que o `claude` de verdade produziria: um evento de sistema, deltas de
texto em stream_event e um evento final de result.
"""

from __future__ import annotations

import json

import pytest

from brand_dossier import engine_claude_code
from brand_dossier.config import MODELS
from brand_dossier.llm import LLMError, _mock_analysis
from brand_dossier.schemas import PostAnalysis


class _FakeStdin:
    def __init__(self) -> None:
        self.written: list[str] = []
        self.closed = False

    def write(self, data: str) -> None:
        self.written.append(data)

    def close(self) -> None:
        self.closed = True


class _FakeStderr:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def _make_fake_popen(lines: list[str], stderr_text: str = "", returncode: int = 0):
    """Devolve uma classe que se comporta como subprocess.Popen, para usar no monkeypatch."""

    class FakePopen:
        instances: list["FakePopen"] = []

        def __init__(self, cmd, stdin=None, stdout=None, stderr=None, text=True, encoding="utf-8"):
            self.cmd = cmd
            self.stdin = _FakeStdin()
            self.stdout = iter(lines)
            self.stderr = _FakeStderr(stderr_text)
            self.returncode = returncode
            FakePopen.instances.append(self)

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            pass

    return FakePopen


def _event_line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False)


@pytest.fixture(autouse=True)
def _fake_cli_path(monkeypatch):
    monkeypatch.setattr(engine_claude_code, "claude_cli_path", lambda: "/fake/claude")


# --- analyze_post ------------------------------------------------------------

def test_analyze_post_usa_structured_output_quando_presente(monkeypatch):
    mock_data = _mock_analysis("x")
    lines = [
        _event_line({"type": "system", "subtype": "init"}),
        _event_line({"type": "stream_event", "event": {"type": "content_block_delta",
                                                        "delta": {"type": "text_delta", "text": "..."}}}),
        _event_line({
            "type": "result", "is_error": False, "structured_output": mock_data,
            "result": json.dumps(mock_data),
            "usage": {"input_tokens": 2, "cache_creation_input_tokens": 2780, "output_tokens": 82},
        }),
    ]
    monkeypatch.setattr(engine_claude_code.subprocess, "Popen", _make_fake_popen(lines))

    client = engine_claude_code.ClaudeCodeClient()
    spec = MODELS["claude-sonnet-5"]
    data, usage = client.analyze_post(spec, "medium", "system", None, "legenda")

    assert data == PostAnalysis.model_validate(mock_data).model_dump()
    assert usage.input_tokens == 2
    assert usage.output_tokens == 82
    assert usage.cache_creation_input_tokens == 2780
    assert usage.cache_read_input_tokens == 0


def test_analyze_post_cai_para_json_loads_do_result_quando_sem_structured_output(monkeypatch):
    mock_data = _mock_analysis("y")
    lines = [
        _event_line({"type": "system", "subtype": "init"}),
        _event_line({
            "type": "result", "is_error": False, "structured_output": None,
            "result": json.dumps(mock_data),
            "usage": {"input_tokens": 2, "cache_creation_input_tokens": 2780, "output_tokens": 82},
        }),
    ]
    monkeypatch.setattr(engine_claude_code.subprocess, "Popen", _make_fake_popen(lines))

    client = engine_claude_code.ClaudeCodeClient()
    spec = MODELS["claude-sonnet-5"]
    data, usage = client.analyze_post(spec, "medium", "system", None, "legenda")

    assert data == PostAnalysis.model_validate(mock_data).model_dump()


def test_analyze_post_levanta_llmerror_quando_nao_logado(monkeypatch):
    lines = [
        _event_line({"type": "system", "subtype": "init"}),
        _event_line({"type": "result", "is_error": True, "result": "Not logged in. Please run `claude login`."}),
    ]
    monkeypatch.setattr(engine_claude_code.subprocess, "Popen", _make_fake_popen(lines))

    client = engine_claude_code.ClaudeCodeClient()
    spec = MODELS["claude-sonnet-5"]
    with pytest.raises(LLMError) as excinfo:
        client.analyze_post(spec, "medium", "system", None, "legenda")

    assert "/login" in str(excinfo.value)


# --- synthesize ---------------------------------------------------------------

def test_synthesize_concatena_deltas_e_devolve_texto_do_result(monkeypatch):
    lines = [
        _event_line({"type": "system", "subtype": "init"}),
        _event_line({"type": "stream_event", "event": {"type": "content_block_delta",
                                                        "delta": {"type": "text_delta", "text": "Ola"}}}),
        _event_line({"type": "stream_event", "event": {"type": "content_block_delta",
                                                        "delta": {"type": "text_delta", "text": " mundo"}}}),
        _event_line({
            "type": "result", "is_error": False, "result": "  Ola mundo  \n",
            "usage": {"input_tokens": 2, "cache_creation_input_tokens": 2780, "output_tokens": 82},
        }),
    ]
    monkeypatch.setattr(engine_claude_code.subprocess, "Popen", _make_fake_popen(lines))

    client = engine_claude_code.ClaudeCodeClient()
    spec = MODELS["claude-opus-5"]
    received: list[str] = []
    text, usage = client.synthesize(spec, "high", "system", "texto do usuario", on_text=received.append)

    assert "".join(received) == "Ola mundo"
    assert text == "Ola mundo"
    assert usage.output_tokens == 82


# --- _base_cmd -----------------------------------------------------------------

def test_base_cmd_inclui_effort_so_quando_spec_suporta():
    cmd_com_effort = engine_claude_code._base_cmd(MODELS["claude-sonnet-5"], "high", "system")
    cmd_sem_effort = engine_claude_code._base_cmd(MODELS["claude-haiku-4-5"], "high", "system")

    assert "--effort" in cmd_com_effort
    assert cmd_com_effort[cmd_com_effort.index("--effort") + 1] == "high"
    assert "--effort" not in cmd_sem_effort

    for cmd in (cmd_com_effort, cmd_sem_effort):
        assert "--tools" in cmd
        assert cmd[cmd.index("--tools") + 1] == ""
        assert "--strict-mcp-config" in cmd
        assert "--bare" not in cmd


def test_base_cmd_levanta_llmerror_quando_claude_nao_encontrado(monkeypatch):
    monkeypatch.setattr(engine_claude_code, "claude_cli_path", lambda: None)

    with pytest.raises(LLMError):
        engine_claude_code._base_cmd(MODELS["claude-sonnet-5"], "high", "system")
