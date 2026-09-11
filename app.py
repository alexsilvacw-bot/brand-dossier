"""Interface Streamlit do Brand Dossier.

Rodar: streamlit run app.py
"""

from __future__ import annotations

import csv
import io
import json
import os

import streamlit as st

from brand_dossier import db
from brand_dossier.config import (
    DEFAULT_ANALYSIS_EFFORT, DEFAULT_ANALYSIS_MODEL, DEFAULT_SYNTHESIS_EFFORT, DEFAULT_SYNTHESIS_MODEL,
    EFFORT_LEVELS, ENGINES, MODELS, default_engine, mock_mode,
)
from brand_dossier.engine_claude_code import claude_cli_path
from brand_dossier.pipeline import (
    analyze_brand_posts, build_dossier, collect_analysis_items, dossier_bundle_json, store_image,
)

st.set_page_config(page_title="Brand Dossier", page_icon="🧭", layout="wide")
db.init_db()

LANGS = {"pt-BR": "Português (Brasil)", "en": "English", "es": "Español"}


# ---------------------------------------------------------------------------
# Sidebar: credenciais, modelos, marca ativa
# ---------------------------------------------------------------------------

def sidebar() -> dict:
    st.sidebar.title("🧭 Brand Dossier")

    st.sidebar.subheader("Motor")
    engine_ids = list(ENGINES.keys())
    engine = st.sidebar.radio("Como chamar o Claude", engine_ids, index=engine_ids.index(default_engine()),
                              format_func=lambda k: ENGINES[k], label_visibility="collapsed")
    api_key = None
    can_call = False
    if mock_mode():
        st.sidebar.warning("Modo simulado ativo (BRAND_DOSSIER_MOCK=1). Nenhuma chamada real será feita.")
        can_call = True
    elif engine == "claude_code":
        if claude_cli_path():
            st.sidebar.success("Claude Code encontrado. Usa sua assinatura, sem custo de API.")
            can_call = True
        else:
            st.sidebar.error("Claude Code não encontrado no PATH. Instale ou troque para a API.")
    elif os.environ.get("ANTHROPIC_API_KEY"):
        st.sidebar.success("Chave da API carregada do ambiente ou .env")
        can_call = True
    else:
        api_key = st.sidebar.text_input("ANTHROPIC_API_KEY", type="password",
                                        help="Fica só nesta sessão. Para persistir, crie um arquivo .env.")
        can_call = bool(api_key)
        if not api_key:
            st.sidebar.error("Informe a chave da API para analisar posts.")

    st.sidebar.subheader("Modelos")
    ids = list(MODELS.keys())
    labels = {k: f"{v.label}  ·  ${v.input_price:.0f}/${v.output_price:.0f} por 1M" for k, v in MODELS.items()}
    analysis_model = st.sidebar.selectbox("Análise por post", ids, index=ids.index(DEFAULT_ANALYSIS_MODEL),
                                          format_func=lambda k: labels[k])
    analysis_effort = None
    if MODELS[analysis_model].supports_effort:
        analysis_effort = st.sidebar.select_slider("Esforço da análise", EFFORT_LEVELS, value=DEFAULT_ANALYSIS_EFFORT)
    synthesis_model = st.sidebar.selectbox("Síntese do dossiê", ids, index=ids.index(DEFAULT_SYNTHESIS_MODEL),
                                           format_func=lambda k: labels[k])
    synthesis_effort = None
    if MODELS[synthesis_model].supports_effort:
        synthesis_effort = st.sidebar.select_slider("Esforço da síntese", EFFORT_LEVELS, value=DEFAULT_SYNTHESIS_EFFORT)
    st.sidebar.caption(MODELS[analysis_model].note + " " + MODELS[synthesis_model].note)

    st.sidebar.subheader("Marca ativa")
    brands = db.list_brands()
    options = {b["id"]: b["name"] for b in brands}
    brand_id = None
    if options:
        current = st.session_state.get("brand_id")
        keys = list(options.keys())
        idx = keys.index(current) if current in keys else 0
        brand_id = st.sidebar.selectbox("Selecione", keys, index=idx, format_func=lambda k: options[k])
        st.session_state["brand_id"] = brand_id
        costs = db.brand_cost_summary(brand_id)
        label = "equivalente em preço de API" if engine == "claude_code" else "gasto estimado"
        st.sidebar.caption(f"Consumo nesta marca ({label}): US$ {costs['total_usd']:.3f}")
    else:
        st.sidebar.info("Cadastre uma marca na aba Marca.")

    return {
        "api_key": api_key, "analysis_model": analysis_model, "analysis_effort": analysis_effort,
        "synthesis_model": synthesis_model, "synthesis_effort": synthesis_effort, "brand_id": brand_id,
        "engine": engine, "can_call": can_call,
    }


