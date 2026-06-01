"""Part B.1 — shapes, and the conformance validator.

A *shape* is a named, versioned declaration of a value's structure. It makes a
value inspectable without the record layer knowing its internals. Shapes are
modelled as pydantic types: the field declaration in ``docs/schema.md`` Part
B.1 maps directly onto a pydantic ``BaseModel``.

The registry is open. A shape module registers exactly one ``Shape`` per
``name@version`` by calling ``register_shape``.
"""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel, ConfigDict, ValidationError


class ShapeRef(BaseModel):
    """A reference into the shape registry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str


class Shape:
    """A named, versioned value structure backed by a pydantic model.

    ``model`` is the pydantic ``BaseModel`` subclass that declares the fields.
    ``validate`` returns the parsed model on success and raises
    ``pydantic.ValidationError`` on failure; ``conforms`` is the boolean form.
    """

    def __init__(self, name: str, version: str, model: Type[BaseModel]):
        if not name:
            raise ValueError("Shape.name must be set")
        if not version:
            raise ValueError("Shape.version must be set")
        self.name = name
        self.version = version
        self.model = model

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"

    def validate(self, value: dict[str, Any]) -> BaseModel:
        return self.model.model_validate(value)

    def conforms(self, value: dict[str, Any]) -> bool:
        try:
            self.validate(value)
            return True
        except ValidationError:
            return False

    def fields(self) -> dict[str, Any]:
        """A JSON Schema view of the shape's fields (for ``self-describe``)."""
        return self.model.model_json_schema()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Shape {self.key}>"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_SHAPES: dict[str, Shape] = {}


def register_shape(shape: Shape) -> Shape:
    """Register a shape. Idempotent per ``name@version``: re-registering the
    same key replaces the previous instance (tests rely on this)."""
    _SHAPES[shape.key] = shape
    return shape


def get_shape(name: str, version: str | None = None) -> Shape | None:
    """Look up a shape. With ``version`` omitted, return the highest-version
    registration for ``name`` (semver-naive: lexicographic on dotted ints)."""
    if version is not None:
        return _SHAPES.get(f"{name}@{version}")
    candidates = [s for s in _SHAPES.values() if s.name == name]
    if not candidates:
        return None
    return max(candidates, key=lambda s: _semver_key(s.version))


def all_shapes() -> list[Shape]:
    return [_SHAPES[k] for k in sorted(_SHAPES)]


def clear_shapes() -> None:
    """Test helper: drop every registered shape."""
    _SHAPES.clear()


def _semver_key(version: str) -> tuple:
    parts = []
    for p in version.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(-1)
    return tuple(parts)


# ---------------------------------------------------------------------------
# Conformance entry point
# ---------------------------------------------------------------------------

def conforms(value: dict[str, Any], shape_name: str, shape_version: str | None = None) -> bool:
    """Return True iff ``value`` conforms to the named shape. Returns False if
    the shape is not registered."""
    shape = get_shape(shape_name, shape_version)
    if shape is None:
        return False
    return shape.conforms(value)


def validate_value(value: dict[str, Any], shape_name: str, shape_version: str | None = None) -> BaseModel:
    """Validate and return the parsed value, raising on a missing shape or a
    conformance failure."""
    shape = get_shape(shape_name, shape_version)
    if shape is None:
        raise KeyError(f"shape not registered: {shape_name}@{shape_version}")
    return shape.validate(value)
