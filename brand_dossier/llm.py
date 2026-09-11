"""Camada de acesso ao Claude: análise por post (JSON estruturado) e síntese do dossiê (streaming)."""

from __future__ import annotations

import base64
import io
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .config import JPEG_QUALITY, MAX_IMAGE_SIDE, ModelSpec, mock_mode
from .schemas import PostAnalysis, strict_json_schema

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
        }

    @classmethod
    def from_response(cls, usage: Any) -> "Usage":
        if usage is None:
            return cls()
        return cls(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )


@dataclass
class ImagePayload:
    media_type: str
    data_b64: str
    width: int
    height: int


def prepare_image(path: str | Path) -> ImagePayload:
    """Abre, converte para RGB, limita o lado maior e devolve JPEG em base64."""
    img = Image.open(path)
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    scale = MAX_IMAGE_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return ImagePayload("image/jpeg", base64.standard_b64encode(buf.getvalue()).decode("ascii"), *img.size)


def build_user_content(images: list[ImagePayload], user_text: str) -> list[dict[str, Any]]:
    """Blocos de conteúdo: imagens rotuladas por slide (quando há mais de uma) e o texto por último."""
    content: list[dict[str, Any]] = []
    n = len(images)
    for i, img in enumerate(images, start=1):
        if n > 1:
            content.append({"type": "text", "text": f"Slide {i} de {n}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": img.media_type,
                                                      "data": img.data_b64}})
    content.append({"type": "text", "text": user_text})
    return content


