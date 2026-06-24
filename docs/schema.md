# The OpenReagent signature schema

A signature is a vulnerability specification. The schema has two layers, kept
separate on purpose:

- **A. the signature record** — one per signature, small and stable.
- **B. the registry** — shapes and recipes, defined once and shared.

A signature record names a recipe, carries a value, and lists where it came
from. Everything about *how* it is extracted and matched lives in the recipe
definition, not re-stated on every record.

> Scope note. A signature describes a vulnerability so a matcher can surface code
> consistent with it. It surfaces candidates; it does not model attacker intent
> or end-to-end exploitability.

This document is the authoritative schema. Where background notes elsewhere
disagree with it, this document wins.

---

## Part A. The signature record

```
Signature := {
  id          : string
  recipe      : RecipeRef          # { name, version } into the registry
  value       : Value              # conforms to the recipe's shape
  provenance  : Provenance[]       # one or more sources
}

RecipeRef  := { name: string, version: semver }

Provenance := {
  source_kind  : "audit_report" | "source_contract" | "bytecode" | ...
  source_ref   : string
  extracted_by : { recipe, version, timestamp }   # the recipe version used at this extraction
  reviewer     : string?
}
```

The record is four fields. `recipe` pins both the extraction and the matching
behavior (and their versions). `provenance` is a list because one signature can
be induced from several sources, each possibly under a different recipe version;
each element keeps its own `extracted_by` so a reviewer can audit each origin.

This layer is implemented by `openreagent.models.Signature` (a pydantic model).

---

## Part B. The registry

### B.1 Shapes

A value shape is a named, versioned declaration of a value's structure. It makes
a value inspectable without the record layer knowing its internals.

```
Shape := { name: string, version: semver, fields: FieldDecl }

# bytecode-hash/v1
fields := { digest: hex(32), normalization: string }

# ast-sketch/v1
fields := { ngram: int, minhash: uint64[K], basis: string }
```

Shapes are modelled as pydantic types and registered with
`openreagent.shapes.register_shape`. The conformance validator is
`openreagent.shapes.conforms(value, shape_name)`. A shape ships as a package (or
inside a recipe package); see [packages.md](packages.md).

### B.2 Recipes

A recipe bundles an extractor and a matcher over one shape. It is the unit a
contributor adds and ships as a package.

```
Recipe := {
  name      : string
  version   : semver
  shape     : ShapeRef                              # { name, version }
  extractor : { impl, version, uses_llm: bool, params? }   # source -> value
  matcher   : { impl, version, params? }                   # (value, code) -> matches
}
```

Two invariants, both enforced in code: **no LLM at matching time** (and, today,
**none at extraction either** — every recipe is deterministic and hashable); and
**matcher and extractor operate on the recipe's shape**.

### B.3 Each detector is its own recipe

Detectors do not share one matcher. Each detector has its own extraction method
and its own detection algorithm, so each is its own recipe over its shape. The
recipe identity *is* the detector, which is why a value carries no
detector-identity field, and why cross-project propagation is per-recipe.

Registry today (open, expected to grow). The `status` column is a **maturity
label only** — never a precision or CI figure:

```
recipe                  shape             extractor (impl)         matcher (impl)               status        what it surfaces
----------------------- ----------------- ------------------------ ---------------------------- ------------- -----------------------------
bytecode-hash           bytecode-hash/v1  normalize+keccak (no)    hash-equality                journey        exact / near-exact clones
ast-sketch              ast-sketch/v1     flatten+minhash (no)     minhash-sim { tau }          journey        lightly modified near-duplicates
```

> Both are cheap, deterministic clone recipes, off by default. Further hashable
> clone/signature recipes are planned (see [roadmap.md](roadmap.md)).

---

## Part C. Examples

### C.1 bytecode-hash record

```json
{
  "id": "sig-evm-7f3a",
  "recipe": { "name": "bytecode-hash", "version": "1.0.0" },
  "value": { "digest": "9af2c1d3...e04b",
             "normalization": "source-text:strip-comments,collapse-ws" },
  "provenance": [
    { "source_kind": "source_contract",
      "source_ref": "VulnerableVault.sol@0xabc...123",
      "extracted_by": { "recipe": "bytecode-hash", "version": "1.0.0",
                        "timestamp": "2026-06-01T09:12:00Z" } }
  ]
}
```

### C.2 ast-sketch record (two sources)

```json
{
  "id": "sig-sketch-amm",
  "recipe": { "name": "ast-sketch", "version": "1.0.0" },
  "value": { "ngram": 5, "minhash": [12, 7, 99, "…"], "basis": "ast" },
  "provenance": [
    { "source_kind": "source_contract", "source_ref": "PriceOracle.sol@0xabc...123",
      "extracted_by": { "recipe": "ast-sketch", "version": "1.0.0",
                        "timestamp": "2026-05-10T00:00:00Z" },
      "reviewer": "reviewer-id" },
    { "source_kind": "source_contract", "source_ref": "PriceOracleV2.sol@0xdef...456",
      "extracted_by": { "recipe": "ast-sketch", "version": "1.1.0",
                        "timestamp": "2026-05-18T00:00:00Z" } }
  ]
}
```

The value has no detector-identity field; the recipe `ast-sketch` is the
identity. The two provenance records show the same signature evidenced by two
findings under two recipe versions.

---

## Status

Draft v0. Versioning follows the schema, not the tool.
