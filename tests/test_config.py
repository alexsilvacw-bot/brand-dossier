"""Testes de brand_dossier.config: escolha do motor padrão (default_engine)."""

from __future__ import annotations

import shutil

from brand_dossier import config


def test_default_engine_respeita_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("BRAND_DOSSIER_ENGINE", "api")
    assert config.default_engine() == "api"


def test_default_engine_sem_variavel_e_sem_claude_no_path_usa_api(monkeypatch):
    monkeypatch.delenv("BRAND_DOSSIER_ENGINE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert config.default_engine() == "api"


def test_default_engine_sem_variavel_e_com_claude_no_path_usa_claude_code(monkeypatch):
    monkeypatch.delenv("BRAND_DOSSIER_ENGINE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/x/claude" if name == "claude" else None)
    assert config.default_engine() == "claude_code"