# ---------------------------------------------------------------------------
# Aba Marca
# ---------------------------------------------------------------------------

def tab_brand(ctx: dict) -> None:
    st.header("Marca")
    brand = db.get_brand(ctx["brand_id"]) if ctx["brand_id"] else None
    mode = st.radio("Ação", ["Editar marca ativa", "Nova marca"], horizontal=True,
                    index=0 if brand else 1, label_visibility="collapsed")
    editing = brand if mode == "Editar marca ativa" and brand else None

    with st.form("brand_form"):
        name = st.text_input("Nome da empresa", value=editing["name"] if editing else "")
        summary = st.text_area("Resumo da empresa", height=120, value=editing["summary"] if editing else "",
                               placeholder="O que a empresa faz, para quem, onde atua, porte, diferenciais.")
        products = st.text_area("Produtos e serviços", height=100, value=editing["products"] if editing else "",
                                placeholder="Um por linha, com uma frase de contexto se ajudar.")
        audience = st.text_area("Público declarado (opcional)", height=70, value=editing["audience"] if editing else "",
                                placeholder="Quem a marca diz que quer atingir. Deixe vazio para inferir só dos posts.")
        lang_keys = list(LANGS.keys())
        language = st.selectbox("Idioma do dossiê", lang_keys, format_func=lambda k: LANGS[k],
                                index=lang_keys.index(editing["language"]) if editing and editing["language"] in lang_keys else 0)
        submitted = st.form_submit_button("Salvar")
    if submitted:
        if not name.strip():
            st.error("Nome é obrigatório.")
        elif editing:
            db.update_brand(editing["id"], name, summary, products, audience, language)
            st.success("Marca atualizada.")
            st.rerun()
        else:
            new_id = db.create_brand(name, summary, products, audience, language)
            st.session_state["brand_id"] = new_id
            st.success("Marca criada.")
            st.rerun()

    if brand:
        with st.expander("Excluir marca ativa"):
            st.warning("Apaga a marca, seus posts, análises e dossiês. Não tem volta.")
            if st.button("Excluir definitivamente", type="primary"):
                db.delete_brand(brand["id"])
                st.session_state.pop("brand_id", None)
                st.rerun()


# ---------------------------------------------------------------------------
# Aba Posts
# ---------------------------------------------------------------------------

def _parse_caption_csv(file) -> dict[str, str]:
    """CSV com colunas filename e caption. Aceita ; ou , como separador."""
    raw = file.getvalue().decode("utf-8-sig")
    sample = raw[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    out = {}
    for row in reader:
        keys = {k.lower().strip(): v for k, v in row.items() if k}
        fname = keys.get("filename") or keys.get("arquivo") or keys.get("imagem") or ""
        cap = keys.get("caption") or keys.get("legenda") or ""
        if fname:
            out[fname.strip()] = (cap or "").strip()
    return out


def tab_posts(ctx: dict) -> None:
    st.header("Posts")
    if not ctx["brand_id"]:
        st.info("Cadastre e selecione uma marca primeiro.")
        return
    brand_id = ctx["brand_id"]

    st.subheader("Adicionar posts")
    uploads = st.file_uploader("Imagens dos posts", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
                               key=f"uploader_{st.session_state.get('uploader_gen', 0)}")
    csv_file = st.file_uploader("Opcional: CSV com colunas filename e caption para preencher as legendas",
                                type=["csv", "txt"], key=f"csv_{st.session_state.get('uploader_gen', 0)}")
    prefill = _parse_caption_csv(csv_file) if csv_file else {}

    if uploads:
        with st.form("posts_form"):
            captions = {}
            for i, up in enumerate(uploads):
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.image(up, width=160, caption=up.name)
                with c2:
                    captions[i] = st.text_area(f"Legenda de {up.name}", height=140, key=f"cap_{up.name}_{i}",
                                               value=prefill.get(up.name, ""), label_visibility="collapsed",
                                               placeholder="Cole a legenda aqui. Pode ficar vazio se o post não tem texto.")
            if st.form_submit_button(f"Adicionar {len(uploads)} post(s)"):
                for i, up in enumerate(uploads):
                    path = store_image(brand_id, up.name, up.getvalue())
                    db.add_post(brand_id, path, up.name, captions.get(i, ""))
                st.session_state["uploader_gen"] = st.session_state.get("uploader_gen", 0) + 1
                st.success(f"{len(uploads)} post(s) adicionados.")
                st.rerun()

    st.subheader("Posts cadastrados")
    posts = db.list_posts(brand_id)
    if not posts:
        st.caption("Nenhum post ainda.")
        return
    analyses = db.latest_analyses(brand_id)
    st.caption(f"{len(posts)} posts, {len(analyses)} analisados.")
    for i, p in enumerate(posts, start=1):
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 1])
            with c1:
                if p.get("image_path") and os.path.exists(p["image_path"]):
                    st.image(p["image_path"], width=150)
                st.caption(f"P{i} · {'analisado' if p['id'] in analyses else 'pendente'}")
            with c2:
                new_cap = st.text_area("Legenda", value=p.get("caption", ""), key=f"edit_{p['id']}", height=120,
                                       label_visibility="collapsed")
                if new_cap != p.get("caption", ""):
                    if st.button("Salvar legenda", key=f"save_{p['id']}"):
                        db.update_post_caption(p["id"], new_cap)
                        st.rerun()
            with c3:
                if st.button("Remover", key=f"del_{p['id']}"):
                    db.delete_post(p["id"])
                    st.rerun()


