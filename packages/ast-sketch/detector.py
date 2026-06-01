"""Package: ast-sketch/1.0.0  (self-contained shape + recipe)

A near-duplicate detector over a lexical token stream. Registers its own shape
(``ast-sketch/v1``) and recipe in one entry module. The value is a MinHash
signature of token n-grams; matching estimates Jaccard similarity and flags files
above a threshold ``tau``. It is a journey recipe (off by default).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from openreagent._hashing import jaccard, minhash, shingle
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


# ---- recipe ----

class AstSketchExtractor(Extractor):
    impl = "flatten+minhash"
    version = "1.0.0"
    uses_llm = False
    params = {"ngram": DEFAULT_NGRAM, "num_perm": DEFAULT_NUM_PERM}

    def extract(self, source: dict) -> dict:
        text = source.get("source")
        if text is None and source.get("source_path"):
            from pathlib import Path

            text = Path(source["source_path"]).read_text(encoding="utf-8", errors="replace")
        if text is None:
            raise ValueError("ast-sketch extract needs 'source' or 'source_path'")
        ngram = int(source.get("ngram", DEFAULT_NGRAM))
        num_perm = int(source.get("num_perm", DEFAULT_NUM_PERM))
        shingles = shingle(code_tokens(text), ngram)
        return {"ngram": ngram, "minhash": minhash(shingles, num_perm=num_perm)}


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
        num_perm = len(sig_minhash)
        tau = float(self.params.get("tau", 0.7))
        findings = []
        for src in sources:
            shingles = shingle(code_tokens(src.text), ngram)
            sim = jaccard(sig_minhash, minhash(shingles, num_perm=num_perm))
            if sim >= tau:
                fn0 = src.functions[0] if src.functions else None
                findings.append(make_finding(
                    NAME, VERSION, signature, src,
                    fn0 or _Pseudo(src.basename), (fn0.start_line if fn0 else 1),
                    round(sim, 3),
                    message=(f"near-duplicate of signature {getattr(signature, 'id', '?')} "
                             f"(estimated similarity {sim:.2f} >= tau {tau})"),
                    details={"similarity": round(sim, 3), "ngram": ngram, "tau": tau},
                ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="ast-sketch", version="1.0.0"),
    extractor=AstSketchExtractor(), matcher=AstSketchMatcher(),
    status=Status.JOURNEY,
    note="lightly modified near-duplicates; cheap deterministic, off by default",
))
