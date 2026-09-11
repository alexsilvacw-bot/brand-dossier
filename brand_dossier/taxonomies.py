"""Listas fechadas usadas na análise por post.

Fontes de inspiração: creative-intel (tipos de valor), copy-that-sells (ganchos e vozes),
CoppieGPT e 10x-Content-Expert (frameworks de copy), tone-of-voice-analyzer (registro de Joos),
Eugene Schwartz (estágios de consciência).
"""

COPY_FRAMEWORKS = [
    "AIDA",            # Atenção, Interesse, Desejo, Ação
    "PAS",             # Problema, Agitação, Solução
    "BAB",             # Antes, Depois, Ponte
    "FAB",             # Feature, Advantage, Benefit
    "4Ps",             # Promise, Picture, Proof, Push
    "PASTOR",          # Problema, Amplificar, Solução, Transformação, Oferta, Resposta
    "Hook-Story-Offer",
    "Storytelling",    # narrativa sem estrutura de venda explícita
    "Lista",           # enumeração de dicas, passos ou itens
    "Pergunta-Resposta",
    "Depoimento",      # prova social direta
    "Anúncio-Direto",  # oferta ou informação sem estrutura persuasiva
    "Educacional",     # explica um conceito ou processo
    "Institucional",   # valores, missão, bastidores
    "Nenhum",          # legenda mínima ou ausente
]

HOOK_TYPES = [
    "dor",               # nomeia um problema do público
    "contra-intuitivo",  # afirmação que contraria o senso comum
    "numerico",          # número, estatística, dado
    "suspense",          # curiosidade, promessa de revelação
    "ressonancia",       # identificação emocional, "você também..."
    "pergunta",
    "afirmacao-ousada",
    "noticia",           # novidade, lançamento, anúncio
    "prova-social",      # resultado de cliente, autoridade
    "direto-ao-produto", # abre falando do produto
    "nenhum",
]

CTA_TYPES = [
    "compra",
    "link-na-bio",
    "comentario",
    "compartilhamento",
    "salvar",
    "marcar-alguem",
    "seguir",
    "contato-direto",   # WhatsApp, DM, ligação
    "visitar",          # loja, evento, site
    "inscricao",        # cadastro, evento, newsletter
    "nenhum",
]

PERSUASION_TRIGGERS = [
    "escassez",
    "urgencia",
    "prova-social",
    "autoridade",
    "reciprocidade",
    "afinidade",
    "novidade",
    "curiosidade",
    "medo-de-perder",
    "pertencimento",
    "aspiracao",
    "seguranca",
]

VALUE_PROPOSITION_TYPES = [
    "economico",          # preço, economia, ROI
    "eficiencia",         # tempo, produtividade
    "reducao-de-risco",   # garantia, segurança, confiabilidade
    "acesso-conveniencia",
    "performance",        # resultado superior, potência
    "alivio-emocional",   # paz, tranquilidade
    "identidade-status",
    "prova-social",
    "novidade-curiosidade",
    "urgencia-escassez",
    "nenhum",
]

CONTENT_PILLARS = [
    "produto",
    "educativo",
    "institucional",
    "promocional",
    "prova-social",
    "bastidores",
    "entretenimento",
    "engajamento",
    "sazonal",
    "recrutamento",
]

REGISTERS = [  # escala de Joos
    "formal",
    "consultivo",
    "coloquial",
    "intimo",
]

VOICE_LABELS = [  # inspirado no voice bank de copy-that-sells
    "confiante-seco",
    "intimo-baixo",
    "manifesto",
    "caseiro-lento",
    "cumplice",
    "autoridade-sobria",
    "rebelde-debochado",
    "fundador-narrador",
    "tecnico-preciso",
    "engracado-provocador",
    "direto-comerciante",
    "servico-publico-grave",
    "entusiasta-vendedor",
    "amigo-proximo",
]

AWARENESS_STAGES = [  # Eugene Schwartz
    "inconsciente",
    "consciente-do-problema",
    "consciente-da-solucao",
    "consciente-do-produto",
    "mais-consciente",
]

VISUAL_FORMATS = [
    "foto-produto",
    "foto-lifestyle",
    "foto-pessoas",
    "foto-campo-operacao",  # equipamento em uso, obra, lavoura
    "ilustracao",
    "grafico-com-texto",    # card tipográfico, citação, dica
    "infografico",
    "captura-de-tela",
    "meme",
    "capa-de-video",
    "colagem",
    "outro",
]

CONTENT_DEPTH = ["superficial", "medio", "profundo"]
AMOUNT_LEVELS = ["nenhum", "pouco", "medio", "muito"]
CONFIDENCE_LEVELS = ["alta", "media", "baixa"]
