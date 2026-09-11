"""Testes de brand_dossier.schemas: JSON Schema estrito e validação do mock de análise."""

from __future__ import annotations

import json
from typing import Any

from brand_dossier.llm import _mock_analysis
from brand_dossier.schemas import PostAnalysis, strict_json_schema


def _walk_objects(node: Any):
    """Gera todo sub-nó do tipo objeto (dict com type == 'object')."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _walk_objects(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_objects(item)


def test_schema_nao_contem_ref_nem_defs():
    schema = strict_json_schema(PostAnalysis)
    dumped = json.dumps(schema)
    assert "$ref" not in dumped
    assert "$defs" not in dumped
    assert "$defs" not in schema


def test_todo_objeto_tem_additional_properties_false_e_required_completo():
    schema = strict_json_schema(PostAnalysis)
    objetos = list(_walk_objects(schema))
    assert objetos, "esperava encontrar ao menos um nó do tipo objeto no schema"

    for obj in objetos:
        assert obj.get("additionalProperties") is False, obj
        if "properties" in obj:
            assert obj.get("required") == list(obj["properties"].keys()), obj


def test_mock_analysis_valida_no_schema_pydantic():
    data = _mock_analysis("qualquer legenda")
    # Não deve levantar erro de validação: os dados do mock respeitam o schema real.
    parsed = PostAnalysis.model_validate(data)
    assert parsed.resumo
    assert parsed.visual.formato
    assert parsed.legenda.framework
    assert parsed.conteudo.pilar
