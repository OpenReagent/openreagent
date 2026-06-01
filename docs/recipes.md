# Recipes

One row per registered recipe. The only status reported is **maturity** —
`production`, `experimental`, or `journey`. No precision, recall, or CI figures
appear here or anywhere else in this repository (see
[evaluation.md](evaluation.md)).

Default enablement follows status: production recipes are on by default;
experimental and journey recipes are off by default and enabled with
`--enable <name>` (or `--enable '*'`). Each recipe ships as a package; see
[packages.md](packages.md).

| recipe | version | shape | status | default | extractor uses LLM | what it surfaces |
|--------|---------|-------|--------|---------|--------------------|------------------|
| `internal-absence` | 1.0.0 | `slot-spec/v1` | production | on | yes | a required element absent at a named site |
| `canonical-divergence` | 1.0.0 | `slot-spec/v1` | production | on | yes | an implementation diverging from a canonical reference |
| `operand-mismatch` | 1.0.0 | `slot-spec/v1` | experimental | off | yes | an operation reading the wrong operand attribute |
| `operator-direction` | 1.0.0 | `slot-spec/v1` | experimental | off | yes | a comparison operator pointing the wrong way |
| `unbound-caller-value` | 1.0.0 | `slot-spec/v1` | experimental | off | yes | a caller-supplied value used without a binding check |
| `ordering-violation` | 1.0.0 | `slot-spec/v1` | experimental | off | yes | two operations occurring in the wrong order |
| `aggregated-state` | 1.0.0 | `slot-spec/v1` | experimental | off | yes | aggregate state inconsistent with keyed state |
| `generic-slot` | 1.0.0 | `slot-spec/v1` | experimental | off | yes | an expressible but unclassified candidate (fallback) |
| `bytecode-hash` | 1.0.0 | `bytecode-hash/v1` | journey | off | no | an exact / near-exact normalized clone |
| `ast-sketch` | 1.0.0 | `ast-sketch/v1` | journey | off | no | a lightly modified near-duplicate |

## Notes on the journey recipes

`bytecode-hash` and `ast-sketch` are kept as cheap, deterministic recipes rather
than as a taxonomy. `bytecode-hash` was effective on exact and near-exact clones
and `ast-sketch` on lightly modified ones; neither generalized to harder cases.

The built-in `bytecode-hash` matcher compares a **source-text** normalization
(`strip comments, collapse whitespace`), which needs no compiler. A digest taken
over compiled **bytecode** can be produced on the extract side with the
`bytecode` extra, but matching a bytecode digest against source requires a
compiler and is out of scope for the built-in matcher.

## Maturity, in words

- **production** — reviewed in depth; on by default. Currently `internal-absence`
  and `canonical-divergence`.
- **experimental** — implemented and tested, but pending broader review; off by
  default.
- **journey** — retained as a cheap deterministic option; off by default.
