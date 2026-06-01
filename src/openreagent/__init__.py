"""OpenReagent — a recipe-based framework for specifying and matching
recurring smart-contract vulnerabilities.

The public surface is small on purpose. A *signature* is a vulnerability
specification (see ``models``). It names a *recipe* from the open registry;
the recipe pins both how a signature is extracted from a source and how it is
matched against code. *Shapes* declare the structure of a signature's value.

Two layers, kept separate:

  - the **record** (``openreagent.models.Signature``): small, stable.
  - the **registry** (``openreagent.shapes`` and ``openreagent.recipes``):
    shapes and recipes, defined once and shared.

See ``docs/schema.md`` for the authoritative schema and ``docs/architecture.md``
for how the pieces fit together.
"""
from __future__ import annotations

__version__ = "0.1.0"

from openreagent.models import (
    ExtractedBy,
    Provenance,
    RecipeRef,
    Signature,
)
from openreagent.shapes import Shape, ShapeRef, conforms, get_shape, register_shape
from openreagent.recipes import (
    Extractor,
    Finding,
    Matcher,
    Recipe,
    Status,
    get_recipe,
    register_recipe,
)

__all__ = [
    "__version__",
    "Signature",
    "RecipeRef",
    "Provenance",
    "ExtractedBy",
    "Shape",
    "ShapeRef",
    "register_shape",
    "get_shape",
    "conforms",
    "Recipe",
    "Extractor",
    "Matcher",
    "Finding",
    "Status",
    "register_recipe",
    "get_recipe",
]
