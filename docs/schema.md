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
fields := { ngram: int, minhash: uint64[K] }

# slot-spec/v1     (no detector-identity field — the recipe is the identity)
fields := { slots: { operation?, attribute?, operator?, site?,
                     intended_order?, canonical_reference?, ... },
            freeform: string? }
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

Two invariants, both enforced in code: **no LLM at matching time** (extraction
may use one, offline, flagged by `extractor.uses_llm`); and **matcher and
extractor operate on the recipe's shape**.

### B.3 Each detector is its own recipe

Detectors do not share one matcher. Each detector has its own extraction method
and its own detection algorithm, so each is its own recipe over a shared shape.
The recipe identity *is* the detector, which is why a value carries no
detector-identity field, and why cross-project propagation is per-recipe. The
slot-based detectors share the `slot-spec` shape; a finding that is expressible
but fits no specific detector uses the `generic-slot` recipe.

Registry today (open, expected to grow). The `status` column is a **maturity
label only** — never a precision or CI figure:

```
recipe                  shape             extractor (impl)         matcher (impl)               status        what it surfaces
----------------------- ----------------- ------------------------ ---------------------------- ------------- -----------------------------
internal-absence        slot-spec/v1      slot-fill (llm)          absence-detector             production     a required element absent at a site
canonical-divergence    slot-spec/v1      slot-fill (llm)          canonical-ref-detector       production     divergence from a canonical reference
operand-mismatch        slot-spec/v1      slot-fill (llm)          operand-detector             experimental   wrong operand attribute
operator-direction      slot-spec/v1      slot-fill (llm)          operator-detector            experimental   comparison points the wrong way
unbound-caller-value    slot-spec/v1      slot-fill (llm)          binding-detector             experimental   caller value used without a bound
ordering-violation      slot-spec/v1      slot-fill (llm)          ordering-detector            experimental   two operations in the wrong order
aggregated-state        slot-spec/v1      slot-fill (llm)          aggregate-detector           experimental   aggregate vs keyed state mismatch
generic-slot            slot-spec/v1      slot-fill (llm)          generic-slot-matcher         experimental   expressible, unclassified fallback
bytecode-hash           bytecode-hash/v1  normalize+keccak (no)    hash-equality                journey        exact / near-exact clones
ast-sketch              ast-sketch/v1     flatten+minhash (no)     minhash-sim { tau }          journey        lightly modified near-duplicates
```

> Journey note, not part of the fixed schema. `bytecode-hash` was effective on
> exact and near-exact clones, `ast-sketch` on lightly modified ones. They stay
> as cheap deterministic recipes, off by default — not as a taxonomy.

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

### C.2 canonical-divergence record (two sources)

```json
{
  "id": "sig-amm-spot",
  "recipe": { "name": "canonical-divergence", "version": "1.0.0" },
  "value": {
    "slots": {
      "operation": "amm_spot_price_read",
      "site": { "function": "getPrice", "file": "PriceOracle.sol" },
      "canonical_reference": "uniswap_v2/twap"
    },
    "freeform": null
  },
  "provenance": [
    { "source_kind": "audit_report", "source_ref": "<contest>-H-05",
      "extracted_by": { "recipe": "canonical-divergence", "version": "1.0.0",
                        "timestamp": "2026-05-10T00:00:00Z" },
      "reviewer": "reviewer-id" },
    { "source_kind": "audit_report", "source_ref": "<contest>-H-13",
      "extracted_by": { "recipe": "canonical-divergence", "version": "1.1.0",
                        "timestamp": "2026-05-18T00:00:00Z" } }
  ]
}
```

The value has no detector-identity field; the recipe `canonical-divergence` is
the identity. The two provenance records show the same signature evidenced by two
findings under two recipe versions.

---

## Status

Draft v0. Versioning follows the schema, not the tool.
