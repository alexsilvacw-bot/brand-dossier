"""Testes de brand_dossier.db: CRUD básico e agregação de análises/dossiês."""

from __future__ import annotations

from brand_dossier import db


def test_crud_marca():
    brand_id = db.create_brand("Marca X", "Resumo", "Produto 1", "Público A", "pt-BR")
    brand = db.get_brand(brand_id)
    assert brand is not None
    assert brand["name"] == "Marca X"
    assert brand["summary"] == "Resumo"

    assert any(b["id"] == brand_id for b in db.list_brands())

    db.update_brand(brand_id, "Marca X Atualizada", "Resumo novo", "Produto 2", "Público B", "en")
    updated = db.get_brand(brand_id)
    assert updated["name"] == "Marca X Atualizada"
    assert updated["language"] == "en"

    db.delete_brand(brand_id)
    assert db.get_brand(brand_id) is None


def test_crud_post():
    brand_id = db.create_brand("Marca Y", "Resumo", "Produto")
    post_id = db.add_post(brand_id, None, "foto.jpg", "Legenda original")

    post = db.get_post(post_id)
    assert post is not None
    assert post["caption"] == "Legenda original"
    assert post["brand_id"] == brand_id

    posts = db.list_posts(brand_id)
    assert [p["id"] for p in posts] == [post_id]

    db.update_post_caption(post_id, "Legenda editada")
    assert db.get_post(post_id)["caption"] == "Legenda editada"

    db.delete_post(post_id)
    assert db.get_post(post_id) is None
    assert db.list_posts(brand_id) == []


def test_latest_analyses_devolve_so_a_mais_recente_por_post():
    brand_id = db.create_brand("Marca Z", "Resumo", "Produto")
    post_id = db.add_post(brand_id, None, "foto.jpg", "Legenda")

    analysis_v1 = {"resumo": "primeira versão"}
    analysis_v2 = {"resumo": "segunda versão"}
    metrics = {"words": 2}

    db.save_analysis(post_id, "claude-sonnet-5", "medium", analysis_v1, metrics,
                     {"input_tokens": 100, "output_tokens": 50}, 0.001)
    db.save_analysis(post_id, "claude-sonnet-5", "medium", analysis_v2, metrics,
                     {"input_tokens": 100, "output_tokens": 50}, 0.001)

    latest = db.latest_analyses(brand_id)
    assert set(latest.keys()) == {post_id}
    assert latest[post_id]["analysis"] == analysis_v2


def test_latest_analyses_ignora_posts_sem_analise():
    brand_id = db.create_brand("Marca W", "Resumo", "Produto")
    post_com_analise = db.add_post(brand_id, None, "a.jpg", "Legenda A")
    db.add_post(brand_id, None, "b.jpg", "Legenda B")  # sem análise

    db.save_analysis(post_com_analise, "claude-sonnet-5", "medium", {"resumo": "ok"}, {"words": 1},
                     {"input_tokens": 10, "output_tokens": 5}, 0.0005)

    latest = db.latest_analyses(brand_id)
    assert set(latest.keys()) == {post_com_analise}


def test_save_dossier_incrementa_version():
    brand_id = db.create_brand("Marca V", "Resumo", "Produto")

    id_v1 = db.save_dossier(brand_id, "claude-opus-5", "high", "claude-sonnet-5", 3,
                           "# Dossiê v1", {"n_posts": 3}, {"input_tokens": 1000, "output_tokens": 500}, 0.05)
    id_v2 = db.save_dossier(brand_id, "claude-opus-5", "high", "claude-sonnet-5", 3,
                           "# Dossiê v2", {"n_posts": 3}, {"input_tokens": 1000, "output_tokens": 500}, 0.05)

    dossiers = db.list_dossiers(brand_id)
    versions = {d["id"]: d["version"] for d in dossiers}
    assert versions[id_v1] == 1
    assert versions[id_v2] == 2

    d2 = db.get_dossier(id_v2)
    assert d2["markdown"] == "# Dossiê v2"
    assert d2["aggregate"] == {"n_posts": 3}


def test_brand_cost_summary_soma_analises_e_dossies():
    brand_id = db.create_brand("Marca U", "Resumo", "Produto")
    post_id = db.add_post(brand_id, None, "a.jpg", "Legenda")
    db.save_analysis(post_id, "claude-sonnet-5", "medium", {"resumo": "ok"}, {"words": 1},
                     {"input_tokens": 10, "output_tokens": 5}, 0.01)
    db.save_dossier(brand_id, "claude-opus-5", "high", "claude-sonnet-5", 1, "# Dossiê", {"n_posts": 1},
                    {"input_tokens": 100, "output_tokens": 50}, 0.02)

    costs = db.brand_cost_summary(brand_id)
    assert costs["analyses_usd"] == 0.01
    assert costs["dossiers_usd"] == 0.02
    assert costs["total_usd"] == 0.03