# ---------------------------------------------------------------------------
# Aba Análise
# ---------------------------------------------------------------------------

def _kv(d: dict) -> None:
    lines = []
    for k, v in d.items():
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v) if v else "nenhum"
        elif isinstance(v, bool):
            v = "sim" if v else "não"
        elif v in ("", None):
            v = "vazio"
        lines.append(f"- **{k}:** {v}")
    st.markdown("\n".join(lines))


def _render_analysis(a: dict) -> None:
    leg, vis, con = a["legenda"], a["visual"], a["conteudo"]
    st.markdown(f"**Resumo:** {a['resumo']}")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Copy**")
        _kv({
            "framework": leg["framework"], "gancho": leg["tipo_de_gancho"], "gancho_texto": leg["gancho_texto"],
            "cta": leg["tipo_de_cta"], "cta_texto": leg["cta_texto"], "gatilhos": leg["gatilhos"],
            "registro": leg["registro"], "voz": leg["voz"], "emoji": leg["uso_de_emoji"],
            "vocabulário": leg["vocabulario_notavel"],
        })
        st.markdown("**Tom (1 a 10)**")
        _kv({k: v for k, v in leg["tom"].items() if k != "evidencias"})
        st.caption("Evidências: " + " | ".join(leg["tom"].get("evidencias", [])))
    with c2:
        st.markdown("**Conteúdo**")
        _kv({
            "tema": con["tema_principal"], "secundarios": con["temas_secundarios"], "pilar": con["pilar"],
            "profundidade": con["profundidade"], "valor": con["tipo_de_valor"], "prova": con["mecanismos_de_prova"],
            "produto": con["produto_ou_servico_citado"],
        })
        st.markdown("**Persona**")
        _kv(con["persona_alvo"])
    with c3:
        st.markdown("**Visual**")
        _kv({
            "formato": vis["formato"], "descricao": vis["descricao"], "composicao": vis["composicao"],
            "cores": vis["cores_dominantes"], "texto_na_imagem": vis["texto_na_imagem"],
            "transcricao": vis["texto_na_imagem_transcricao"], "pessoas": vis["pessoas_presentes"],
            "marca_visivel": vis["marca_visivel"], "estilo": vis["palavras_de_estilo"],
            "producao": vis["qualidade_de_producao"],
        })
    st.markdown(f"**Coerência imagem/legenda:** {a['coerencia_imagem_legenda']} · **Confiança:** {a['confianca']}")
    st.markdown(f"**Padrão reutilizável:** {a['padrao_reutilizavel']}")
    if a.get("observacoes"):
        st.caption("Observações: " + a["observacoes"])


