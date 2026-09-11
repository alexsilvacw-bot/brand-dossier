"""Testes de brand_dossier.llm.build_user_content e brand_dossier.prompts.analysis_user_text."""

from __future__ import annotations

from brand_dossier.llm import ImagePayload, build_user_content
from brand_dossier.prompts import analysis_user_text


def _images(n: int) -> list[ImagePayload]:
    return [ImagePayload("image/jpeg", "AAAA", 10, 10) for _ in range(n)]


# --- build_user_content -------------------------------------------------------

def test_build_user_content_sem_imagens():
    content = build_user_content([], "texto do post")
    assert len(content) == 1
    assert content[0] == {"type": "text", "text": "texto do post"}


def test_build_user_content_com_uma_imagem_nao_rotula_slide():
    content = build_user_content(_images(1), "texto do post")
    assert len(content) == 2
    assert content[0]["type"] == "image"
    assert content[1] == {"type": "text", "text": "texto do post"}
    # Com uma imagem só, não deve haver rótulo de slide.
    assert not any("Slide" in b.get("text", "") for b in content if b["type"] == "text" and b is not content[-1])


def test_build_user_content_com_tres_imagens_rotula_cada_slide_e_texto_por_ultimo():
    content = build_user_content(_images(3), "texto do post")
    # 3 imagens * (rótulo + imagem) + o texto final = 7 blocos.
    assert len(content) == 7

    labels = [b["text"] for b in content if b["type"] == "text"]
    assert labels[:3] == ["Slide 1 de 3:", "Slide 2 de 3:", "Slide 3 de 3:"]
    # O texto do usuário vem por último, depois de todas as imagens.
    assert content[-1] == {"type": "text", "text": "texto do post"}
    assert [b["type"] for b in content[:-1]] == ["text", "image", "text", "image", "text", "image"]


# --- analysis_user_text --------------------------------------------------------

def test_analysis_user_text_sem_imagem():
    texto = analysis_user_text("P1", "legenda", {}, n_images=0)
    assert "não tem imagem" in texto


def test_analysis_user_text_com_uma_imagem():
    texto = analysis_user_text("P1", "legenda", {}, n_images=1)
    assert "A imagem do post está acima" in texto


def test_analysis_user_text_com_carrossel_de_cinco_slides():
    texto = analysis_user_text("P1", "legenda", {}, n_images=5)
    assert "carrossel com 5 slides" in texto
