"""Modelos Pydantic da análise por post e utilitários de JSON Schema para structured outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from . import taxonomies as T

CopyFramework = Literal[tuple(T.COPY_FRAMEWORKS)]  # type: ignore[valid-type]
HookType = Literal[tuple(T.HOOK_TYPES)]  # type: ignore[valid-type]
CtaType = Literal[tuple(T.CTA_TYPES)]  # type: ignore[valid-type]
Trigger = Literal[tuple(T.PERSUASION_TRIGGERS)]  # type: ignore[valid-type]
ValueProp = Literal[tuple(T.VALUE_PROPOSITION_TYPES)]  # type: ignore[valid-type]
Pillar = Literal[tuple(T.CONTENT_PILLARS)]  # type: ignore[valid-type]
Register = Literal[tuple(T.REGISTERS)]  # type: ignore[valid-type]
VoiceLabel = Literal[tuple(T.VOICE_LABELS)]  # type: ignore[valid-type]
Awareness = Literal[tuple(T.AWARENESS_STAGES)]  # type: ignore[valid-type]
VisualFormat = Literal[tuple(T.VISUAL_FORMATS)]  # type: ignore[valid-type]
Depth = Literal[tuple(T.CONTENT_DEPTH)]  # type: ignore[valid-type]
Amount = Literal[tuple(T.AMOUNT_LEVELS)]  # type: ignore[valid-type]
Confidence = Literal[tuple(T.CONFIDENCE_LEVELS)]  # type: ignore[valid-type]


class ToneScores(BaseModel):
    """Seis dimensões de tom, inteiros de 1 a 10."""

    formalidade: int = Field(description="1 = muito informal, 10 = muito formal")
    profundidade_tecnica: int = Field(description="1 = leigo, 10 = especialista")
    autoridade: int = Field(description="1 = humilde/pergunta, 10 = afirma com autoridade")
    urgencia: int = Field(description="1 = sem pressa, 10 = agir agora")
    calor: int = Field(description="1 = frio/distante, 10 = caloroso/próximo")
    humor: int = Field(description="1 = sério, 10 = muito bem-humorado")
    evidencias: list[str] = Field(
        description="2 a 4 citações literais da legenda, cada uma com menos de 14 palavras, que justificam as notas"
    )


class VisualAnalysis(BaseModel):
    formato: VisualFormat
    descricao: str = Field(description="O que aparece na imagem, em 1 a 3 frases objetivas")
    composicao: str = Field(description="Enquadramento, foco, plano, uso de espaço, em 1 frase")
    cores_dominantes: list[str] = Field(description="2 a 5 cores em nome ou hex aproximado")
    texto_na_imagem: Amount
    texto_na_imagem_transcricao: str = Field(description="Texto legível na imagem, transcrito. Vazio se não houver")
    pessoas_presentes: bool
    marca_visivel: bool = Field(description="Logo, produto ou identidade visual claramente presente")
    palavras_de_estilo: list[str] = Field(description="3 a 6 adjetivos de estilo visual, ex: limpo, saturado, rústico, corporativo")
    qualidade_de_producao: Literal["baixa", "media", "alta"]


class CopyAnalysis(BaseModel):
    framework: CopyFramework
    tipo_de_gancho: HookType
    gancho_texto: str = Field(description="Primeira frase ou trecho que funciona como gancho, literal. Vazio se não houver")
    tem_cta: bool
    tipo_de_cta: CtaType
    cta_texto: str = Field(description="Texto literal do CTA. Vazio se não houver")
    gatilhos: list[Trigger] = Field(description="Gatilhos de persuasão presentes. Lista vazia se nenhum")
    figuras_retoricas: list[str] = Field(description="Ex: analogia, repetição, pergunta retórica, hipérbole. Lista vazia se nenhuma")
    registro: Register
    voz: VoiceLabel = Field(description="Rótulo de voz que melhor descreve a legenda")
    uso_de_emoji: Amount
    tom: ToneScores
    vocabulario_notavel: list[str] = Field(description="Palavras ou expressões recorrentes ou marcantes, até 8")


class Persona(BaseModel):
    nome_curto: str = Field(description="Apelido descritivo, ex: 'Produtor rural que quer reduzir custo'")
    descricao: str = Field(description="Quem é, em 1 a 2 frases")
    dor: str = Field(description="Problema que o post endereça para essa pessoa")
    desejo: str = Field(description="Resultado que essa pessoa quer")
    estagio_de_consciencia: Awareness


class ContentAnalysis(BaseModel):
    tema_principal: str = Field(description="Tema em 2 a 5 palavras")
    temas_secundarios: list[str] = Field(description="Até 3 temas secundários")
    pilar: Pillar
    profundidade: Depth = Field(description="superficial = só menciona; medio = explica; profundo = ensina com detalhe ou dado")
    tipo_de_valor: ValueProp
    persona_alvo: Persona
    mecanismos_de_prova: list[str] = Field(description="Dados, depoimentos, certificações, demonstrações. Lista vazia se nenhum")
    produto_ou_servico_citado: str = Field(description="Nome do produto ou serviço em foco. Vazio se nenhum")


class PostAnalysis(BaseModel):
    """Análise completa de um post. Toda afirmação deve ter base na imagem ou na legenda."""

    resumo: str = Field(description="O post em 1 frase")
    visual: VisualAnalysis
    legenda: CopyAnalysis
    conteudo: ContentAnalysis
    coerencia_imagem_legenda: Literal["alta", "media", "baixa"] = Field(
        description="Quanto a imagem e a legenda contam a mesma história"
    )
    padrao_reutilizavel: str = Field(
        description="Como reproduzir este post em outro contexto: estrutura, tom e formato, em 2 a 3 frases. Sem citar a marca"
    )
    confianca: Confidence = Field(description="alta se legenda e imagem são claras; baixa se faltou informação")
    observacoes: str = Field(description="Algo relevante que não coube nos campos. Vazio se nada")


# ---------------------------------------------------------------------------
# JSON Schema para structured outputs
# ---------------------------------------------------------------------------

def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"].split("/")[-1]
            return _inline_refs(defs[ref], defs)
        out = {}
        for k, v in node.items():
            if k == "$defs":
                continue
            out[k] = _inline_refs(v, defs)
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"].keys())
        # Structured outputs não aceita alguns metadados do pydantic
        out.pop("title", None)
        out.pop("default", None)
        return out
    if isinstance(node, list):
        return [_inline_refs(x, defs) for x in node]
    return node


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Schema plano, sem $ref, com additionalProperties=false e todos os campos obrigatórios."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    return _inline_refs(raw, defs)
