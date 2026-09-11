"""Orquestração: métricas -> análise por post em paralelo -> agregação -> síntese do dossiê."""

from __future__ import annotations

import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import db
from .aggregate import aggregate_analyses
from .config import ANALYSIS_WORKERS, DATA_DIR, IMAGES_DIR, MODELS, estimate_cost_usd
from .llm import LLMError, make_client, prepare_image
from .metrics import compute_caption_metrics
from .prompts import analysis_system_prompt, analysis_user_text, synthesis_system_prompt, synthesis_user_prompt

EXPORTS_DIR = DATA_DIR / "exports"


# --- posts ------------------------------------------------------------------

def store_image(brand_id: int, filename: str, data: bytes) -> str:
    """Salva a imagem enviada em data/images/<brand_id>/ e devolve o caminho."""
    folder = IMAGES_DIR / str(brand_id)
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower() or ".jpg"
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    return str(path)


# --- estágio 2 --------------------------------------------------------------

@dataclass
class PostResult:
    post_id: int
    ok: bool
    error: str = ""
    cost_usd: float = 0.0


def _post_ref(index: int) -> str:
    return f"P{index}"


def analyze_brand_posts(brand_id: int, model_id: str, effort: str | None, only_missing: bool = True,
                        api_key: str | None = None, progress: Callable[[int, int, PostResult], None] | None = None,
                        workers: int = ANALYSIS_WORKERS, engine: str = "api") -> list[PostResult]:
    brand = db.get_brand(brand_id)
    if not brand:
        raise ValueError("Marca não encontrada")
    spec = MODELS[model_id]
    posts = db.list_posts(brand_id)
    existing = db.latest_analyses(brand_id) if only_missing else {}
    todo = [(i + 1, p) for i, p in enumerate(posts) if p["id"] not in existing]
    if not todo:
        return []

    client = make_client(engine, api_key=api_key)
    system = analysis_system_prompt(brand)

    def work(index: int, post: dict[str, Any]) -> PostResult:
        try:
            metrics = compute_caption_metrics(post.get("caption", "")).to_dict()
            image = prepare_image(post["image_path"]) if post.get("image_path") else None
            user_text = analysis_user_text(_post_ref(index), post.get("caption", ""), metrics)
            analysis, usage = client.analyze_post(spec, effort, system, image, user_text)
            u = usage.to_dict()
            cost = estimate_cost_usd(model_id, u["input_tokens"], u["output_tokens"],
                                     u["cache_read_input_tokens"], u["cache_creation_input_tokens"])
            db.save_analysis(post["id"], model_id, effort, analysis, metrics, u, cost)
            return PostResult(post["id"], True, cost_usd=cost)
        except LLMError as e:
            return PostResult(post["id"], False, str(e))
        except Exception as e:  # noqa: BLE001
            return PostResult(post["id"], False, f"{type(e).__name__}: {e}")

    results: list[PostResult] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(work, i, p): p["id"] for i, p in todo}
        for n, fut in enumerate(as_completed(futures), start=1):
            res = fut.result()
            results.append(res)
            if progress:
                progress(n, len(todo), res)
    results.sort(key=lambda r: r.post_id)
    return results


# --- estágio 3 --------------------------------------------------------------

def collect_analysis_items(brand_id: int) -> list[dict[str, Any]]:
    """Junta post, métricas e análise mais recente, com referência [Pn] estável pela ordem dos posts."""
    posts = db.list_posts(brand_id)
    latest = db.latest_analyses(brand_id)
    items = []
    for i, p in enumerate(posts, start=1):
        a = latest.get(p["id"])
        if not a:
            continue
        items.append({
            "ref": _post_ref(i), "post_id": p["id"], "caption": p.get("caption", ""),
            "image_path": p.get("image_path"), "metrics": a["metrics"], "analysis": a["analysis"],
            "analysis_model": a["model"],
        })
    return items


def build_dossier(brand_id: int, model_id: str, effort: str | None, api_key: str | None = None,
                  on_text: Callable[[str], None] | None = None, engine: str = "api") -> int:
    brand = db.get_brand(brand_id)
    if not brand:
        raise ValueError("Marca não encontrada")
    items = collect_analysis_items(brand_id)
    if not items:
        raise ValueError("Nenhum post analisado. Rode a análise antes de gerar o dossiê.")

    spec = MODELS[model_id]
    aggregate = aggregate_analyses(items)
    analysis_models = sorted({it["analysis_model"] for it in items})
    models_used = {"analise_por_post": ", ".join(analysis_models), "sintese": model_id}

    client = make_client(engine, api_key=api_key)
    markdown, usage = client.synthesize(
        spec, effort, synthesis_system_prompt(brand.get("language", "pt-BR")),
        synthesis_user_prompt(brand, aggregate, items, models_used), on_text=on_text,
    )
    u = usage.to_dict()
    cost = estimate_cost_usd(model_id, u["input_tokens"], u["output_tokens"],
                             u["cache_read_input_tokens"], u["cache_creation_input_tokens"])
    # A tabela de dossiês guarda só entrada e saída; soma os tokens de cache na entrada.
    u_total = {"input_tokens": u["input_tokens"] + u["cache_read_input_tokens"] + u["cache_creation_input_tokens"],
               "output_tokens": u["output_tokens"]}
    dossier_id = db.save_dossier(brand_id, model_id, effort, ", ".join(analysis_models), len(items),
                                 markdown, aggregate, u_total, cost)
    export_dossier(dossier_id)
    return dossier_id


# --- exportação -------------------------------------------------------------

def _slug(s: str) -> str:
    keep = "".join(c if c.isalnum() else "-" for c in s.lower())
    return "-".join(filter(None, keep.split("-")))[:60] or "marca"


def export_dossier(dossier_id: int) -> dict[str, Path]:
    """Grava .md e .json em data/exports/<marca>/ e devolve os caminhos."""
    d = db.get_dossier(dossier_id)
    if not d:
        raise ValueError("Dossiê não encontrado")
    brand = db.get_brand(d["brand_id"]) or {"name": "marca"}
    folder = EXPORTS_DIR / _slug(brand["name"])
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"dossie-v{d['version']}"
    md_path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")
    md_path.write_text(d["markdown"], encoding="utf-8")
    payload = {
        "marca": brand, "versao": d["version"], "modelo_sintese": d["model"], "modelo_analise": d["analysis_model"],
        "criado_em": d["created_at"], "agregacao": d["aggregate"],
        "posts": collect_analysis_items(d["brand_id"]),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def dossier_bundle_json(dossier_id: int) -> str:
    d = db.get_dossier(dossier_id)
    if not d:
        return "{}"
    brand = db.get_brand(d["brand_id"])
    return json.dumps({
        "marca": brand, "versao": d["version"], "modelo_sintese": d["model"], "modelo_analise": d["analysis_model"],
        "criado_em": d["created_at"], "agregacao": d["aggregate"], "posts": collect_analysis_items(d["brand_id"]),
    }, ensure_ascii=False, indent=1)


def reset_data() -> None:
    """Apaga banco, imagens e exportações. Uso em testes."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
