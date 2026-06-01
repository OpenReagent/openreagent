"""Part B.2 / B.3 — recipes, and the open recipe registry.

A *recipe* bundles an extractor and a matcher over one shape. It is the unit a
contributor adds (one package). Each detector is its own recipe over a shared
shape; the recipe identity *is* the detector, which is why a value carries no
detector-identity field.

Two invariants are enforced structurally:

  1. **No LLM at matching time.** ``Matcher.uses_llm`` is a hard ``False`` and
     the scan engine imports no LLM client (see ``openreagent.scan``).
     Extraction may use an LLM, offline, flagged by ``Extractor.uses_llm``.
  2. **Matcher and extractor operate on the recipe's shape.** Both read and
     produce values described by ``Recipe.shape``.
"""
from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from openreagent.shapes import ShapeRef


class Status(str, enum.Enum):
    """Maturity of a recipe. This is the *only* public status signal; it is a
    maturity label, never a precision or CI figure (see ``docs/evaluation.md``).

      - ``production``   reviewed in depth; on by default.
      - ``experimental`` implemented; off by default pending broader review.
      - ``journey``      kept as a cheap, deterministic option; off by default.
    """

    PRODUCTION = "production"
    EXPERIMENTAL = "experimental"
    JOURNEY = "journey"


class Finding(BaseModel):
    """One match emitted by a recipe's matcher."""

    model_config = ConfigDict(extra="forbid")

    recipe: str
    recipe_version: str
    signature_id: str
    file: str
    function: str
    line: int
    tier: str = Field(description="HIGH | MEDIUM | LOW")
    score: float
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Extractor:
    """Source -> value. May use an LLM, offline, on the extract path only.

    Subclasses implement ``extract``. The base records the static descriptor
    (impl name, version, ``uses_llm``) that the recipe self-describes with.
    """

    impl: str = ""
    version: str = "0.0.0"
    uses_llm: bool = False
    params: dict[str, Any] = {}

    def extract(self, source: dict[str, Any]) -> dict[str, Any]:
        """Turn a source description into a value conforming to the shape."""
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "impl": self.impl,
            "version": self.version,
            "uses_llm": bool(self.uses_llm),
            "params": dict(self.params),
        }


class Matcher:
    """(value, code) -> matches. Never uses an LLM (hard invariant).

    Subclasses implement ``match`` and must be a pure function of their inputs:
    no shared mutable state across recipes, no I/O beyond reading the supplied
    sources. This is what makes scan deterministic and recipe-isolated.
    """

    impl: str = ""
    version: str = "0.0.0"
    uses_llm: bool = False  # invariant — do not override to True
    params: dict[str, Any] = {}

    def match(self, value: dict[str, Any], sources: list, signature) -> list[Finding]:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "impl": self.impl,
            "version": self.version,
            "uses_llm": False,
            "params": dict(self.params),
        }


class Recipe:
    """A named, versioned bundle of one extractor and one matcher over a shape."""

    def __init__(
        self,
        name: str,
        version: str,
        shape: ShapeRef,
        extractor: Extractor,
        matcher: Matcher,
        status: Status = Status.EXPERIMENTAL,
        default_enabled: bool | None = None,
        note: str = "",
    ):
        if matcher.uses_llm:
            raise ValueError(
                f"recipe {name}: matcher.uses_llm must be False (no LLM at match time)"
            )
        self.name = name
        self.version = version
        self.shape = shape
        self.extractor = extractor
        self.matcher = matcher
        self.status = status
        # Default rule: production recipes are on by default; everything else
        # (experimental, journey) is off by default. Overridable per recipe.
        self.default_enabled = (
            default_enabled
            if default_enabled is not None
            else (status == Status.PRODUCTION)
        )
        self.note = note

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"

    def describe(self) -> dict[str, Any]:
        """Self-description used by ``openreagent recipes`` and the loadability
        guard. Carries no measurement numbers — maturity status only."""
        return {
            "name": self.name,
            "version": self.version,
            "shape": {"name": self.shape.name, "version": self.shape.version},
            "status": self.status.value,
            "default_enabled": self.default_enabled,
            "extractor": self.extractor.describe(),
            "matcher": self.matcher.describe(),
            "note": self.note,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Recipe {self.key} status={self.status.value}>"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_RECIPES: dict[str, Recipe] = {}


def register_recipe(recipe: Recipe) -> Recipe:
    """Register a recipe. Idempotent per ``name@version``."""
    _RECIPES[recipe.key] = recipe
    return recipe


def get_recipe(name: str, version: str | None = None) -> Recipe | None:
    if version is not None:
        return _RECIPES.get(f"{name}@{version}")
    candidates = [r for r in _RECIPES.values() if r.name == name]
    if not candidates:
        return None
    return max(candidates, key=lambda r: _semver_key(r.version))


def all_recipes() -> list[Recipe]:
    """Every registered recipe, in deterministic (name, version) order."""
    return [_RECIPES[k] for k in sorted(_RECIPES)]


def clear_recipes() -> None:
    """Test helper: drop every registered recipe."""
    _RECIPES.clear()


def _semver_key(version: str) -> tuple:
    parts = []
    for p in version.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(-1)
    return tuple(parts)
