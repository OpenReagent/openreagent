"""Shared, deterministic helpers for recipe matchers.

These helpers carry no recipe-specific logic. They turn a ``slot-spec`` value's
``site`` slot into candidate-function targeting, score a match into a tier, and
do glob-aware name matching. Every function here is pure.
"""
from __future__ import annotations

import fnmatch

from openreagent.solidity import Function, SourceFile

THRESHOLD_LOW = 0.4
THRESHOLD_HIGH = 0.7


def tier_for(score: float, low: float = THRESHOLD_LOW, high: float = THRESHOLD_HIGH) -> str | None:
    """HIGH for score >= high, MEDIUM for [low, high), None below low."""
    if score < low:
        return None
    return "HIGH" if score >= high else "MEDIUM"


def name_match(actual: str, pattern: str) -> bool:
    if not actual or not pattern:
        return False
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatchcase(actual, pattern)
    return actual == pattern


def site_targets(site_value) -> tuple[list[str], list[str]]:
    """Pull (function_patterns, file_basenames) out of a ``site`` slot.

    Accepts a structured dict (``{function|functions, file|files}``) or a bare
    string. A bare string contributes nothing to targeting (it is treated as
    prose) and the matcher falls back to scanning all functions.
    """
    funcs: list[str] = []
    files: list[str] = []
    if isinstance(site_value, dict):
        for key in ("function", "functions"):
            v = site_value.get(key)
            if isinstance(v, str) and v.strip():
                funcs.append(v.strip())
            elif isinstance(v, list):
                funcs.extend(s.strip() for s in v if isinstance(s, str) and s.strip())
        for key in ("file", "files"):
            v = site_value.get(key)
            if isinstance(v, str) and v.strip():
                files.append(_basename(v.strip()))
            elif isinstance(v, list):
                files.extend(_basename(s.strip()) for s in v if isinstance(s, str) and s.strip())
    # De-dup, preserve order.
    return list(dict.fromkeys(funcs)), list(dict.fromkeys(files))


def _basename(p: str) -> str:
    return p.replace("\\", "/").split("/")[-1]


def function_in_scope(src: SourceFile, fn: Function,
                      func_patterns: list[str], file_basenames: list[str]) -> bool:
    """True if ``fn`` is in the targeted scope.

    - If file basenames are given, the file must match.
    - If function patterns are given, the name must match.
    - If neither is given, every function is in scope (the matcher then relies
      on its own slot-token evidence to decide).
    """
    if file_basenames and src.basename not in file_basenames:
        return False
    if func_patterns and not any(name_match(fn.name, p) for p in func_patterns):
        return False
    return True


def slot(value: dict, name: str):
    """Read ``value['slots'][name]`` defensively (returns None if absent)."""
    slots = value.get("slots") if isinstance(value, dict) else None
    if isinstance(slots, dict):
        return slots.get(name)
    return None


def marker_present(fn: Function, markers: list[str]) -> bool:
    """True if any marker is present in ``fn`` — either as an identifier/call
    token (case-insensitive) or as a substring of the (lowercased) body text.
    Substring matching lets markers like ``address(0)`` or ``balances[`` work."""
    if not markers:
        return False
    idents = {t.lower() for t in (fn.identifiers() | fn.call_targets())}
    body = fn.body_text.lower()
    for m in markers:
        ml = m.strip().lower()
        if not ml:
            continue
        if ml in idents or ml in body:
            return True
    return False


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


def as_token_list(v) -> list[str]:
    """Coerce a slot value into a list of lowercase tokens for marker matching."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip().lower()] if v.strip() else []
    if isinstance(v, list):
        out: list[str] = []
        for item in v:
            out.extend(as_token_list(item))
        return out
    if isinstance(v, dict):
        out = []
        for key in ("value", "kind", "name", "tokens", "markers"):
            if key in v:
                out.extend(as_token_list(v[key]))
        return out
    return [str(v).strip().lower()]
