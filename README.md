# Brand Dossier

MVP que analisa posts de social media (imagem + legenda) usando Claude e gera um dossiê de comunicação de marca: um relatório que descreve padrões de copy, tom de voz, temas de conteúdo e estilo visual a partir de um conjunto de posts cadastrados. A interface é feita em Streamlit e os dados ficam salvos localmente em SQLite. O app pode falar com o Claude por dois motores diferentes, ver a seção "Dois motores" abaixo.

## Instalação

Requer Python 3.11 ou superior. Usando [uv](https://github.com/astral-sh/uv):

```bash
uv venv
uv pip install -e ".[dev]"
```

Isso instala as dependências do projeto (`anthropic`, `streamlit`, `pydantic`, `pillow`, `python-dotenv`) e as de desenvolvimento (`pytest`).

## Dois motores

O app fala com o Claude por um de dois motores, escolhido na barra lateral ("Motor"):

- **Claude Code** (`claude_code`): chama o binário `claude` já instalado na máquina, no modo não interativo (`claude -p`), usando a assinatura do usuário. Não precisa de chave de API. Requisitos: Claude Code instalado (`npm install -g @anthropic-ai/claude-code`) e logado (rode `claude` no terminal e depois `/login`). O consumo entra na cota da assinatura; o valor em dólares mostrado no app é apenas um equivalente em preço de API, não uma cobrança real. É o motor padrão quando o binário `claude` é encontrado no PATH.
- **API** (`api`): usa o SDK oficial da Anthropic com uma chave de API, cobrando por uso (ver seção seguinte). É o padrão quando o binário `claude` não é encontrado no PATH.

A variável de ambiente `BRAND_DOSSIER_ENGINE` força a escolha do padrão, com os valores `claude_code` ou `api`. Sem ela, o app detecta automaticamente se o `claude` está no PATH. Em qualquer um dos dois casos, o motor ainda pode ser trocado manualmente na barra lateral a cada sessão.

Tempos observados: cerca de 60 a 90 segundos para analisar um lote de 3 posts com Claude Haiku 4.5, e cerca de 90 segundos para gerar o dossiê com Claude Sonnet 5, usando o motor Claude Code.

## Configurando a chave da API

A chave de API só é necessária se você for usar o motor **API** (`api`). Com o motor Claude Code, pule esta seção.

Crie um arquivo `.env` na raiz do projeto com a chave da Anthropic:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Um modelo está disponível em `.env.example`. Se preferir não usar `.env`, a chave também pode ser informada diretamente na barra lateral da aplicação (fica só na sessão do navegador; não é salva em disco).

## Como rodar

```bash
.venv/bin/streamlit run app.py
```

A aplicação abre no navegador. Pela barra lateral é possível escolher o motor, os modelos, o nível de esforço de cada etapa e a marca ativa.

## Como testar pela primeira vez

1. Suba o app com `.venv/bin/streamlit run app.py`.
2. Na barra lateral, confira a mensagem sobre o motor: se o Claude Code estiver instalado e logado, aparece "Claude Code encontrado. Usa sua assinatura, sem custo de API." Caso contrário, troque para o motor API e informe a chave.
3. Na aba de marca, cadastre uma marca (nome, resumo, produtos e público).
4. Na aba de posts, envie de 5 a 8 imagens e cole a legenda de cada uma (ou use o CSV opcional, ver seção abaixo).
5. Analise os posts primeiro com Claude Haiku 4.5, o modelo mais barato, para validar o fluxo.
6. Depois, gere o dossiê com Claude Sonnet 5 ou Claude Opus 5 na etapa de síntese.

## Como funciona o pipeline

A análise de cada marca passa por três estágios:

1. **Métricas determinísticas da legenda** (`brand_dossier/metrics.py`): sem chamar o modelo, o texto da legenda é processado com expressões regulares para extrair contagem de palavras e frases, densidade, emojis, hashtags, menções, URLs, uso de maiúsculas, presença de padrões de CTA (call to action), estratégia de pronome (foco no leitor vs. foco na marca) e estilo de pontuação. Essas métricas entram no prompt da etapa seguinte como fatos, não como opinião do modelo.
2. **Análise por post em JSON estruturado** (`brand_dossier/llm.py` e `brand_dossier/schemas.py`): para cada post, a imagem e a legenda (mais as métricas da etapa 1) são enviadas ao Claude, que devolve uma análise estruturada e validada contra um schema Pydantic (`PostAnalysis`), incluindo framework de copy, gancho, tipo de CTA, gatilhos de persuasão, tom em seis dimensões, tema, pilar de conteúdo, persona-alvo, formato visual e coerência entre imagem e legenda, entre outros campos. O resultado é salvo no banco por post.
3. **Agregação e síntese do dossiê** (`brand_dossier/aggregate.py` e `brand_dossier/pipeline.py`): as análises de todos os posts da marca são agregadas de forma determinística (frequências, médias, distribuições) e esse resumo é enviado a um modelo de síntese, que escreve o dossiê final em Markdown. O dossiê é versionado e exportado em `.md` e `.json`.

## Modelos disponíveis

Definidos em `brand_dossier/config.py`, com preço por 1 milhão de tokens (entrada/saída):

| Modelo | Preço (US$ in/out por 1M) | Uso recomendado |
| --- | --- | --- |
| Claude Haiku 4.5 | $1 / $5 | Barato, para testar o fluxo |
| Claude Sonnet 5 | $2 / $10 | Bom custo para a análise post a post (padrão da etapa 2) |
| Claude Opus 5 | $5 / $25 | Recomendado para a síntese do dossiê (padrão da etapa 3) |
| Claude Fable 5.1 | $10 / $50 | Mais capaz e mais caro, para síntese premium |

Os níveis de esforço disponíveis (quando o modelo suporta) são `low`, `medium`, `high`, `xhigh` e `max`.

## Modo simulado (sem gastar API)

Definindo a variável de ambiente `BRAND_DOSSIER_MOCK=1`, o aplicativo não faz nenhuma chamada real à API: a análise por post e a síntese do dossiê retornam respostas simuladas, úteis para testar a interface e o pipeline sem custo. É o modo usado pela suíte de testes automatizados.

## Onde ficam os dados

Tudo é salvo em `data/` na raiz do projeto:

- `data/brand_dossier.sqlite3`: marcas, posts, análises e dossiês.
- `data/images/<id-da-marca>/`: imagens dos posts enviados.
- `data/exports/<marca>/`: dossiês exportados em `.md` e `.json`, um par de arquivos por versão.

O local pode ser alterado com a variável de ambiente `BRAND_DOSSIER_DATA`, apontando para outro diretório.

## CSV opcional de legendas

Na aba de posts é possível enviar, junto com as imagens, um CSV para preencher as legendas automaticamente. O arquivo deve ter as colunas `filename` (nome do arquivo de imagem) e `caption` (texto da legenda); também são aceitos os nomes em português `arquivo`/`imagem` e `legenda`. O separador pode ser vírgula, ponto e vírgula ou tabulação.

## Como rodar os testes

```bash
.venv/bin/python -m pytest
```

Os testes (em `tests/`) cobrem métricas de legenda, geração e validação do schema JSON estrito, agregação, escolha do motor padrão, o motor Claude Code (com o subprocesso simulado, sem chamar o binário real) e o fluxo completo do pipeline (banco, análise, dossiê e exportação), sempre em modo simulado (`BRAND_DOSSIER_MOCK=1`) ou com dependências externas substituídas, sem chamar a API real nem o `claude` de verdade.

## Limitações do MVP

- Não há autenticação nem separação de usuários: qualquer pessoa com acesso ao aplicativo vê e edita todas as marcas salvas no banco local.
- O banco é SQLite em arquivo único; não é pensado para uso concorrente por várias pessoas ao mesmo tempo.
- Só imagens são analisadas como conteúdo visual; não há suporte a vídeo ou carrossel com múltiplas imagens por post.
- A qualidade da análise depende inteiramente do modelo de linguagem: erros de leitura de imagem, alucinação de detalhes ou classificações equivocadas nas listas fechadas de taxonomia não são verificados automaticamente.
- Não há edição manual da análise gerada por post nem versionamento por post (só o dossiê final é versionado).
- A exclusão de marca ou de post é definitiva, sem lixeira ou confirmação além do próprio clique na interface.
