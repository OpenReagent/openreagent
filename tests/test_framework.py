"""Framework-level guards: registries, shapes, conformance, loadability."""
from __future__ import annotations

import pytest

from openreagent import loader
from openreagent.models import Signature
from openreagent.recipes import Status, all_recipes, get_recipe
from openreagent.shapes import conforms, get_shape


def setup_module(_):
    loader.load_builtins()


def test_recipes_load_and_self_describe():
    recs = all_recipes()
    names = {r.name for r in recs}
    expected = {
        "internal-absence", "canonical-divergence", "operand-mismatch",
        "operator-direction", "unbound-caller-value", "ordering-violation",
        "aggregated-state", "generic-slot", "bytecode-hash", "ast-sketch",
    }
    assert expected <= names
    for r in recs:
        d = r.describe()
        assert d["name"] == r.name
        assert "status" in d and d["status"] in {s.value for s in Status}
        # Invariant: a matcher never uses an LLM.
        assert d["matcher"]["uses_llm"] is False
        # Every recipe references a registered shape.
        assert get_shape(r.shape.name, r.shape.version) is not None


def test_status_map_defaults():
    assert get_recipe("internal-absence").default_enabled is True
    assert get_recipe("canonical-divergence").default_enabled is True
    assert get_recipe("bytecode-hash").default_enabled is False
    assert get_recipe("ast-sketch").default_enabled is False
    assert get_recipe("generic-slot").default_enabled is False


def test_slot_spec_conformance():
    assert conforms({"slots": {"operation": "access_control"}}, "slot-spec")
    assert conforms({"slots": {}, "freeform": "anything"}, "slot-spec")
    assert not conforms({"no_slots": 1}, "slot-spec")


def test_bytecode_hash_conformance():
    assert conforms({"digest": "ab" * 32, "normalization": "x"}, "bytecode-hash")
    assert conforms({"digest": "0x" + "cd" * 32, "normalization": "x"}, "bytecode-hash")
    assert not conforms({"digest": "zz", "normalization": "x"}, "bytecode-hash")
    assert not conforms({"digest": "ab" * 32, "normalization": ""}, "bytecode-hash")


def test_ast_sketch_conformance():
    assert conforms({"ngram": 5, "minhash": [1, 2, 3]}, "ast-sketch")
    assert not conforms({"ngram": 0, "minhash": [1]}, "ast-sketch")
    assert not conforms({"ngram": 5, "minhash": []}, "ast-sketch")
    assert not conforms({"ngram": 5, "minhash": [-1]}, "ast-sketch")


def test_signature_record_roundtrip():
    raw = {
        "id": "sig-x",
        "recipe": {"name": "internal-absence", "version": "1.0.0"},
        "value": {"slots": {"operation": "access_control"}},
        "provenance": [{
            "source_kind": "audit_report",
            "source_ref": "x",
            "extracted_by": {"recipe": "internal-absence", "version": "1.0.0",
                             "timestamp": "2026-06-01T00:00:00Z"},
        }],
    }
    sig = Signature.from_dict(raw)
    assert sig.id == "sig-x"
    assert sig.to_dict()["recipe"]["name"] == "internal-absence"


def test_signature_requires_provenance():
    with pytest.raises(Exception):
        Signature.from_dict({
            "id": "x",
            "recipe": {"name": "a", "version": "1.0.0"},
            "value": {},
            "provenance": [],
        })
