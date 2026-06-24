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
| `bytecode-hash` | 1.0.0 | `bytecode-hash/v1` | journey | off | an exact / near-exact normalized clone |
| `ast-sketch` | 1.0.0 | `ast-sketch/v1` | journey | off | a lightly modified near-duplicate |

No recipe uses an LLM — extraction and matching are both deterministic.

## Notes on the journey recipes

`bytecode-hash` and `ast-sketch` are cheap, deterministic clone recipes.
`bytecode-hash` is effective on exact and near-exact clones; `ast-sketch` on
lightly modified ones.

Both consume the **unified scan input** (`Code` + `Bytecode` + `AST` + `ABI`; see
[frameworks.md](frameworks.md)). They prefer real build artifacts and fall back to
the lexical *Code* view when a target was not built:

- `bytecode-hash` matches a **source-text** normalization with no compiler
  (lexical fallback), **and** a compiled-**bytecode** digest (creation bytecode)
  when the target was built. The signature's `normalization` records which.
- `ast-sketch` shingles a real **AST** (node-type sequence) when one is available
  and falls back to the lexical **token** stream otherwise. The signature's
  `basis` (`ast` | `lexical-tokens`) records which; only same-basis signatures
  compare.

## Planned

Additional hashable clone/signature recipes are on the [roadmap](roadmap.md):
`function-skeleton` (abstracted function-level clone), `bytecode-sketch`
(basic-block opcode near-duplicate), and `snippet-match` (sub-function token
snippet clone).

## Maturity, in words

- **production** — reviewed in depth; on by default. (None ship yet.)
- **experimental** — implemented and tested, but pending broader review; off by
  default.
- **journey** — retained as a cheap deterministic option; off by default.
