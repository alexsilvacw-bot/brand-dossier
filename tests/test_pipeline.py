"""Teste de fluxo completo do pipeline em modo simulado (BRAND_DOSSIER_MOCK=1)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from brand_dossier import db, pipeline
from brand_dossier.config import DEFAULT_ANALYSIS_EFFORT, DEFAULT_ANALYSIS_MODEL, DEFAULT_SYNTHESIS_EFFORT, DEFAULT_SYNTHESIS_MODEL


def _png_bytes(mode: str, color) -> bytes:
    img = Image.new(mode, (40, 40), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def brand_with_posts():
    brand_id = db.create_brand(
        name="Marca de Teste",
        summary="Empresa fictícia para testes automatizados.",
        products="Produto A, Produto B",
        audience="Pequenos empresários",
    )

    imagens = [
        _png_bytes("RGB", (255, 0, 0)),
        _png_bytes("RGBA", (0, 255, 0, 128)),
        _png_bytes("RGB", (0, 0, 255)),
    ]
    legendas = [
        "Confira nosso produto novo! Link na bio. #promo",
        "Você já perdeu tempo com isso? A gente resolve para você.",
        "Nosso compromisso é com a qualidade desde o primeiro dia.",
    ]

    post_ids = []
    for i, (img_bytes, caption) in enumerate(zip(imagens, legendas), start=1):
        path = pipeline.store_image(brand_id, f"post{i}.png", img_bytes)
        assert Path(path).exists()
        post_id = db.add_post(brand_id, path, f"post{i}.png", caption)
        post_ids.append(post_id)

    return brand_id, post_ids


def test_fluxo_completo(brand_with_posts):
    brand_id, post_ids = brand_with_posts
    assert len(post_ids) == 3

    # --- estágio 2: análise por post (mock) ---
    results = pipeline.analyze_brand_posts(
        brand_id, DEFAULT_ANALYSIS_MODEL, DEFAULT_ANALYSIS_EFFORT, only_missing=True
    )
    assert len(results) == 3
    assert all(r.ok for r in results)
    assert all(r.cost_usd > 0 for r in results)

    # Segunda chamada com only_missing=True: nada pendente.
    results_again = pipeline.analyze_brand_posts(
        brand_id, DEFAULT_ANALYSIS_MODEL, DEFAULT_ANALYSIS_EFFORT, only_missing=True
    )
    assert results_again == []

    # --- estágio 3: agregação ---
    items = pipeline.collect_analysis_items(brand_id)
    assert [it["ref"] for it in items] == ["P1", "P2", "P3"]

    # --- estágio 3: síntese do dossiê ---
    dossier_id = pipeline.build_dossier(brand_id, DEFAULT_SYNTHESIS_MODEL, DEFAULT_SYNTHESIS_EFFORT)
    dossiers = db.list_dossiers(brand_id)
    assert len(dossiers) == 1
    assert dossiers[0]["version"] == 1
    assert dossiers[0]["id"] == dossier_id

    dossier = db.get_dossier(dossier_id)
    assert dossier["post_count"] == 3
    assert dossier["markdown"]

    # --- exportação ---
    paths = pipeline.export_dossier(dossier_id)
    md_path, json_path = paths["markdown"], paths["json"]
    assert md_path.exists() and md_path.read_text(encoding="utf-8").strip()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["versao"] == 1
    assert len(payload["posts"]) == 3

    # --- exclusão de post remove a imagem ---
    post = db.get_post(post_ids[0])
    image_path = Path(post["image_path"])
    assert image_path.exists()
    db.delete_post(post_ids[0])
    assert not image_path.exists()
    assert db.get_post(post_ids[0]) is None

    # --- custo acumulado da marca ---
    costs = db.brand_cost_summary(brand_id)
    assert costs["total_usd"] > 0
    assert costs["analyses_usd"] > 0
    assert costs["dossiers_usd"] > 0
