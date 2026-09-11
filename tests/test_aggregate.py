"""Testes de brand_dossier.aggregate.aggregate_analyses (sem LLM)."""

from __future__ import annotations

import pytest

from brand_dossier.aggregate import aggregate_analyses
from brand_dossier.llm import _mock_analysis
from brand_dossier.metrics import compute_caption_metrics

CAPTIONS = [
    "Confira nosso produto novo! Link na bio para comprar agora. #promo",
    "Você já perdeu tempo com isso? A gente resolve para você.",
    "Nosso compromisso é com a qualidade desde o primeiro dia.",
]


def _build_items():
    items = []
    for i, caption in enumerate(CAPTIONS, start=1):
        items.append(
            {
                "ref": f"P{i}",
                "caption": caption,
                "metrics": compute_caption_metrics(caption).to_dict(),
                "analysis": _mock_analysis(caption),
            }
        )
    return items


def test_lista_vazia_devolve_apenas_n_posts():
    assert aggregate_analyses([]) == {"n_posts": 0}


def test_agregacao_com_tres_itens():
    items = _build_items()
    agg = aggregate_analyses(items)

    assert agg["n_posts"] == 3

    # A soma das porcentagens dos frameworks (um por post) deve fechar em ~100%.
    soma_frameworks = sum(d["pct"] for d in agg["copy"]["frameworks"])
    assert soma_frameworks == pytest.approx(100.0, abs=1.0)

    # Todas as seções principais devem estar presentes.
    for chave in ("texto", "copy", "conteudo", "visual"):
        assert chave in agg

    # Personas agregadas devem trazer os posts de origem.
    assert agg["conteudo"]["personas"], "esperava ao menos uma persona agregada"
    for persona in agg["conteudo"]["personas"]:
        assert "posts" in persona
        assert isinstance(persona["posts"], list)
        assert persona["posts"], "cada persona deve referenciar ao menos um post"


def test_carrosseis_com_n_images_1_1_4():
    items = _build_items()
    # Dois posts com uma imagem só, um carrossel (P3) com 4 slides.
    items[0]["n_images"] = 1
    items[1]["n_images"] = 1
    items[2]["n_images"] = 4

    agg = aggregate_analyses(items)
    carrosseis = agg["visual"]["carrosseis"]

    assert carrosseis["n"] == 1
    assert carrosseis["pct"] == pytest.approx(33.3)
    assert carrosseis["posts"] == ["P3"]
    assert carrosseis["slides_media_nos_carrosseis"] == 4
    assert carrosseis["slides_max"] == 4