def _first_text(content: list[Any]) -> str:
    return "".join(getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text")


class LLMClient:
    def __init__(self, api_key: str | None = None):
        self.mock = mock_mode()
        self._client = None
        if not self.mock:
            import anthropic  # importado aqui para o modo mock funcionar sem rede

            self._anthropic = anthropic
            self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    # --- montagem de parâmetros -------------------------------------------

    def _base_kwargs(self, spec: ModelSpec, effort: str | None, system: str, messages: list[dict],
                     max_tokens: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": spec.id,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if spec.thinking == "adaptive":
            kwargs["thinking"] = {"type": "adaptive"}
        if spec.supports_effort and effort:
            kwargs["output_config"] = {"effort": effort}
        return kwargs

    def _create(self, spec: ModelSpec, kwargs: dict[str, Any]) -> Any:
        """Chama a API. Em modelos com fallback de recusa, tenta o caminho beta e recua para o comum."""
        if spec.use_beta_fallbacks:
            try:
                return self._client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except self._anthropic.BadRequestError:
                pass  # parâmetro não aceito nesta conta ou versão; segue sem fallback
        return self._client.messages.create(**kwargs)

    def _check_stop(self, response: Any) -> None:
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            why = getattr(details, "explanation", None) or "sem detalhe"
            raise LLMError(f"O modelo recusou a requisição: {why}")
        if response.stop_reason == "max_tokens":
            raise LLMError("Resposta truncada por max_tokens. Aumente o limite ou reduza a entrada.")

    # --- estágio 2: análise por post ---------------------------------------

    def analyze_post(self, spec: ModelSpec, effort: str | None, system: str, images: list[ImagePayload],
                     user_text: str) -> tuple[dict[str, Any], Usage]:
        if self.mock:
            return _mock_analysis(user_text), Usage(input_tokens=2500 + 1500 * len(images), output_tokens=900)

        content = build_user_content(images, user_text)
        kwargs = self._base_kwargs(spec, effort, system, [{"role": "user", "content": content}], max_tokens=8000)
        kwargs.setdefault("output_config", {})["format"] = {
            "type": "json_schema",
            "schema": strict_json_schema(PostAnalysis),
        }
        response = self._create(spec, kwargs)
        self._check_stop(response)
        text = _first_text(response.content)
        try:
            parsed = PostAnalysis.model_validate_json(text)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"JSON da análise inválido: {e}\n{text[:500]}") from e
        return parsed.model_dump(), Usage.from_response(response.usage)

    # --- estágio 3: síntese do dossiê --------------------------------------

    def synthesize(self, spec: ModelSpec, effort: str | None, system: str, user_text: str,
                   on_text: Callable[[str], None] | None = None) -> tuple[str, Usage]:
        if self.mock:
            md = _mock_dossier()
            if on_text:
                for chunk in md.split("\n"):
                    on_text(chunk + "\n")
            return md, Usage(input_tokens=40000, output_tokens=6000)

        kwargs = self._base_kwargs(spec, effort, system, [{"role": "user", "content": user_text}], max_tokens=32000)
        if spec.use_beta_fallbacks:
            try:
                return self._stream(self._client.beta.messages, kwargs, on_text,
                                    betas=[FALLBACK_BETA], fallbacks="default")
            except self._anthropic.BadRequestError:
                pass
        return self._stream(self._client.messages, kwargs, on_text)

    def _stream(self, api: Any, kwargs: dict[str, Any], on_text: Callable[[str], None] | None,
                **extra: Any) -> tuple[str, Usage]:
        parts: list[str] = []
        with api.stream(**kwargs, **extra) as stream:
            for text in stream.text_stream:
                parts.append(text)
                if on_text:
                    on_text(text)
            final = stream.get_final_message()
        self._check_stop(final)
        return "".join(parts).strip(), Usage.from_response(final.usage)


def make_client(engine: str, api_key: str | None = None):
    """Devolve o cliente do motor escolhido. Em modo mock, sempre o LLMClient simulado."""
    if mock_mode() or engine == "api":
        return LLMClient(api_key=api_key)
    if engine == "claude_code":
        from .engine_claude_code import ClaudeCodeClient

        return ClaudeCodeClient()
    raise ValueError(f"Motor desconhecido: {engine}")


# ---------------------------------------------------------------------------
# Modo simulado (BRAND_DOSSIER_MOCK=1): testa a interface sem gastar API
# ---------------------------------------------------------------------------

def _mock_analysis(user_text: str) -> dict[str, Any]:
    rnd = random.Random(hash(user_text) % 10_000)
    from . import taxonomies as T

    pick = rnd.choice
    return PostAnalysis.model_validate({
        "resumo": "Post simulado para teste da interface.",
        "visual": {
            "formato": pick(T.VISUAL_FORMATS), "descricao": "Imagem simulada.", "composicao": "Plano médio, produto centralizado.",
            "cores_dominantes": ["verde", "branco"], "texto_na_imagem": pick(T.AMOUNT_LEVELS),
            "texto_na_imagem_transcricao": "", "pessoas_presentes": pick([True, False]), "marca_visivel": True,
            "palavras_de_estilo": ["limpo", "corporativo", "iluminado"], "qualidade_de_producao": "alta",
            "estrutura_dos_slides": "",
        },
        "legenda": {
            "framework": pick(T.COPY_FRAMEWORKS), "tipo_de_gancho": pick(T.HOOK_TYPES), "gancho_texto": "Você já perdeu produção?",
            "tem_cta": True, "tipo_de_cta": pick(T.CTA_TYPES), "cta_texto": "Clique no link na bio",
            "gatilhos": [pick(T.PERSUASION_TRIGGERS)], "figuras_retoricas": ["pergunta retórica"],
            "registro": pick(T.REGISTERS), "voz": pick(T.VOICE_LABELS), "uso_de_emoji": pick(T.AMOUNT_LEVELS),
            "tom": {"formalidade": rnd.randint(3, 7), "profundidade_tecnica": rnd.randint(3, 8), "autoridade": rnd.randint(5, 9),
                    "urgencia": rnd.randint(2, 7), "calor": rnd.randint(4, 8), "humor": rnd.randint(1, 4),
                    "evidencias": ["Você já perdeu produção?", "precisão centimétrica"]},
            "vocabulario_notavel": ["produção", "precisão", "custo"],
        },
        "conteudo": {
            "tema_principal": pick(["eficiência na aplicação", "redução de custo", "tecnologia no campo", "depoimento de cliente"]),
            "temas_secundarios": ["inovação"], "pilar": pick(T.CONTENT_PILLARS), "profundidade": pick(T.CONTENT_DEPTH),
            "tipo_de_valor": pick(T.VALUE_PROPOSITION_TYPES),
            "persona_alvo": {"nome_curto": pick(["Produtor que quer reduzir custo", "Gestor de fazenda tecnológico"]),
                             "descricao": "Produtor rural de médio porte.", "dor": "Aplicação irregular.", "desejo": "Mais produtividade.",
                             "estagio_de_consciencia": pick(T.AWARENESS_STAGES)},
            "mecanismos_de_prova": ["dado percentual"], "produto_ou_servico_citado": "Drone EA-30",
        },
        "coerencia_imagem_legenda": "alta", "padrao_reutilizavel": "Abra com pergunta de dor, apresente número concreto, feche com CTA.",
        "confianca": "media", "observacoes": "",
    }).model_dump()


def _mock_dossier() -> str:
    return "# Dossiê de comunicação: (simulado)\n\n" + "\n\n".join(
        f"## {i}. Seção simulada {i}\nConteúdo de teste. [P1]" for i in range(1, 13)
    ) + "\n\n```markdown\nSystem prompt simulado.\n```\n"
