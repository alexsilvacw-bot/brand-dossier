"""Configuração global dos testes.

Importante: brand_dossier.config lê as variáveis de ambiente BRAND_DOSSIER_MOCK e
BRAND_DOSSIER_DATA no momento do import (elas definem DATA_DIR, IMAGES_DIR e DB_PATH
como constantes de módulo). Por isso, essas variáveis precisam estar definidas ANTES
que qualquer submódulo de brand_dossier seja importado por qualquer teste.

O jeito mais simples e robusto é fazer isso aqui, no topo do conftest.py: o pytest
sempre importa o conftest.py de um diretório antes de coletar/importar os módulos de
teste desse diretório. Usamos um diretório temporário dedicado (criado com
tempfile.mkdtemp) para os dados, de forma que os testes nunca leiam nem escrevam em
data/ do projeto real.
"""

from __future__ import annotations

import os
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="brand_dossier_tests_")

# setdefault: se o usuário já exportou essas variáveis no ambiente, respeita a escolha
# dele, mas garante que exista um valor sensato para rodar a suíte sem chamar a API.
os.environ.setdefault("BRAND_DOSSIER_MOCK", "1")
os.environ.setdefault("BRAND_DOSSIER_DATA", _TEST_DATA_DIR)

import pytest  # noqa: E402

from brand_dossier import db, pipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_data_dir():
    """Garante um banco/dados limpos a cada teste, isolados no diretório temporário."""
    pipeline.reset_data()
    db.init_db()
    yield
