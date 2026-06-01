"""The extract path: an audit finding -> a signature record.

Extraction is kept separate from scanning. It runs offline and *may* use an LLM
(only to fill a value's slots from prose; flagged by the recipe's
``extractor.uses_llm``). The produced value is validated against the recipe's
shape before a record is assembled, and every extraction is recorded in the
signature's provenance.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from openreagent import loader
from openreagent.models import ExtractedBy, Provenance, RecipeRef, Signature
from openreagent.recipes import get_recipe
from openreagent.shapes import get_shape


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_finding(path_or_obj: str | Path | dict) -> dict[str, Any]:
    if isinstance(path_or_obj, dict):
        return path_or_obj
    return json.loads(Path(path_or_obj).read_text(encoding="utf-8"))


def extract_signature(
    finding: str | Path | dict,
    recipe_name: str,
    version: str | None = None,
    signature_id: str | None = None,
    reviewer: str | None = None,
    client: Any = None,
    timestamp: str | None = None,
) -> Signature:
    loader.load_builtins()
    recipe = get_recipe(recipe_name, version)
    if recipe is None:
        raise KeyError(f"recipe not registered: {recipe_name}@{version or 'latest'}")

    src = dict(load_finding(finding))
    if client is not None:
        src["_client"] = client

    value = recipe.extractor.extract(src)

    shape = get_shape(recipe.shape.name, recipe.shape.version)
    if shape is None:
        raise KeyError(f"shape not registered for recipe {recipe.name}")
    shape.validate(value)  # raises pydantic.ValidationError on nonconformance

    ts = timestamp or _now()
    prov = Provenance(
        source_kind=src.get("source_kind", "audit_report"),
        source_ref=src.get("source_ref", src.get("id", "unknown")),
        extracted_by=ExtractedBy(recipe=recipe.name, version=recipe.version, timestamp=ts),
        reviewer=reviewer or src.get("reviewer"),
    )
    sig_id = signature_id or src.get("id") or f"sig-{recipe.name}-{ts.replace(':', '').replace('-', '')}"
    return Signature(
        id=sig_id,
        recipe=RecipeRef(name=recipe.name, version=recipe.version),
        value=value,
        provenance=[prov],
    )


def write_signature(sig: Signature, out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sig.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p
