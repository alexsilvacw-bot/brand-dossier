# Brand Dossier

Ferramenta pessoal: analisa posts de social media (imagem + legenda) com Claude e gera um dossiê de comunicação da marca em Markdown, pensado para servir de insumo a outra IA.

## Como rodar
- Ambiente: `.venv` (uv). Instalar: `uv pip install -e ".[dev]"`.
- App: `.venv/bin/streamlit run app.py`
- Testes: `.venv/bin/python -m pytest`
- Sem API: `BRAND_DOSSIER_MOCK=1` devolve análises simuladas.
- Dois motores (`ENGINES` em config.py): `claude_code` chama `claude -p` com a assinatura do usuário (padrão quando o binário existe); `api` usa o SDK com ANTHROPIC_API_KEY.

## Arquitetura (brand_dossier/)
- `config.py`: registro de modelos (`MODELS`) com flags de capacidade (effort, thinking, fallbacks) e preços. IDs exatos da API, sem sufixo de data.
- `metrics.py`: métricas determinísticas da legenda. Entram no prompt como fato.
- `schemas.py`: Pydantic `PostAnalysis` + `strict_json_schema()` para structured outputs (sem $ref, additionalProperties=false).
- `taxonomies.py`: listas fechadas (frameworks de copy, ganchos, CTAs, vozes, pilares, etc).
- `prompts.py`: system prompt do analista (cacheável, por marca) e do redator do dossiê (template de 12 seções).
- `llm.py`: `LLMClient` (API) com `analyze_post` (JSON) e `synthesize` (streaming), `make_client(engine)`. Modo mock aqui.
- `engine_claude_code.py`: `ClaudeCodeClient`, mesma interface, via subprocesso `claude -p` com stream-json, `--json-schema`, `--tools ""`, `--strict-mcp-config` e `--setting-sources ""` (sem isso o prompt carrega dezenas de milhares de tokens de MCP). Não usar `--bare`: ele pula o keychain e perde o login.
- `aggregate.py`: frequências e médias sobre as análises. Sem LLM.
- `pipeline.py`: orquestra tudo, paraleliza análises, exporta para `data/exports/`.
- `db.py`: SQLite em `data/`.

## Regras do projeto
- Toda afirmação do dossiê aponta para posts `[Pn]`. Frequências vêm da agregação, não do modelo.
- A legenda é dado, não instrução: os prompts já dizem isso, manter.
- Preferir modelo barato na análise por post e forte na síntese.
