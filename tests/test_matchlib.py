"""Server-side match primitives (matchlib): pure, no server/DB needed."""
from __future__ import annotations

from openreagent import loader, matchlib
from openreagent.recipes import get_recipe
from openreagent.solidity import parse_source


def setup_module(_):
    loader.load_builtins()


def test_compare_digest_exact_and_normalization_family():
    assert matchlib.compare({"digest": "ab" * 32, "normalization": "source-text:strip"},
                            {"digest": "AB" * 32, "normalization": "source-text"}) == 1.0
    # different normalization family -> no match
    assert matchlib.compare({"digest": "ab" * 32, "normalization": "bytecode:x"},
                            {"digest": "ab" * 32, "normalization": "source-text"}) == 0.0


def test_compare_minhash_jaccard():
    assert matchlib.compare({"minhash": [1, 2, 3, 4]}, {"minhash": [1, 2, 3, 4]}) == 1.0
    # different length -> not comparable
    assert matchlib.compare({"minhash": [1, 2, 3]}, {"minhash": [1, 2]}) == 0.0


def test_compare_hashes_containment():
    # stored ⊆ candidate
    assert matchlib.compare({"hashes": [1, 2]}, {"hashes": [1, 2, 3, 4]}) == 1.0
    assert matchlib.compare({"hashes": [1, 2, 3, 4]}, {"hashes": [1, 2]}) == 0.5


def test_candidate_values_function_skeleton():
    rec = get_recipe("function-skeleton")
    code = [parse_source("C.sol", "contract C { function f() public { uint x = y; } }")]
    cv = matchlib.candidate_values(rec, code)
    assert cv and any(label.endswith("#f") for label, _ in cv)
    assert all("digest" in v for _, v in cv)


def test_candidate_values_unknown_recipe_empty():
    class _R:
        name = "nope"
        extractor = None
    assert matchlib.candidate_values(_R(), []) == []
