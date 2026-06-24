"""Reusable building blocks for recipe authors.

Currently this exposes ``make_finding``, the shared helper that turns a matched
``(SourceFile, Function)`` into a :class:`~openreagent.recipes.Finding`. Recipes
are deterministic and hashable; nothing here imports an LLM client.
"""
from __future__ import annotations

from typing import Any

from openreagent.matching import tier_for
from openreagent.recipes import Finding
from openreagent.solidity import Function, SourceFile


def make_finding(
    recipe_name: str,
    recipe_version: str,
    signature,
    src: SourceFile,
    fn: Function,
    line: int,
    score: float,
    message: str,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        recipe=recipe_name,
        recipe_version=recipe_version,
        signature_id=getattr(signature, "id", "?"),
        file=src.path,
        function=fn.name,
        line=line,
        tier=tier_for(score) or "LOW",
        score=round(float(score), 3),
        message=message,
        details=details or {},
    )
