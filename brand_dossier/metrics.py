"""Métricas determinísticas da legenda. Sem LLM.

Entram no prompt como fatos e alimentam a agregação. Inspirado em stackmd/src/analyzer.js.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0001F900-\U0001F9FF⭐⭕‼⁉™ℹ↔-↙↩↪⌚⌛⌨⏏⏩-⏳⏸-⏺Ⓜ▪▫▶◀◻-◾⤴⤵〰〽㊗㊙\U0001F1E6-\U0001F1FF]"
)
_HASHTAG_RE = re.compile(r"(?<!\w)#(\w+)")
_MENTION_RE = re.compile(r"(?<!\w)@(\w+)")
_URL_RE = re.compile(r"https?://\S+|www\.\S+|\b[\w-]+\.(?:com|br|io|net|org)(?:\.\w{2})?\b", re.I)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?…]+[\s\n]+|[.!?…]+$|\n{2,}")
_WORD_RE = re.compile(r"[\wÀ-ÿ'-]+")

# Pronomes: leitor (você) versus marca (nós). PT-BR e inglês.
_YOU_WORDS = {"você", "voce", "vocês", "voces", "seu", "sua", "seus", "suas", "te", "ti", "tu", "teu", "tua",
              "you", "your", "yours"}
_WE_WORDS = {"nós", "nos", "nosso", "nossa", "nossos", "nossas", "a gente", "we", "our", "ours", "us"}

# Verbos e expressões típicas de chamada para ação, em PT-BR e inglês.
_CTA_PATTERNS = [
    r"\blink na bio\b", r"\bclique\b", r"\bclica\b", r"\bacesse\b", r"\bacessa\b", r"\bcompre\b", r"\bcompra\b",
    r"\bgaranta\b", r"\bgarante\b", r"\bsaiba mais\b", r"\bconfira\b", r"\bconfere\b", r"\bcomente\b",
    r"\bcomenta\b", r"\bmarque\b", r"\bmarca (?:um|uma|aquele|aquela|seu|sua)\b", r"\bcompartilhe\b",
    r"\bcompartilha\b", r"\bsalve\b", r"\bsalva\b", r"\bsiga\b", r"\bsegue\b", r"\bentre em contato\b",
    r"\bfale com\b", r"\bchame\b", r"\bchama\b", r"\bmande\b", r"\bmanda\b", r"\bwhatsapp\b", r"\bdirect\b",
    r"\bdm\b", r"\binscreva-se\b", r"\bcadastre-se\b", r"\bparticipe\b", r"\bagende\b", r"\bagenda\b",
    r"\bsolicite\b", r"\bpeça\b", r"\baproveite\b", r"\bnão perca\b", r"\bcorre\b",
    r"\bshop now\b", r"\bclick\b", r"\blearn more\b", r"\bsign up\b", r"\bfollow\b", r"\bcomment\b",
    r"\bshare\b", r"\bsave\b", r"\btag\b", r"\bdm us\b", r"\bcontact us\b", r"\bbook\b", r"\bget yours\b",
]
_CTA_RE = re.compile("|".join(_CTA_PATTERNS), re.I)


@dataclass
class CaptionMetrics:
    chars: int = 0
    words: int = 0
    sentences: int = 0
    avg_sentence_words: float = 0.0
    paragraphs: int = 0
    lines: int = 0
    emojis: int = 0
    emoji_ratio_per_100_words: float = 0.0
    hashtags: int = 0
    hashtag_list: list[str] = field(default_factory=list)
    mentions: int = 0
    urls: int = 0
    questions: int = 0
    exclamations: int = 0
    caps_words: int = 0
    caps_ratio: float = 0.0
    you_words: int = 0
    we_words: int = 0
    pronoun_strategy: str = "neutro"
    has_cta_pattern: bool = False
    cta_matches: list[str] = field(default_factory=list)
    density: str = "vazio"
    reading_level: str = "n/a"
    punctuation_style: str = "neutro"
    vocabulary_richness: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _density(words: int) -> str:
    if words == 0:
        return "vazio"
    if words < 15:
        return "minimo"
    if words < 50:
        return "curto"
    if words < 120:
        return "medio"
    if words < 250:
        return "longo"
    return "muito-longo"


def _reading_level(avg_sentence_words: float) -> str:
    if avg_sentence_words == 0:
        return "n/a"
    if avg_sentence_words < 10:
        return "simples"
    if avg_sentence_words < 16:
        return "padrao"
    if avg_sentence_words < 22:
        return "avancado"
    return "denso"


def _punctuation_style(periods: int, exclamations: int, questions: int, ellipses: int) -> str:
    base = max(periods, 1)
    if exclamations > 0.3 * base and exclamations >= 2:
        return "entusiasmado"
    if questions >= 2 or (questions > 0 and questions > 0.3 * base):
        return "conversacional"
    if ellipses >= 2:
        return "reflexivo"
    return "neutro"


def compute_caption_metrics(caption: str | None) -> CaptionMetrics:
    text = (caption or "").strip()
    m = CaptionMetrics()
    if not text:
        return m

    m.chars = len(text)
    words = _WORD_RE.findall(text)
    m.words = len(words)
    lower_words = [w.lower() for w in words]

    # Sentenças: separa por pontuação final ou parágrafo. Remove fragmentos vazios e hashtags soltas.
    raw_sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s and s.strip()]
    sentences = [s for s in raw_sentences if _WORD_RE.search(s) and not all(t.startswith("#") for t in s.split())]
    m.sentences = max(len(sentences), 1 if words else 0)
    m.avg_sentence_words = round(m.words / m.sentences, 1) if m.sentences else 0.0

    m.lines = len([l for l in text.split("\n") if l.strip()])
    m.paragraphs = len([p for p in re.split(r"\n\s*\n", text) if p.strip()])

    m.emojis = len(_EMOJI_RE.findall(text))
    m.emoji_ratio_per_100_words = round(100 * m.emojis / m.words, 1) if m.words else 0.0

    m.hashtag_list = [h.lower() for h in _HASHTAG_RE.findall(text)]
    m.hashtags = len(m.hashtag_list)
    m.mentions = len(_MENTION_RE.findall(text))
    m.urls = len(_URL_RE.findall(text))

    m.questions = text.count("?")
    m.exclamations = text.count("!")
    periods = text.count(".") - 3 * text.count("...")
    ellipses = text.count("...") + text.count("…")
    m.punctuation_style = _punctuation_style(periods, m.exclamations, m.questions, ellipses)

    caps = [w for w in words if len(w) >= 3 and w.isupper() and w.isalpha()]
    m.caps_words = len(caps)
    m.caps_ratio = round(m.caps_words / m.words, 3) if m.words else 0.0

    joined = " " + " ".join(lower_words) + " "
    m.you_words = sum(1 for w in lower_words if w in _YOU_WORDS)
    m.we_words = sum(1 for w in lower_words if w in _WE_WORDS) + joined.count(" a gente ")
    if m.you_words == 0 and m.we_words == 0:
        m.pronoun_strategy = "neutro"
    elif m.you_words >= 2 * max(m.we_words, 1):
        m.pronoun_strategy = "centrado-no-leitor"
    elif m.we_words >= 2 * max(m.you_words, 1):
        m.pronoun_strategy = "centrado-na-marca"
    else:
        m.pronoun_strategy = "equilibrado"

    m.cta_matches = sorted({x.lower() for x in _CTA_RE.findall(text)})
    m.has_cta_pattern = bool(m.cta_matches)

    m.density = _density(m.words)
    m.reading_level = _reading_level(m.avg_sentence_words)
    m.vocabulary_richness = round(len(set(lower_words)) / m.words, 3) if m.words else 0.0
    return m
