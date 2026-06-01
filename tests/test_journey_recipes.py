"""Journey recipes (bytecode-hash, ast-sketch) and the hashing primitives."""
from __future__ import annotations

from openreagent import loader
from openreagent._hashing import jaccard, keccak256, minhash, shingle
from openreagent.recipes import get_recipe
from openreagent.solidity import load_target


def setup_module(_):
    loader.load_builtins()


def test_keccak256_known_vector():
    # keccak-256 of the empty string (Ethereum variant).
    assert keccak256(b"") == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"


def test_minhash_jaccard_self_identity():
    sh = shingle(["a", "b", "c", "d", "e", "f"], 3)
    m = minhash(sh, num_perm=64)
    assert jaccard(m, m) == 1.0


def test_bytecode_hash_self_clone(fixtures_path):
    recipe = get_recipe("bytecode-hash")
    token = fixtures_path / "Token.sol"
    value = recipe.extractor.extract({"source_path": str(token)})
    assert value["normalization"].startswith("source-text")
    sources = load_target(str(token))

    class _Sig:
        id = "sig-clone"

    findings = recipe.matcher.match(value, sources, _Sig())
    assert len(findings) == 1
    assert findings[0].score == 1.0
    assert findings[0].tier == "HIGH"


def test_ast_sketch_self_similarity(fixtures_path):
    recipe = get_recipe("ast-sketch")
    oracle = fixtures_path / "PriceOracle.sol"
    value = recipe.extractor.extract({"source_path": str(oracle)})
    sources = load_target(str(oracle))

    class _Sig:
        id = "sig-sketch"

    findings = recipe.matcher.match(value, sources, _Sig())
    assert len(findings) == 1
    assert findings[0].score >= 0.99
