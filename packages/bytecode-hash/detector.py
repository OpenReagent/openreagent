"""Package: bytecode-hash/1.0.0  (self-contained shape + recipe)

A cheap, deterministic clone detector. Registers its own shape
(``bytecode-hash/v1``) and recipe in one entry module, so the package has no
external shape dependency.

The value is a keccak-256 digest over a normalized form of a contract. It was
effective on exact and near-exact clones; it is a journey recipe (off by
default), not a taxonomy. Default normalization is source-text based
("strip comments, collapse whitespace"), which needs no compiler.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from openreagent._hashing import keccak256
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import make_finding
from openreagent.shapes import Shape, ShapeRef, register_shape
from openreagent.solidity import _mask

NAME = "bytecode-hash"
VERSION = "1.0.0"
SOURCE_NORM = "source-text:strip-comments,collapse-ws"
BYTECODE_NORM = "bytecode:strip-metadata,mask-push-args"
_HEX32 = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


# ---- shape: bytecode-hash/v1 ----

class BytecodeHashV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: str
    normalization: str

    @field_validator("digest")
    @classmethod
    def _hex32(cls, v: str) -> str:
        if not _HEX32.match(v):
            raise ValueError("digest must be 32 bytes as 64 hex chars (optional 0x prefix)")
        return v.lower()

    @field_validator("normalization")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("normalization must be a non-empty descriptor")
        return v


register_shape(Shape(name="bytecode-hash", version="1.0.0", model=BytecodeHashV1))


# ---- normalization helpers ----

def _normalize_source(text: str) -> str:
    return " ".join(_mask(text).split())


def _normalize_bytecode(hexstr: str) -> str:
    h = hexstr[2:] if hexstr.startswith("0x") else hexstr
    h = h.lower()
    if len(h) > 4:
        meta_len = int(h[-4:], 16) if all(c in "0123456789abcdef" for c in h[-4:]) else 0
        if 0 < meta_len * 2 < len(h):
            h = h[: -(meta_len * 2 + 4)]
    return h


# ---- recipe ----

class BytecodeHashExtractor(Extractor):
    impl = "normalize+keccak"
    version = "1.0.0"
    uses_llm = False

    def extract(self, source: dict) -> dict:
        if source.get("bytecode"):
            norm = _normalize_bytecode(str(source["bytecode"]))
            return {"digest": keccak256(bytes.fromhex(norm)), "normalization": BYTECODE_NORM}
        text = source.get("source")
        if text is None and source.get("source_path"):
            from pathlib import Path

            text = Path(source["source_path"]).read_text(encoding="utf-8", errors="replace")
        if text is None:
            raise ValueError("bytecode-hash extract needs 'bytecode', 'source', or 'source_path'")
        normalized = _normalize_source(text)
        return {"digest": keccak256(normalized.encode("utf-8")), "normalization": SOURCE_NORM}


class _Pseudo:
    def __init__(self, name: str):
        self.name = name
        self.start_line = 1


class BytecodeHashMatcher(Matcher):
    impl = "hash-equality"
    version = "1.0.0"
    uses_llm = False

    def match(self, value, sources, signature):
        digest = value.get("digest", "").lower().removeprefix("0x")
        norm = value.get("normalization", "")
        if not norm.startswith("source-text"):
            return []  # bytecode digests need a compiler; not handled here
        findings = []
        for src in sources:
            d = keccak256(_normalize_source(src.text).encode("utf-8"))
            if d == digest:
                fn0 = src.functions[0] if src.functions else None
                findings.append(make_finding(
                    NAME, VERSION, signature, src,
                    fn0 or _Pseudo(src.basename), (fn0.start_line if fn0 else 1), 1.0,
                    message=f"exact normalized-source clone of signature {getattr(signature, 'id', '?')}",
                    details={"digest": digest, "normalization": norm},
                ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="bytecode-hash", version="1.0.0"),
    extractor=BytecodeHashExtractor(), matcher=BytecodeHashMatcher(),
    status=Status.JOURNEY,
    note="exact / near-exact clones; cheap deterministic, off by default",
))
