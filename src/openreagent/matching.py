"""Shared, deterministic helpers for recipe matchers.

These helpers carry no recipe-specific logic: they score a match into a tier and
expose the build artifacts (Bytecode/AST/ABI) a matcher may want. Every function
here is pure.
"""
from __future__ import annotations

THRESHOLD_LOW = 0.4
THRESHOLD_HIGH = 0.7


def tier_for(score: float, low: float = THRESHOLD_LOW, high: float = THRESHOLD_HIGH) -> str | None:
    """HIGH for score >= high, MEDIUM for [low, high), None below low."""
    if score < low:
        return None
    return "HIGH" if score >= high else "MEDIUM"


# ---------------------------------------------------------------------------
# Artifact access (the unified CodeView; falls back to "no artifacts" on a list)
# ---------------------------------------------------------------------------

def artifacts_for(sources, src) -> list:
    """Build artifacts for ``src`` when scanning a :class:`CodeView`, else ``[]``.

    Duck-typed so a matcher works whether it is handed a ``CodeView`` (artifacts
    available) or a plain ``list[SourceFile]`` (no build — lexical fallback).
    """
    fn = getattr(sources, "artifacts_for", None)
    return fn(src) if callable(fn) else []


def ast_for(sources, src):
    """The AST for ``src`` when available (built target), else ``None``."""
    fn = getattr(sources, "ast_for", None)
    return fn(src) if callable(fn) else None


def bytecode_for(sources, src) -> list[tuple[str, str]]:
    """List of ``(contract, creation_bytecode)`` for ``src``; empty without a build."""
    out: list[tuple[str, str]] = []
    for art in artifacts_for(sources, src):
        bc = getattr(art, "bytecode", "") or ""
        if bc:
            out.append((getattr(art, "contract", ""), bc))
    return out


def abi_for(sources, src) -> list:
    """Concatenated ABIs for ``src`` (across its contracts); empty without a build."""
    out: list = []
    for art in artifacts_for(sources, src):
        abi = getattr(art, "abi", None)
        if isinstance(abi, list):
            out.extend(abi)
    return out
