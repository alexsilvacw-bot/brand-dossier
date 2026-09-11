"""Testes de brand_dossier.metrics.compute_caption_metrics (sem LLM)."""

from __future__ import annotations

from brand_dossier.metrics import compute_caption_metrics


def test_legenda_vazia():
    m = compute_caption_metrics("")
    assert m.words == 0
    assert m.chars == 0
    assert m.sentences == 0
    assert m.density == "vazio"
    assert m.reading_level == "n/a"
    assert m.pronoun_strategy == "neutro"
    assert m.punctuation_style == "neutro"
    assert m.has_cta_pattern is False
    assert m.cta_matches == []
    assert m.hashtags == 0
    assert m.emojis == 0


def test_legenda_none():
    m = compute_caption_metrics(None)
    assert m.words == 0
    assert m.density == "vazio"


def test_legenda_curta_ptbr_com_emoji_hashtag_e_cta():
    caption = "Chegou a novidade! 🎉 Clique agora e garanta o seu. Link na bio #promo #outlet"
    m = compute_caption_metrics(caption)

    assert m.words > 0
    assert m.emojis == 1
    assert m.emoji_ratio_per_100_words > 0

    assert m.hashtags == 2
    assert sorted(m.hashtag_list) == ["outlet", "promo"]

    assert m.has_cta_pattern is True
    assert "clique" in m.cta_matches
    assert "garanta" in m.cta_matches
    assert "link na bio" in m.cta_matches

    assert m.density in ("minimo", "curto")


def test_legenda_ingles_centrada_no_leitor():
    caption = "Your business deserves better tools. You will love the results!"
    m = compute_caption_metrics(caption)

    assert m.you_words >= 2
    assert m.we_words == 0
    assert m.pronoun_strategy == "centrado-no-leitor"


def test_legenda_centrada_na_marca():
    caption = "Nós valorizamos nossa missão. Nossa equipe é dedicada. Nosso compromisso é com a qualidade."
    m = compute_caption_metrics(caption)

    assert m.we_words >= 2
    assert m.you_words == 0
    assert m.pronoun_strategy == "centrado-na-marca"


def test_legenda_equilibrada():
    caption = "Você pode contar com a gente. Nós cuidamos de tudo para você."
    m = compute_caption_metrics(caption)

    assert m.you_words > 0
    assert m.we_words > 0


def test_contagem_de_frases_e_densidade():
    caption = "Primeira frase. Segunda frase! Terceira frase?"
    m = compute_caption_metrics(caption)

    assert m.sentences == 3
    assert m.avg_sentence_words == round(m.words / m.sentences, 1)
    assert m.density == "minimo"
    assert m.reading_level == "simples"


def test_densidade_por_faixa_de_palavras():
    poucas = compute_caption_metrics(" ".join(["palavra"] * 10))
    curto = compute_caption_metrics(" ".join(["palavra"] * 30))
    medio = compute_caption_metrics(" ".join(["palavra"] * 80))
    longo = compute_caption_metrics(" ".join(["palavra"] * 200))
    muito_longo = compute_caption_metrics(" ".join(["palavra"] * 300))

    assert poucas.density == "minimo"
    assert curto.density == "curto"
    assert medio.density == "medio"
    assert longo.density == "longo"
    assert muito_longo.density == "muito-longo"


def test_punctuation_style_entusiasmado():
    m = compute_caption_metrics("Adorei muito isso!!")
    assert m.exclamations == 2
    assert m.punctuation_style == "entusiasmado"


def test_punctuation_style_conversacional():
    m = compute_caption_metrics("Você já tentou isso? Já pensou em mudar?")
    assert m.questions == 2
    assert m.punctuation_style == "conversacional"


def test_punctuation_style_reflexivo():
    m = compute_caption_metrics("Pensando bastante... talvez... quem sabe amanhece diferente")
    assert m.punctuation_style == "reflexivo"


def test_punctuation_style_neutro():
    m = compute_caption_metrics("Isso é o nosso produto novo hoje.")
    assert m.punctuation_style == "neutro"
