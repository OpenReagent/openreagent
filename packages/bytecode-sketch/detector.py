"""Package: bytecode-sketch/1.0.0  (self-contained shape + recipe)

Bytecode near-duplicate detector. It disassembles a contract's compiled bytecode
to an opcode stream — after stripping the Solidity metadata trailer and masking
PUSH immediates — shingles opcode n-grams, and stores a MinHash signature. Two
contracts' Jaccard similarity is estimated from the signatures alone, so it
catches forks and near-copies that exact `bytecode-hash` misses. (He et al. found
clones propagate vulnerabilities across the EVM ecosystem at this granularity.)

Deterministic and hashable (no LLM). Disassembly uses **pyevmasm** (the
``bytecode`` extra); without it, or without a build to supply bytecode, the recipe
contributes nothing (graceful). Journey recipe (off by default).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from openreagent._hashing import jaccard, minhash, shingle
from openreagent.matching import bytecode_for
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import make_finding
from openreagent.shapes import Shape, ShapeRef, register_shape

NAME, VERSION = "bytecode-sketch", "1.0.0"
DEFAULT_NGRAM = 4
DEFAULT_NUM_PERM = 64
_U64 = (1 << 64) - 1


# ---- shape: bytecode-sketch/v1 ----

class BytecodeSketchV1(BaseModel):
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
            if not (0 <= x <= _U64):
                raise ValueError("minhash entries must be uint64")
        return v


register_shape(Shape(name="bytecode-sketch", version="1.0.0", model=BytecodeSketchV1))


def _opcode_minhash(code_hex: str, ngram: int, num_perm: int) -> list[int]:
    """MinHash over PUSH-masked opcode n-grams of (metadata-stripped) bytecode."""
    from openreagent.evm import from_hex, opcodes, strip_metadata  # lazy: bytecode extra

    ops = opcodes(strip_metadata(from_hex(code_hex)))
    return minhash(shingle(ops, ngram), num_perm=num_perm)


class _Pseudo:
    def __init__(self, name: str):
        self.name = name
        self.start_line = 1


# ---- recipe ----

class BytecodeSketchExtractor(Extractor):
    impl = "opcode-ngram+minhash"
    version = "1.0.0"
    params = {"ngram": DEFAULT_NGRAM, "num_perm": DEFAULT_NUM_PERM}

    def extract(self, source: dict) -> dict:
        bc = source.get("bytecode")
        if not bc:
            raise ValueError("bytecode-sketch extract needs 'bytecode' (hex)")
        ngram = int(source.get("ngram", DEFAULT_NGRAM))
        num_perm = int(source.get("num_perm", DEFAULT_NUM_PERM))
        return {"ngram": ngram, "minhash": _opcode_minhash(str(bc), ngram, num_perm)}


class BytecodeSketchMatcher(Matcher):
    impl = "minhash-sim"
    version = "1.0.0"
    params = {"tau": 0.7}

    def match(self, value, sources, signature):
        sig_mh = value.get("minhash", [])
        if not sig_mh:
            return []
        ngram = int(value.get("ngram", DEFAULT_NGRAM))
        num_perm = len(sig_mh)
        tau = float(self.params.get("tau", 0.7))
        findings = []
        try:
            for src in sources:
                for contract, bc in bytecode_for(sources, src):
                    sim = jaccard(sig_mh, _opcode_minhash(bc, ngram, num_perm))
                    if sim >= tau:
                        fn0 = src.functions[0] if src.functions else None
                        findings.append(make_finding(
                            NAME, VERSION, signature, src,
                            fn0 or _Pseudo(contract or src.basename),
                            (fn0.start_line if fn0 else 1), round(sim, 3),
                            message=f"near-duplicate bytecode of signature "
                                    f"{getattr(signature, 'id', '?')} (contract {contract}, "
                                    f"similarity {sim:.2f} >= tau {tau})",
                            details={"similarity": round(sim, 3), "ngram": ngram,
                                     "tau": tau, "contract": contract},
                        ))
        except ImportError:
            return []  # pyevmasm (bytecode extra) not installed — degrade gracefully
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="bytecode-sketch", version="1.0.0"),
    extractor=BytecodeSketchExtractor(), matcher=BytecodeSketchMatcher(),
    status=Status.JOURNEY,
    note="bytecode near-duplicate via opcode-ngram MinHash; off by default",
))
