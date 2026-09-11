"""Motor alternativo: usa o Claude Code instalado na máquina (`claude -p`), com a assinatura do usuário.

Sem chave de API. Cada chamada é um subprocesso em modo não interativo, com entrada e saída em
stream-json, sem ferramentas, sem servidores MCP e com system prompt próprio, para manter o
consumo de tokens no mínimo (cerca de 2 a 3 mil tokens por post além da imagem).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Callable

from .config import ModelSpec
from .llm import ImagePayload, LLMError, Usage, build_user_content
from .schemas import PostAnalysis, strict_json_schema

ANALYSIS_TIMEOUT_S = 600
SYNTHESIS_TIMEOUT_S = 1800


def claude_cli_path() -> str | None:
    return shutil.which("claude")


def _base_cmd(spec: ModelSpec, effort: str | None, system: str) -> list[str]:
    cli = claude_cli_path()
    if not cli:
        raise LLMError("Claude Code não encontrado no PATH. Instale com: npm install -g @anthropic-ai/claude-code")
    cmd = [
        cli, "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--model", spec.id,
        "--system-prompt", system,
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--setting-sources", "",
    ]
    if spec.supports_effort and effort:
        cmd += ["--effort", effort]
    return cmd


def _user_message(images: list[ImagePayload], text: str) -> str:
    content = build_user_content(images, text)
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}}, ensure_ascii=False) + "\n"


def _run(cmd: list[str], stdin_text: str, timeout: int,
         on_text: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Executa o subprocesso, repassa deltas de texto e devolve o evento final de resultado."""
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8")
    result: dict[str, Any] | None = None
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(stdin_text)
        proc.stdin.close()
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "stream_event" and on_text:
                ev = event.get("event", {})
                if ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                    on_text(ev["delta"]["text"])
            elif etype == "result":
                result = event
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise LLMError(f"Claude Code excedeu {timeout}s sem responder.")
    stderr = proc.stderr.read() if proc.stderr else ""
    if result is None:
        raise LLMError(f"Claude Code terminou sem resultado (código {proc.returncode}). {stderr[:500]}")
    if result.get("is_error"):
        msg = result.get("result") or result.get("terminal_reason") or "erro desconhecido"
        if "Not logged in" in str(msg):
            msg = "Claude Code não está logado. Abra um terminal, rode `claude` e faça /login."
        raise LLMError(f"Claude Code retornou erro: {msg}")
    return result


def _usage(result: dict[str, Any]) -> Usage:
    u = result.get("usage", {}) or {}
    return Usage(
        input_tokens=int(u.get("input_tokens", 0) or 0),
        output_tokens=int(u.get("output_tokens", 0) or 0),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens", 0) or 0),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens", 0) or 0),
    )


class ClaudeCodeClient:
    """Mesma interface de LLMClient, mas via `claude -p`."""

    mock = False

    def analyze_post(self, spec: ModelSpec, effort: str | None, system: str, images: list[ImagePayload],
                     user_text: str) -> tuple[dict[str, Any], Usage]:
        cmd = _base_cmd(spec, effort, system) + ["--json-schema", json.dumps(strict_json_schema(PostAnalysis))]
        result = _run(cmd, _user_message(images, user_text), ANALYSIS_TIMEOUT_S)
        data = result.get("structured_output")
        if data is None:
            raw = result.get("result", "")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                raise LLMError(f"Claude Code não devolveu JSON estruturado: {raw[:300]}") from e
        try:
            parsed = PostAnalysis.model_validate(data)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"JSON da análise inválido: {e}") from e
        return parsed.model_dump(), _usage(result)

    def synthesize(self, spec: ModelSpec, effort: str | None, system: str, user_text: str,
                   on_text: Callable[[str], None] | None = None) -> tuple[str, Usage]:
        cmd = _base_cmd(spec, effort, system) + ["--include-partial-messages"]
        result = _run(cmd, _user_message([], user_text), SYNTHESIS_TIMEOUT_S, on_text=on_text)
        text = (result.get("result") or "").strip()
        if not text:
            raise LLMError("Claude Code devolveu dossiê vazio.")
        return text, _usage(result)
