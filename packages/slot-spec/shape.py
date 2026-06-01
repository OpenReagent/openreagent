"""Shape: slot-spec/v1.

The shared value shape for slot-based detectors and the unclassified
``generic-slot`` fallback. The value carries no detector-identity field — the
recipe is the identity. See docs/schema.md Part B.1.

The known slot keys are all optional; additional keys are permitted (the
``...`` in the schema), so a recipe can carry slots beyond the common set.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from openreagent.shapes import Shape, register_shape


class Slots(BaseModel):
    model_config = ConfigDict(extra="allow")

    operation: Optional[Any] = None
    attribute: Optional[Any] = None
    operator: Optional[Any] = None
    site: Optional[Any] = None
    intended_order: Optional[Any] = None
    canonical_reference: Optional[Any] = None


class SlotSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: Slots
    freeform: Optional[str] = None


register_shape(Shape(name="slot-spec", version="1.0.0", model=SlotSpecV1))
