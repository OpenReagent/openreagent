"""Package: ast-sketch/1.0.0  (self-contained shape + recipe)

A near-duplicate detector. The value is a MinHash signature; matching estimates
Jaccard similarity and flags files above a threshold ``tau``. A journey recipe
(off by default).

The signature's ``basis`` records what was shingled: ``"ast"`` (a sequence of
solc AST node types — used when the target was built and an AST is available) or
``"lexical-tokens"`` (the dependency-free token stream — the fallback). Only
signatures of the **same basis** are comparable.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from openreagent._hashing import jaccard, minhash, shingle
from openreagent.matching import ast_for
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import make_finding
from openreagent.shapes import Shape, ShapeRef, register_shape
from openreagent.solidity import code_tokens

NAME = "ast-sketch"
VERSION = "1.0.0"
DEFAULT_NGRAM = 5
DEFAULT_NUM_PERM = 64
_UINT64_MAX = 2**64 - 1


# ---- shape: ast-sketch/v1 ----

class AstSketchV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ngram: int
    minhash: list[int]
    basis: str = "lexical-tokens"  # "ast" | "lexical-tokens"

    @field_validator("ngram")
    @classmethod
    def _ngram_pos(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ngram must be >= 1")
        return v

    @field_validator("minhash")
    @classmethod
    def _uint64(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("minhash must be non-empty")
        for x in v:
            if not (0 <= x <= _UINT64_MAX):
                raise ValueError("minhash entries must be uint64")
        return v


register_shape(Shape(name="ast-sketch", version="1.0.0", model=AstSketchV1))


def _ast_node_types(node) -> list[str]:
    """Pre-order sequence of solc AST ``nodeType`` values. Deterministic."""
    seq: list[str] = []

    def walk(n):
        if isinstance(n, dict):
            nt = n.get("nodeType")
            if isinstance(nt, str):
                seq.append(nt)
            for k, v in n.items():
                if k != "nodeType":
                    walk(v)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(node)
    return seq


# ---- recipe ----

class AstSketchExtractor(Extractor):
    impl = "flatten+minhash"
    version = "1.0.0"
    uses_llm = False
    params = {"ngram": DEFAULT_NGRAM, "num_perm": DEFAULT_NUM_PERM}

    def extract(self, source: dict) -> dict:
        ngram = int(source.get("ngram", DEFAULT_NGRAM))
        num_perm = int(source.get("num_perm", DEFAULT_NUM_PERM))
        ast = source.get("ast")
        if isinstance(ast, dict):
            seq, basis = _ast_node_types(ast), "ast"
        else:
            text = source.get("source")
            if text is None and source.get("source_path"):
                from pathlib import Path

                text = Path(source["source_path"]).read_text(encoding="utf-8", errors="replace")
            if text is None:
                raise ValueError("ast-sketch extract needs 'ast', 'source', or 'source_path'")
            seq, basis = code_tokens(text), "lexical-tokens"
        return {"ngram": ngram, "minhash": minhash(shingle(seq, ngram), num_perm=num_perm),
                "basis": basis}


class _Pseudo:
    def __init__(self, name: str):
        self.name = name
        self.start_line = 1


class AstSketchMatcher(Matcher):
    impl = "minhash-sim"
    version = "1.0.0"
    uses_llm = False
    params = {"tau": 0.7}

    def match(self, value, sources, signature):
        ngram = int(value.get("ngram", DEFAULT_NGRAM))
        sig_minhash = value.get("minhash", [])
        if not sig_minhash:
            return []
        basis = value.get("basis", "lexical-tokens")
        num_perm = len(sig_minhash)
        tau = float(self.params.get("tau", 0.7))
        findings = []
        for src in sources:
            if basis == "ast":
                ast = ast_for(sources, src)
                if ast is None:
                    continue  # an AST-basis signature needs a built AST; skip without one
                seq = _ast_node_types(ast)
            else:
                seq = code_tokens(src.text)
            sim = jaccard(sig_minhash, minhash(shingle(seq, ngram), num_perm=num_perm))
            if sim >= tau:
                fn0 = src.functions[0] if src.functions else None
                findings.append(make_finding(
                    NAME, VERSION, signature, src,
                    fn0 or _Pseudo(src.basename), (fn0.start_line if fn0 else 1),
                    round(sim, 3),
                    message=(f"near-duplicate of signature {getattr(signature, 'id', '?')} "
                             f"(estimated similarity {sim:.2f} >= tau {tau}, basis {basis})"),
                    details={"similarity": round(sim, 3), "ngram": ngram, "tau": tau, "basis": basis},
                ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="ast-sketch", version="1.0.0"),
    extractor=AstSketchExtractor(), matcher=AstSketchMatcher(),
    status=Status.JOURNEY,
    note="lightly modified near-duplicates; cheap deterministic, off by default",
))
