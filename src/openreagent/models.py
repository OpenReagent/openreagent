"""Part A — the signature record.

A signature record is four fields (see ``docs/schema.md`` Part A). It names a
recipe, carries a value that conforms to that recipe's shape, and lists where
it came from. Everything about *how* a signature is extracted and matched lives
in the recipe definition, not re-stated on every record.

The record layer deliberately does not know a value's internals: ``value`` is
an opaque mapping here. Shape conformance is checked by the registry
(``openreagent.shapes.conforms``) against the recipe's declared shape.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecipeRef(BaseModel):
    """A reference into the recipe registry. Pins both the extraction and the
    matching behavior, including their version."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = Field(description="semver, e.g. '1.0.0'")


class ExtractedBy(BaseModel):
    """The recipe version used at one extraction event."""

    model_config = ConfigDict(extra="forbid")

    recipe: str
    version: str
    timestamp: str = Field(description="ISO-8601 UTC, e.g. '2026-06-01T09:12:00Z'")


class Provenance(BaseModel):
    """One source from which a signature was induced.

    ``provenance`` is a list on the record because a single signature can be
    evidenced by several sources, each possibly extracted under a different
    recipe version; each element keeps its own ``extracted_by`` so a reviewer
    can audit each origin independently.
    """

    model_config = ConfigDict(extra="forbid")

    source_kind: str = Field(
        description="e.g. 'audit_report' | 'source_contract' | 'bytecode'"
    )
    source_ref: str
    extracted_by: ExtractedBy
    reviewer: str | None = None


class Signature(BaseModel):
    """A vulnerability specification: the stable, four-field record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    recipe: RecipeRef
    value: dict[str, Any] = Field(
        description="conforms to the recipe's shape; validated by the registry"
    )
    provenance: list[Provenance] = Field(min_length=1)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Signature":
        return cls.model_validate(d)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
