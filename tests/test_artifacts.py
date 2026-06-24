"""The unified scan input (CodeView) and the artifact-fed recipe paths.

These tests are hermetic: they build a CodeView from *synthetic* artifacts, so no
solc/forge/hardhat is required to exercise bytecode-hash (bytecode) and ast-sketch
(AST) matching.
"""
from __future__ import annotations

import pathlib
import types

from openreagent import loader
from openreagent.building import Artifact, BuildResult, BuildStatus
from openreagent.codeview import CodeView, _suffix_keys
from openreagent.matching import abi_for, artifacts_for, ast_for, bytecode_for
from openreagent.recipes import get_recipe
from openreagent.solidity import load_target

HERE = pathlib.Path(__file__).resolve().parent
VANILLA = HERE / "fixtures" / "projects" / "vanilla_app"


def setup_module(_):
    loader.load_builtins()


def _src(path="/x/y/contracts/Counter.sol", basename="Counter.sol"):
    return types.SimpleNamespace(path=path, basename=basename, functions=[], text="")


# ---- CodeView reconciliation ----

def test_suffix_keys_most_specific_first():
    assert _suffix_keys("a/b/c.sol") == ["a/b/c.sol", "b/c.sol", "c.sol"]
    assert _suffix_keys("Counter.sol") == ["Counter.sol"]


def test_codeview_reconciles_relative_artifact_to_absolute_source():
    # Hardhat names a source "contracts/Counter.sol"; the SourceFile path is absolute.
    art = Artifact(source="contracts/Counter.sol", contract="Counter", bytecode="ab", ast={"nodeType": "SourceUnit"})
    build = BuildResult("hardhat", BuildStatus.OK, artifacts=[art])
    src = _src()
    code = CodeView([src], build)
    assert code.artifacts_for(src) == [art]
    assert code.ast_for(src) == {"nodeType": "SourceUnit"}


def test_codeview_behaves_as_source_list():
    src = _src()
    code = CodeView([src], None)
    assert len(code) == 1 and code[0] is src  # backward-compatible list


def test_matching_helpers_empty_on_plain_list():
    src = _src()
    assert artifacts_for([src], src) == []
    assert ast_for([src], src) is None
    assert bytecode_for([src], src) == []
    assert abi_for([src], src) == []


def test_matching_helpers_read_codeview():
    art = Artifact(source="contracts/Counter.sol", contract="Counter",
                   bytecode="6080", ast={"nodeType": "SourceUnit"}, abi=[{"type": "function", "name": "f"}])
    code = CodeView([_src()], BuildResult("hardhat", BuildStatus.OK, artifacts=[art]))
    src = code[0]
    assert bytecode_for(code, src) == [("Counter", "6080")]
    assert abi_for(code, src) == [{"type": "function", "name": "f"}]


# ---- bytecode-hash: bytecode path ----

def test_bytecode_hash_matches_compiled_bytecode():
    rec = get_recipe("bytecode-hash")
    bc = "60806040" * 4  # contrived creation bytecode (even-length hex)
    value = rec.extractor.extract({"bytecode": bc})
    assert value["normalization"].startswith("bytecode")

    src = load_target(VANILLA)[0]
    art = Artifact(source=src.path, contract="Counter", bytecode=bc)
    code = CodeView([src], BuildResult("vanilla", BuildStatus.OK, compiler="0.8.19", artifacts=[art]))
    sig = types.SimpleNamespace(id="sig-bc", value=value)

    findings = rec.matcher.match(value, code, sig)
    assert findings and findings[0].recipe == "bytecode-hash"
    assert findings[0].details["contract"] == "Counter"

    # Without a build (plain list / no artifacts) the bytecode path finds nothing.
    assert rec.matcher.match(value, [src], sig) == []


def test_bytecode_hash_no_match_on_different_bytecode():
    rec = get_recipe("bytecode-hash")
    value = rec.extractor.extract({"bytecode": "60806040" * 4})
    src = load_target(VANILLA)[0]
    other = Artifact(source=src.path, contract="Counter", bytecode="deadbeef" * 4)
    code = CodeView([src], BuildResult("vanilla", BuildStatus.OK, artifacts=[other]))
    sig = types.SimpleNamespace(id="x", value=value)
    assert rec.matcher.match(value, code, sig) == []


# ---- ast-sketch: AST basis ----

_AST = {
    "nodeType": "SourceUnit",
    "nodes": [
        {"nodeType": "ContractDefinition", "nodes": [
            {"nodeType": "FunctionDefinition", "body": {"nodeType": "Block", "statements": [
                {"nodeType": "ExpressionStatement"}]}}]}],
}


def test_ast_sketch_extracts_ast_basis():
    rec = get_recipe("ast-sketch")
    value = rec.extractor.extract({"ast": _AST})
    assert value["basis"] == "ast"
    assert value["minhash"]


def test_ast_sketch_matches_via_real_ast():
    rec = get_recipe("ast-sketch")
    value = rec.extractor.extract({"ast": _AST})  # basis "ast"
    src = load_target(VANILLA)[0]
    art = Artifact(source=src.path, contract="Counter", ast=_AST)
    code = CodeView([src], BuildResult("vanilla", BuildStatus.OK, artifacts=[art]))
    sig = types.SimpleNamespace(id="sig-ast", value=value)

    findings = rec.matcher.match(value, code, sig)
    assert findings  # identical AST => similarity 1.0 >= tau
    assert findings[0].details["basis"] == "ast"

    # An AST-basis signature with no built AST available simply does not fire.
    assert rec.matcher.match(value, [src], sig) == []


def test_ast_sketch_lexical_basis_still_works():
    rec = get_recipe("ast-sketch")
    src = load_target(VANILLA)[0]
    value = rec.extractor.extract({"source": src.text})  # basis lexical
    assert value["basis"] == "lexical-tokens"
    sig = types.SimpleNamespace(id="sig-lex", value=value)
    # Lexical basis works on a plain list (no build needed).
    findings = rec.matcher.match(value, [src], sig)
    assert findings and findings[0].details["basis"] == "lexical-tokens"