def tab_analysis(ctx: dict) -> None:
    st.header("Análise por post")
    if not ctx["brand_id"]:
        st.info("Cadastre e selecione uma marca primeiro.")
        return
    brand_id = ctx["brand_id"]
    posts = db.list_posts(brand_id)
    analyses = db.latest_analyses(brand_id)
    pending = [p for p in posts if p["id"] not in analyses]
    st.caption(f"{len(posts)} posts · {len(analyses)} analisados · {len(pending)} pendentes")

    c1, c2 = st.columns([2, 1])
    with c1:
        only_missing = st.checkbox("Analisar só os pendentes", value=True,
                                   help="Desmarque para reanalisar todos os posts com o modelo selecionado.")
    with c2:
        run = st.button("Analisar posts", type="primary", disabled=not posts or not ctx["can_call"])

    if run:
        bar = st.progress(0.0, text="Iniciando...")
        log = st.empty()
        lines: list[str] = []
        total_cost = 0.0

        def progress(n: int, total: int, res) -> None:
            nonlocal total_cost
            total_cost += res.cost_usd
            lines.append(f"{'✅' if res.ok else '❌'} post {res.post_id}" + (f": {res.error}" if res.error else ""))
            bar.progress(n / total, text=f"{n}/{total} posts · US$ {total_cost:.3f}")
            log.code("\n".join(lines[-12:]))

        with st.spinner("Analisando com " + MODELS[ctx["analysis_model"]].label):
            results = analyze_brand_posts(brand_id, ctx["analysis_model"], ctx["analysis_effort"],
                                          only_missing=only_missing, api_key=ctx["api_key"], progress=progress,
                                          engine=ctx["engine"])
        ok = sum(1 for r in results if r.ok)
        if not results:
            st.info("Nada a analisar.")
        elif ok == len(results):
            st.success(f"{ok} posts analisados. Custo estimado: US$ {total_cost:.3f}")
        else:
            st.warning(f"{ok} de {len(results)} posts analisados. Veja os erros acima.")
        analyses = db.latest_analyses(brand_id)

    st.subheader("Resultados")
    if not analyses:
        st.caption("Nenhuma análise ainda.")
        return
    for i, p in enumerate(posts, start=1):
        a = analyses.get(p["id"])
        if not a:
            continue
        title = f"P{i} · {a['analysis']['conteudo']['tema_principal']} · {a['analysis']['legenda']['framework']} · {a['model']}"
        with st.expander(title):
            c1, c2 = st.columns([1, 4])
            with c1:
                if p.get("image_path") and os.path.exists(p["image_path"]):
                    st.image(p["image_path"], width=220)
                m = a["metrics"]
                st.caption(f"{m['words']} palavras · {m['sentences']} frases · {m['emojis']} emojis · "
                           f"{m['hashtags']} hashtags · densidade {m['density']}")
                tokens_in = a["input_tokens"] + a["cache_read_tokens"] + a["cache_write_tokens"]
                st.caption(f"Tokens: {tokens_in} in / {a['output_tokens']} out · US$ {a['cost_usd']:.4f}")
            with c2:
                _render_analysis(a["analysis"])
            if st.toggle("JSON completo", key=f"json_{p['id']}"):
                st.json(a["analysis"])


# ---------------------------------------------------------------------------
# Aba Dossiê
# ---------------------------------------------------------------------------

def tab_dossier(ctx: dict) -> None:
    st.header("Dossiê")
    if not ctx["brand_id"]:
        st.info("Cadastre e selecione uma marca primeiro.")
        return
    brand_id = ctx["brand_id"]
    items = collect_analysis_items(brand_id)
    st.caption(f"{len(items)} posts analisados disponíveis para a síntese.")

    if st.button("Gerar dossiê", type="primary", disabled=not items or not ctx["can_call"]):
        placeholder = st.empty()
        buffer: list[str] = []

        def on_text(chunk: str) -> None:
            buffer.append(chunk)
            if len(buffer) % 8 == 0:
                placeholder.markdown("".join(buffer) + " ▌")

        with st.spinner("Sintetizando com " + MODELS[ctx["synthesis_model"]].label):
            try:
                dossier_id = build_dossier(brand_id, ctx["synthesis_model"], ctx["synthesis_effort"],
                                           api_key=ctx["api_key"], on_text=on_text, engine=ctx["engine"])
                placeholder.empty()
                st.session_state["dossier_id"] = dossier_id
                st.success("Dossiê gerado e exportado em data/exports/.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                placeholder.empty()
                st.error(f"Falha na síntese: {e}")

    versions = db.list_dossiers(brand_id)
    if not versions:
        st.caption("Nenhum dossiê gerado ainda.")
        return
    ids = [v["id"] for v in versions]
    label = {v["id"]: f"v{v['version']} · {v['model']} · {v['post_count']} posts · {v['created_at'][:16]} · US$ {v['cost_usd']:.3f}"
             for v in versions}
    current = st.session_state.get("dossier_id")
    idx = ids.index(current) if current in ids else 0
    chosen = st.selectbox("Versão", ids, index=idx, format_func=lambda k: label[k])
    d = db.get_dossier(chosen)
    if not d:
        return
    brand = db.get_brand(brand_id) or {"name": "marca"}
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("Baixar Markdown", d["markdown"], file_name=f"dossie-{brand['name']}-v{d['version']}.md",
                           mime="text/markdown")
    with c2:
        st.download_button("Baixar JSON (agregação + análises)", dossier_bundle_json(chosen),
                           file_name=f"dossie-{brand['name']}-v{d['version']}.json", mime="application/json")
    with c3:
        st.caption(f"Tokens: {d['input_tokens']} in / {d['output_tokens']} out")

    view = st.radio("Ver", ["Dossiê", "Agregação"], horizontal=True, label_visibility="collapsed")
    if view == "Dossiê":
        st.markdown(d["markdown"])
    else:
        st.json(d["aggregate"])


# ---------------------------------------------------------------------------

def main() -> None:
    ctx = sidebar()
    tabs = st.tabs(["Marca", "Posts", "Análise", "Dossiê"])
    with tabs[0]:
        tab_brand(ctx)
    with tabs[1]:
        tab_posts(ctx)
    with tabs[2]:
        tab_analysis(ctx)
    with tabs[3]:
        tab_dossier(ctx)


main()
