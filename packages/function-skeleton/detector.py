"""Package: function-skeleton/1.0.0  (self-contained shape + recipe)

Function-level clone detector. It abstracts a function's identifiers (so renamed
copies still match — Type-1/2), hashes the normalized token *skeleton*, and
matches by exact equality. This catches a known-vulnerable function copied — and
possibly renamed — into another, larger contract, which the file/contract-level
recipes miss.

Deterministic and hashable (no LLM, no ML). It works on the lexical Code view, so
it also applies to partial / non-compiling source (e.g. an audit snippet). A
journey recipe (off by default).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from openreagent._hashing import keccak256
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import make_finding
from openreagent.shapes import Shape, ShapeRef, register_shape
from openreagent.solidity import _KEYWORDS, code_tokens, iter_functions, parse_source

NAME, VERSION = "function-skeleton", "1.0.0"
_HEX64 = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


# ---- shape: function-skeleton/v1 ----

class FunctionSkeletonV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length: int
    digest: str

    @field_validator("length")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("length must be >= 1")
        return v

    @field_validator("digest")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not _HEX64.match(v):
            raise ValueError("digest must be a keccak-256 hex (64 chars, optional 0x)")
        return v.lower().removeprefix("0x")


register_shape(Shape(name="function-skeleton", version="1.0.0", model=FunctionSkeletonV1))


# ---- skeleton ----

def _is_ident(tok: str) -> bool:
    return bool(tok) and (tok[0].isalpha() or tok[0] in "_$")


def _skeleton(text: str) -> tuple[int, str]:
    """(token count, keccak of the identifier-abstracted token stream)."""
    toks = code_tokens(text)
    abstracted = ["ID" if (_is_ident(t) and t not in _KEYWORDS) else t for t in toks]
    return len(toks), keccak256(" ".join(abstracted).encode("utf-8"))


def _function_body(text: str) -> str:
    """If ``text`` is a single function, return its body; else return ``text``."""
    fns = parse_source("<extract>", text).functions
    return fns[0].body_text if len(fns) == 1 else text


# ---- recipe ----

class FunctionSkeletonExtractor(Extractor):
    impl = "abstract+keccak"
    version = "1.0.0"

    def extract(self, source: dict) -> dict:
        text = source.get("source")
        if text is None and source.get("source_path"):
            from pathlib import Path

            text = Path(source["source_path"]).read_text(encoding="utf-8", errors="replace")
        if text is None:
            raise ValueError("function-skeleton extract needs 'source' or 'source_path'")
        length, digest = _skeleton(_function_body(text))
        return {"length": length, "digest": digest}


class FunctionSkeletonMatcher(Matcher):
    impl = "skeleton-equality"
    version = "1.0.0"

    def match(self, value, sources, signature):
        digest = value.get("digest", "").lower().removeprefix("0x")
        findings = []
        for src, fn in iter_functions(sources):
            ln, dg = _skeleton(fn.body_text)
            if dg == digest:
                findings.append(make_finding(
                    NAME, VERSION, signature, src, fn, fn.start_line, 1.0,
                    message=f"abstracted-function clone of signature "
                            f"{getattr(signature, 'id', '?')} ({fn.name})",
                    details={"digest": digest, "length": ln},
                ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="function-skeleton", version="1.0.0"),
    extractor=FunctionSkeletonExtractor(), matcher=FunctionSkeletonMatcher(),
    status=Status.JOURNEY,
    note="function-level abstracted clone; deterministic, off by default",
))
