# Recipes

OpenReagent's recipes are **deterministic and hashable**: a signature reduces to a
stored value (a hash, a MinHash signature, …) and matching is a pure function of
`(value, code)` with **no LLM and no ML** anywhere — not even at extraction. The
only status reported is **maturity** — `production`, `experimental`, or `journey`.
No precision, recall, or CI figures appear here or anywhere in this repository
(see [evaluation.md](evaluation.md)).

Default enablement follows status: production recipes are on by default;
experimental and journey recipes are off by default and enabled with
`--enable <name>` (or `--enable '*'`). Each recipe ships as a package; see
[packages.md](packages.md).

| recipe | version | shape | status | default | what it surfaces |
|--------|---------|-------|--------|---------|------------------|
| `bytecode-hash` | 1.0.0 | `bytecode-hash/v1` | journey | off | an exact / near-exact normalized clone (bytecode or source-text) |
| `bytecode-sketch` | 1.0.0 | `bytecode-sketch/v1` | journey | off | a bytecode near-duplicate (opcode n-gram MinHash) |
| `ast-sketch` | 1.0.0 | `ast-sketch/v1` | journey | off | a lightly modified near-duplicate (AST or token MinHash) |
| `function-skeleton` | 1.0.0 | `function-skeleton/v1` | journey | off | a function-level abstracted clone (renamed copies match) |
| `snippet-match` | 1.0.0 | `snippet-match/v1` | journey | off | a sub-function snippet present (token n-gram containment) |

No recipe uses an LLM — extraction and matching are both deterministic and hashable.

## Notes on the journey recipes

All recipes are cheap, deterministic clone detectors, complementary across
granularity (contract / function / snippet) and view (source / bytecode):

- **`bytecode-hash`** — exact clone. Matches a **source-text** normalization with
  no compiler (lexical fallback) **and** a compiled-**bytecode** digest (creation
  bytecode) when built. The signature's `normalization` records which.
- **`bytecode-sketch`** — bytecode near-duplicate. MinHash over PUSH-masked,
  metadata-stripped **opcode** n-grams (disassembled with `pyevmasm`, the
  `bytecode` extra); Jaccard estimated from signatures. Needs a build to supply
  bytecode, else contributes nothing.
- **`ast-sketch`** — source near-duplicate. Shingles a real **AST** (node-type
  sequence) when available, else the lexical **token** stream; the `basis`
  (`ast` | `lexical-tokens`) records which (only same-basis signatures compare).
- **`function-skeleton`** — function-level clone. Hashes a function's
  identifier-abstracted token skeleton, so renamed copies (Type-2) match;
  catches a vulnerable function pasted into a larger contract. Lexical, so it
  works on partial source.
- **`snippet-match`** — sub-function snippet clone. Token n-gram **containment**
  of a known-vulnerable snippet; catches a few vulnerable lines pasted anywhere.
  Lexical, works on partial / non-compiling source.

The source recipes use the lexical *Code* view (and `ast-sketch` the real AST
when a build is available); the bytecode recipes use compiled artifacts from the
**unified scan input** (see [frameworks.md](frameworks.md)) and fall back to no
output when a target was not built.

## Planned

Out of scope for now but on the [roadmap](roadmap.md): **patch-aware** signatures
(store a vulnerable *and* a patched fingerprint, flag only "matches vulnerable AND
not patched"), and PoC-trace behavioral signatures (v0.3).

## Maturity, in words

- **production** — reviewed in depth; on by default. (None ship yet.)
- **experimental** — implemented and tested, but pending broader review; off by
  default.
- **journey** — retained as a cheap deterministic option; off by default.
