"""The hashable clone recipes added in Card 5b: function-skeleton, snippet-match,
bytecode-sketch. Hermetic — no toolchain needed except pyevmasm for the bytecode
recipe (skipped if absent)."""
from __future__ import annotations

import pathlib
import types

import pytest

from openreagent import loader
from openreagent.building import Artifact, BuildResult, BuildStatus
from openreagent.codeview import CodeView
from openreagent.recipes import get_recipe
from openreagent.solidity import load_target, parse_source

HERE = pathlib.Path(__file__).resolve().parent
VANILLA = HERE / "fixtures" / "projects" / "vanilla_app"


def setup_module(_):
    loader.load_builtins()


def _sig(i):
    return types.SimpleNamespace(id=i)


def test_clone_recipes_registered():
    names = {r.name for r in __import__("openreagent.recipes", fromlist=["all_recipes"]).all_recipes()}
    assert {"function-skeleton", "snippet-match", "bytecode-sketch"} <= names


# ---- function-skeleton ----

def test_function_skeleton_self_match():
    rec = get_recipe("function-skeleton")
    code = "function f(uint x) public { uint y = x; require(x == y); }"
    value = rec.extractor.extract({"source": code})
    assert value["digest"] and value["length"] >= 1
    sources = [parse_source("T.sol", f"contract T {{ {code} }}")]
    findings = rec.matcher.match(value, sources, _sig("fs"))
    assert findings and findings[0].recipe == "function-skeleton"
    assert findings[0].function == "f"


def test_function_skeleton_type2_rename_match():
    rec = get_recipe("function-skeleton")
    a = "function f(uint x) public { uint y = x; require(x == y); }"
    b = "function transfer(uint amt) public { uint bal = amt; require(amt == bal); }"
    value = rec.extractor.extract({"source": a})
    sources = [parse_source("T.sol", f"contract T {{ {b} }}")]
    assert rec.matcher.match(value, sources, _sig("fs2"))  # renamed clone still matches


def test_function_skeleton_no_match_when_different():
    rec = get_recipe("function-skeleton")
    value = rec.extractor.extract({"source": "function f() public { selfdestruct(msg.sender); }"})
    sources = [parse_source("T.sol", "contract T { function g() public { uint z = 0; } }")]
    assert rec.matcher.match(value, sources, _sig("fs3")) == []


# ---- snippet-match ----

def test_snippet_match_containment_fires():
    rec = get_recipe("snippet-match")
    snippet = "require(msg.sender == owner); balances[msg.sender] = amount;"
    value = rec.extractor.extract({"source": snippet, "ngram": 3})
    target = ("contract V { function f() public { uint a = b; "
              "require(msg.sender == owner); balances[msg.sender] = amount; emit Done(); } }")
    findings = rec.matcher.match(value, [parse_source("V.sol", target)], _sig("sm"))
    assert findings and findings[0].recipe == "snippet-match"
    assert findings[0].details["containment"] >= 0.8


def test_snippet_match_absent():
    rec = get_recipe("snippet-match")
    value = rec.extractor.extract(
        {"source": "selfdestruct(msg.sender); uint a = b; uint c = d;", "ngram": 3})
    sources = [parse_source("V.sol", "contract V { function f() public { return; } }")]
    assert rec.matcher.match(value, sources, _sig("sm2")) == []


# ---- bytecode-sketch ----

def _has_pyevmasm() -> bool:
    try:
        import pyevmasm  # noqa: F401
    except ImportError:
        return False
    return True


_BYTECODE = "6001600260030160045560056006025560075500"  # ~13 opcodes


@pytest.mark.skipif(not _has_pyevmasm(), reason="pyevmasm (bytecode extra) not installed")
def test_bytecode_sketch_self_match():
    rec = get_recipe("bytecode-sketch")
    value = rec.extractor.extract({"bytecode": _BYTECODE, "ngram": 3})
    assert value["minhash"]
    src = load_target(VANILLA)[0]
    art = Artifact(source=src.path, contract="C", bytecode=_BYTECODE)
    code = CodeView([src], BuildResult("vanilla", BuildStatus.OK, artifacts=[art]))
    findings = rec.matcher.match(value, code, _sig("bs"))
    assert findings and findings[0].details["contract"] == "C"
    # Without a build (plain list, no artifacts) the bytecode path finds nothing.
    assert rec.matcher.match(value, [src], _sig("bs")) == []


@pytest.mark.skipif(not _has_pyevmasm(), reason="pyevmasm not installed")
def test_bytecode_sketch_no_match_on_different_bytecode():
    rec = get_recipe("bytecode-sketch")
    value = rec.extractor.extract({"bytecode": _BYTECODE, "ngram": 3})
    other = "60ff60fe60fd0360fc5560fb60fa0a5560f95500"  # different opcodes (DIV, EXP, …)
    src = load_target(VANILLA)[0]
    art = Artifact(source=src.path, contract="C", bytecode=other)
    code = CodeView([src], BuildResult("vanilla", BuildStatus.OK, artifacts=[art]))
    # Low Jaccard → below tau → no finding.
    assert rec.matcher.match(value, code, _sig("bs2")) == []
