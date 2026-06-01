"""Reusable building blocks for recipe authors.

Nothing here imports an LLM client at module load: the slot-fill extractor pulls
in ``openreagent.llm`` lazily, inside ``extract``, so importing a recipe (which
the scan path does) never imports an LLM client.
"""
from __future__ import annotations

from typing import Any

from openreagent.matching import tier_for
from openreagent.recipes import Extractor, Finding
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


class SlotFillExtractor(Extractor):
    """Audit finding -> ``slot-spec`` value.

    Offline by default: if the finding already carries structured ``slots``,
    they are used verbatim (no LLM, fully deterministic). Only when slots are
    absent and prose is supplied is an LLM consulted to fill them — and only
    then is ``openreagent.llm`` imported.
    """

    uses_llm = True
    slot_keys: tuple[str, ...] = ()

    def build_prompt(self, source: dict[str, Any]) -> str:
        prose = source.get("prose") or source.get("mechanism") or ""
        keys = ", ".join(self.slot_keys) if self.slot_keys else "operation, attribute, operator, site, intended_order, canonical_reference"
        return (
            f"You are filling a slot-spec value for the '{self.impl}' recipe.\n"
            f"Given the audit finding prose below, return a JSON object of the form\n"
            f'{{"slots": {{ ... }}, "freeform": null}} using only these slot keys: {keys}.\n'
            f"Use null for any slot you cannot fill confidently. Do not invent facts.\n\n"
            f"FINDING:\n{prose}\n"
        )

    def extract(self, source: dict[str, Any]) -> dict[str, Any]:
        if "slots" in source and source["slots"] is not None:
            return {"slots": source["slots"], "freeform": source.get("freeform")}
        # LLM path — imported lazily, only here.
        from openreagent.llm import LLMError, default_client

        client = source.get("_client") or default_client()
        if client is None:
            raise LLMError(
                "No slots supplied and no LLM client available. Provide 'slots' "
                "in the finding, set ANTHROPIC_API_KEY, or set OPENREAGENT_REPLAY_FILE."
            )
        key = f"{self.impl}::{source.get('id', source.get('source_ref', '?'))}"
        out = client.complete_json(self.build_prompt(source), key)
        slots = out.get("slots", out) if isinstance(out, dict) else {}
        freeform = out.get("freeform") if isinstance(out, dict) else None
        return {"slots": slots, "freeform": freeform}
