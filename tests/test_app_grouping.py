"""Testes de app.py: _split_slide_name, _default_groups e _slide_sort_key.

app.py executa código de nível de módulo do Streamlit (st.set_page_config, db.init_db()
etc.) e chama a interface fora do runtime real, o que dispara apenas avisos em modo
"bare" do Streamlit, mas não é algo que queremos acionar num teste unitário isolado.

Por isso não importamos brand_dossier/app.py inteiro: extraímos só o trecho de texto
entre "_SLIDE_RE = " e "def tab_posts" (onde vivem as três funções puras testadas
aqui) e o executamos com exec(), num namespace com os e re disponíveis.
"""

from __future__ import annotations

import os
import re
import types
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _load_grouping_functions() -> dict:
    source = APP_PATH.read_text(encoding="utf-8")
    start = source.index("_SLIDE_RE = ")
    end = source.index("def tab_posts")
    snippet = source[start:end]
    namespace: dict = {"os": os, "re": re}
    exec(compile(snippet, str(APP_PATH), "exec"), namespace)  # noqa: S102
    return namespace


_FUNCS = _load_grouping_functions()
_split_slide_name = _FUNCS["_split_slide_name"]
_default_groups = _FUNCS["_default_groups"]
_slide_sort_key = _FUNCS["_slide_sort_key"]


def _upload(name: str):
    """Objeto simples com atributo .name, como um UploadedFile do Streamlit."""
    return types.SimpleNamespace(name=name)


# --- _split_slide_name --------------------------------------------------------

def test_split_slide_name_com_numero_no_final():
    assert _split_slide_name("post3_2.jpg") == ("post3", 2)


def test_split_slide_name_sem_numero_no_final():
    assert _split_slide_name("foto.png") == ("foto", None)


def test_split_slide_name_padrao_de_camera_captura_so_dois_digitos():
    """A regex captura no máximo 2 dígitos como número de slide, então em nomes no
    padrão de câmera (IMG_0001, IMG_0002, ...) o número inteiro vai para o slide e o
    prefixo fica "img". No modo "nome" isso agrupa fotos sequenciais como um carrossel,
    o que é o comportamento esperado desse modo."""
    assert _split_slide_name("IMG_0001.jpg") == ("img", 1)
    assert _split_slide_name("IMG_0002.jpg") == ("img", 2)


# --- _default_groups -----------------------------------------------------------

def test_default_groups_modo_um_cria_um_grupo_por_imagem():
    uploads = [_upload("a.jpg"), _upload("b.jpg"), _upload("c.jpg")]
    assert _default_groups(uploads, "um") == {0: 1, 1: 2, 2: 3}


def test_default_groups_modo_carrossel_coloca_tudo_num_grupo_so():
    uploads = [_upload("a.jpg"), _upload("b.jpg"), _upload("c.jpg")]
    assert _default_groups(uploads, "carrossel") == {0: 1, 1: 1, 2: 1}


def test_default_groups_modo_nome_agrupa_pelo_prefixo_do_numero_final():
    uploads = [_upload("post3_1.jpg"), _upload("post3_2.jpg"), _upload("foto.png")]
    groups = _default_groups(uploads, "nome")

    # post3_1 e post3_2 compartilham o prefixo "post3" -> mesmo grupo (carrossel).
    assert groups[0] == groups[1]
    # foto.png não tem número no final -> fica sozinha, em grupo próprio.
    assert groups[2] not in (groups[0], groups[1])


def test_default_groups_modo_nome_padrao_de_camera_cai_no_mesmo_grupo():
    """Segue da mesma limitação de _split_slide_name: como IMG_0001.jpg e
    IMG_0002.jpg têm o mesmo prefixo detectado ("img"), o modo "nome" os agrupa
    como se fossem slides de um único carrossel, mesmo não sendo. Comportamento
    atual, apenas documentado aqui."""
    uploads = [_upload("IMG_0001.jpg"), _upload("IMG_0002.jpg")]
    groups = _default_groups(uploads, "nome")
    assert groups[0] == groups[1]


# --- _slide_sort_key ------------------------------------------------------------

def test_slide_sort_key_ordena_pelo_numero_do_slide():
    uploads = [_upload("post3_2.jpg"), _upload("post3_1.jpg"), _upload("post3_3.jpg")]
    ordered = sorted(uploads, key=_slide_sort_key)
    assert [u.name for u in ordered] == ["post3_1.jpg", "post3_2.jpg", "post3_3.jpg"]


def test_slide_sort_key_sem_numero_desempata_pelo_nome():
    uploads = [_upload("foto_b.png"), _upload("foto_a.png")]
    ordered = sorted(uploads, key=_slide_sort_key)
    assert [u.name for u in ordered] == ["foto_a.png", "foto_b.png"]
