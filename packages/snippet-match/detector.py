"""Package: snippet-match/1.0.0  (self-contained shape + recipe)

Sub-function snippet clone detector (ReDeBug / winnowing style). The signature is
the set of token n-gram hashes of a known-vulnerable *snippet* (often just a few
lines). A target matches when it **contains** enough of those n-grams — i.e. the
vulnerable snippet was pasted somewhere inside it, even within an otherwise
different function.

Deterministic and hashable (no LLM). Token-only, so it works on partial /
non-compiling source — the common shape of an audit finding. Journey recipe (off
by default).
"""
from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, field_validator

from openreagent._hashing import shingle
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import make_finding
from openreagent.shapes import Shape, ShapeRef, register_shape
from openreagent.solidity import code_tokens

NAME, VERSION = "snippet-match", "1.0.0"
DEFAULT_NGRAM = 4
_U64 = (1 << 64) - 1


# ---- shape: snippet-match/v1 ----

class SnippetMatchV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ngram: int
    hashes: list[int]

    @field_validator("ngram")
    @classmethod
    def _ngram_pos(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ngram must be >= 1")
        return v

    @field_validator("hashes")
    @classmethod
    def _uint64(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("hashes must be non-empty")
        for x in v:
            if not (0 <= x <= _U64):
                raise ValueError("hash entries must be uint64")
        return v


register_shape(Shape(name="snippet-match", version="1.0.0", model=SnippetMatchV1))


# ---- n-gram hashing ----

def _h(shingle_str: str) -> int:
    return int.from_bytes(hashlib.sha1(shingle_str.encode("utf-8")).digest()[:8], "big")


def _ngram_hashes(text: str, ngram: int) -> list[int]:
    return sorted({_h(s) for s in shingle(code_tokens(text), ngram)})


class _Pseudo:
    def __init__(self, name: str):
        self.name = name
        self.start_line = 1


# ---- recipe ----

class SnippetMatchExtractor(Extractor):
    impl = "ngram-set"
    version = "1.0.0"
    params = {"ngram": DEFAULT_NGRAM}

    def extract(self, source: dict) -> dict:
        text = source.get("source")
        if text is None and source.get("source_path"):
            from pathlib import Path

            text = Path(source["source_path"]).read_text(encoding="utf-8", errors="replace")
        if text is None:
            raise ValueError("snippet-match extract needs 'source' or 'source_path'")
        ngram = int(source.get("ngram", DEFAULT_NGRAM))
        hashes = _ngram_hashes(text, ngram)
        if not hashes:
            raise ValueError("snippet too short for the chosen ngram")
        return {"ngram": ngram, "hashes": hashes}


class SnippetMatchMatcher(Matcher):
    impl = "containment"
    version = "1.0.0"
    params = {"tau": 0.8}

    def match(self, value, sources, signature):
        sig = set(value.get("hashes", []))
        if not sig:
            return []
        ngram = int(value.get("ngram", DEFAULT_NGRAM))
        tau = float(self.params.get("tau", 0.8))
        findings = []
        for src in sources:
            target = set(_ngram_hashes(src.text, ngram))
            containment = len(sig & target) / len(sig)
            if containment >= tau:
                fn0 = src.functions[0] if src.functions else None
                findings.append(make_finding(
                    NAME, VERSION, signature, src,
                    fn0 or _Pseudo(src.basename), (fn0.start_line if fn0 else 1),
                    round(containment, 3),
                    message=f"snippet of signature {getattr(signature, 'id', '?')} present "
                            f"(containment {containment:.2f} >= tau {tau})",
                    details={"containment": round(containment, 3), "ngram": ngram, "tau": tau},
                ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="snippet-match", version="1.0.0"),
    extractor=SnippetMatchExtractor(), matcher=SnippetMatchMatcher(),
    status=Status.JOURNEY,
    note="sub-function snippet clone via token n-gram containment; off by default",
))
