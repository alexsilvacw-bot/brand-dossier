"""Configuração: caminhos, registro de modelos e preços."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BRAND_DOSSIER_DATA", PROJECT_ROOT / "data"))
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "brand_dossier.sqlite3"

load_dotenv(PROJECT_ROOT / ".env")


def mock_mode() -> bool:
    return os.environ.get("BRAND_DOSSIER_MOCK", "0") in ("1", "true", "True")


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    input_price: float  # USD por 1M tokens
    output_price: float
    supports_effort: bool
    thinking: str  # "adaptive" | "omit" | "none"
    use_beta_fallbacks: bool = False
    note: str = ""


# IDs exatos da API. Não acrescentar sufixos de data.
MODELS: dict[str, ModelSpec] = {
    "claude-sonnet-5": ModelSpec(
        id="claude-sonnet-5",
        label="Claude Sonnet 5",
        input_price=2.00,
        output_price=10.00,
        supports_effort=True,
        thinking="adaptive",
        note="Bom custo para a análise post a post.",
    ),
    "claude-opus-5": ModelSpec(
        id="claude-opus-5",
        label="Claude Opus 5",
        input_price=5.00,
        output_price=25.00,
        supports_effort=True,
        thinking="adaptive",
        use_beta_fallbacks=True,
        note="Recomendado para a síntese do dossiê.",
    ),
    "claude-fable-5-1": ModelSpec(
        id="claude-fable-5-1",
        label="Claude Fable 5.1",
        input_price=10.00,
        output_price=50.00,
        supports_effort=True,
        thinking="omit",  # thinking sempre ligado; não enviar o parâmetro
        use_beta_fallbacks=True,
        note="Mais capaz e mais caro. Síntese premium.",
    ),
    "claude-haiku-4-5": ModelSpec(
        id="claude-haiku-4-5",
        label="Claude Haiku 4.5",
        input_price=1.00,
        output_price=5.00,
        supports_effort=False,
        thinking="none",
        note="Barato para testar o fluxo.",
    ),
}

# Motores: como o app fala com o Claude.
ENGINES = {
    "claude_code": "Claude Code (usa sua assinatura, sem chave de API)",
    "api": "API Anthropic (paga por uso, precisa de ANTHROPIC_API_KEY)",
}


def default_engine() -> str:
    import shutil

    if os.environ.get("BRAND_DOSSIER_ENGINE") in ENGINES:
        return os.environ["BRAND_DOSSIER_ENGINE"]
    return "claude_code" if shutil.which("claude") else "api"


DEFAULT_ANALYSIS_MODEL = "claude-sonnet-5"
DEFAULT_SYNTHESIS_MODEL = "claude-opus-5"
EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]
DEFAULT_ANALYSIS_EFFORT = "medium"
DEFAULT_SYNTHESIS_EFFORT = "high"

# Redimensionamento das imagens antes do envio (lado maior, em pixels).
MAX_IMAGE_SIDE = 1568
JPEG_QUALITY = 88

# Paralelismo da análise post a post.
ANALYSIS_WORKERS = 4


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int,
                      cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    spec = MODELS.get(model_id)
    if not spec:
        return 0.0
    cost = input_tokens * spec.input_price / 1e6
    cost += output_tokens * spec.output_price / 1e6
    cost += cache_read_tokens * spec.input_price * 0.1 / 1e6
    cost += cache_write_tokens * spec.input_price * 1.25 / 1e6
    return cost
