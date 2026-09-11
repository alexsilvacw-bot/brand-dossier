"""Agregação determinística das análises por post. Sem LLM.

Produz as frequências e médias que o redator do dossiê deve usar como fato.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, pstdev
from typing import Any


def _dist(counter: Counter, total: int, top: int | None = None) -> list[dict[str, Any]]:
    items = counter.most_common(top)
    return [{"valor": k, "n": v, "pct": round(100 * v / total, 1) if total else 0.0} for k, v in items]


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _norm(s: str) -> str:
    return " ".join(s.lower().strip().split())


def aggregate_analyses(items: list[dict[str, Any]]) -> dict[str, Any]:
    """items: lista de {ref, caption, metrics, analysis}."""
    n = len(items)
    if n == 0:
        return {"n_posts": 0}

    c_framework, c_hook, c_cta, c_triggers = Counter(), Counter(), Counter(), Counter()
    c_register, c_voice, c_pillar, c_value = Counter(), Counter(), Counter(), Counter()
    c_depth, c_awareness, c_format, c_text_in_img = Counter(), Counter(), Counter(), Counter()
    c_emoji_use, c_coherence, c_confidence, c_quality = Counter(), Counter(), Counter(), Counter()
    c_themes, c_vocab, c_colors, c_style, c_proof, c_rhetoric = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    c_density, c_pronoun, c_punct, c_reading = Counter(), Counter(), Counter(), Counter()
    c_personas: Counter = Counter()
    persona_examples: dict[str, dict[str, Any]] = {}
    theme_examples: dict[str, list[str]] = {}
    tone_dims = {"formalidade": [], "profundidade_tecnica": [], "autoridade": [], "urgencia": [], "calor": [], "humor": []}

    words, sentences, avg_sentence, emojis, hashtags, paragraphs = [], [], [], [], [], []
    has_cta_pattern = has_cta_llm = has_hashtags = has_people = brand_visible = has_question = 0
    slides: list[int] = []
    carousel_refs: list[str] = []

    for it in items:
        a = it["analysis"]
        m = it["metrics"]
        ref = it["ref"]
        leg, vis, con = a["legenda"], a["visual"], a["conteudo"]

        c_framework[leg["framework"]] += 1
        c_hook[leg["tipo_de_gancho"]] += 1
        c_cta[leg["tipo_de_cta"]] += 1
        c_triggers.update(leg.get("gatilhos", []))
        c_rhetoric.update(_norm(x) for x in leg.get("figuras_retoricas", []))
        c_register[leg["registro"]] += 1
        c_voice[leg["voz"]] += 1
        c_emoji_use[leg["uso_de_emoji"]] += 1
        c_vocab.update(_norm(x) for x in leg.get("vocabulario_notavel", []))
        for k in tone_dims:
            v = leg["tom"].get(k)
            if isinstance(v, (int, float)):
                tone_dims[k].append(float(v))
        if leg.get("tem_cta"):
            has_cta_llm += 1

        c_pillar[con["pilar"]] += 1
        c_value[con["tipo_de_valor"]] += 1
        c_depth[con["profundidade"]] += 1
        c_awareness[con["persona_alvo"]["estagio_de_consciencia"]] += 1
        c_proof.update(_norm(x) for x in con.get("mecanismos_de_prova", []))
        theme = _norm(con["tema_principal"])
        c_themes[theme] += 1
        theme_examples.setdefault(theme, []).append(ref)
        for t in con.get("temas_secundarios", []):
            c_themes[_norm(t)] += 0.5  # peso menor para secundários
        pname = _norm(con["persona_alvo"]["nome_curto"])
        c_personas[pname] += 1
        persona_examples.setdefault(pname, {**con["persona_alvo"], "posts": []})["posts"].append(ref)

        c_format[vis["formato"]] += 1
        c_text_in_img[vis["texto_na_imagem"]] += 1
        c_quality[vis["qualidade_de_producao"]] += 1
        c_colors.update(_norm(x) for x in vis.get("cores_dominantes", []))
        c_style.update(_norm(x) for x in vis.get("palavras_de_estilo", []))
        if vis.get("pessoas_presentes"):
            has_people += 1
        if vis.get("marca_visivel"):
            brand_visible += 1

        c_coherence[a["coerencia_imagem_legenda"]] += 1
        c_confidence[a["confianca"]] += 1

        n_img = int(it.get("n_images", 1 if it.get("image_path") else 0) or 0)
        slides.append(n_img)
        if n_img > 1:
            carousel_refs.append(ref)

        words.append(m.get("words", 0))
        sentences.append(m.get("sentences", 0))
        if m.get("avg_sentence_words"):
            avg_sentence.append(m["avg_sentence_words"])
        emojis.append(m.get("emojis", 0))
        hashtags.append(m.get("hashtags", 0))
        paragraphs.append(m.get("paragraphs", 0))
        c_density[m.get("density", "n/a")] += 1
        c_pronoun[m.get("pronoun_strategy", "n/a")] += 1
        c_punct[m.get("punctuation_style", "n/a")] += 1
        c_reading[m.get("reading_level", "n/a")] += 1
        if m.get("has_cta_pattern"):
            has_cta_pattern += 1
        if m.get("hashtags", 0) > 0:
            has_hashtags += 1
        if m.get("questions", 0) > 0:
            has_question += 1

    tone_summary = {}
    for k, vals in tone_dims.items():
        if vals:
            tone_summary[k] = {"media": round(mean(vals), 1), "desvio": round(pstdev(vals), 1) if len(vals) > 1 else 0.0,
                               "min": min(vals), "max": max(vals)}

    themes_out = []
    for theme, score in c_themes.most_common(15):
        themes_out.append({"tema": theme, "peso": round(score, 1), "posts_principal": theme_examples.get(theme, [])})

    personas_out = []
    for pname, cnt in c_personas.most_common(8):
        p = persona_examples[pname]
        personas_out.append({"nome_curto": p["nome_curto"], "n_posts": cnt, "posts": p["posts"],
                             "descricao": p["descricao"], "dor": p["dor"], "desejo": p["desejo"],
                             "estagio_de_consciencia": p["estagio_de_consciencia"]})

    pct = lambda x: round(100 * x / n, 1)  # noqa: E731

    return {
        "n_posts": n,
        "texto": {
            "palavras_media": _avg(words), "palavras_min": min(words), "palavras_max": max(words),
            "palavras_desvio": round(pstdev(words), 1) if n > 1 else 0.0,
            "frases_media": _avg(sentences), "palavras_por_frase_media": _avg(avg_sentence),
            "paragrafos_media": _avg(paragraphs),
            "emojis_media": _avg(emojis), "hashtags_media": _avg(hashtags),
            "pct_com_hashtags": pct(has_hashtags), "pct_com_pergunta": pct(has_question),
            "pct_com_cta_por_padrao": pct(has_cta_pattern), "pct_com_cta_segundo_analise": pct(has_cta_llm),
            "densidade": _dist(c_density, n), "nivel_de_leitura": _dist(c_reading, n),
            "estrategia_de_pronome": _dist(c_pronoun, n), "estilo_de_pontuacao": _dist(c_punct, n),
        },
        "copy": {
            "frameworks": _dist(c_framework, n), "ganchos": _dist(c_hook, n), "tipos_de_cta": _dist(c_cta, n),
            "gatilhos": _dist(c_triggers, n), "figuras_retoricas": _dist(c_rhetoric, n, 10),
            "registro": _dist(c_register, n), "voz": _dist(c_voice, n), "uso_de_emoji": _dist(c_emoji_use, n),
            "tom": tone_summary, "vocabulario_recorrente": _dist(c_vocab, n, 25),
        },
        "conteudo": {
            "temas": themes_out, "pilares": _dist(c_pillar, n), "tipos_de_valor": _dist(c_value, n),
            "profundidade": _dist(c_depth, n), "estagios_de_consciencia": _dist(c_awareness, n),
            "mecanismos_de_prova": _dist(c_proof, n, 10), "personas": personas_out,
        },
        "visual": {
            "formatos": _dist(c_format, n), "texto_na_imagem": _dist(c_text_in_img, n),
            "qualidade_de_producao": _dist(c_quality, n), "cores_recorrentes": _dist(c_colors, n, 12),
            "palavras_de_estilo": _dist(c_style, n, 15),
            "pct_com_pessoas": pct(has_people), "pct_marca_visivel": pct(brand_visible),
            "carrosseis": {
                "n": len(carousel_refs), "pct": pct(len(carousel_refs)), "posts": carousel_refs,
                "slides_media_nos_carrosseis": _avg([x for x in slides if x > 1]),
                "slides_max": max(slides) if slides else 0,
            },
        },
        "coerencia_imagem_legenda": _dist(c_coherence, n),
        "confianca_das_analises": _dist(c_confidence, n),
    }
