# Conventions

Guidance for authoring **deterministic, hashable** signature recipes: how a
signature reduces to a stored value, how to keep it reproducible, and how to name
things.

## A recipe's signature must be hashable and deterministic

A recipe turns code into a fixed **value** (a hash, a MinHash signature, a
fingerprint set, …) that is stored in a signature record and compared with no LLM
and no ML. Two rules make this work:

- **The matcher is a pure function of `(value, code)`** — no shared mutable
  state, no I/O beyond the supplied sources. This is what makes a scan
  deterministic and recipe-isolated.
- **The extractor is deterministic too.** OpenReagent ships no LLM on either
  path. If a value derives from randomness (MinHash permutations, SimHash
  hyperplanes), the seed and hash family are **constants** and part of the
  signature's schema — pin them and never compare across schemas. Reuse the
  shared primitives in `openreagent._hashing` (seeded MinHash, pure-Python
  keccak), which are already fixed for reproducibility.

Watch the usual determinism traps: never use Python's salted `hash()` (use the
hashing helpers); don't depend on `set`/`dict` iteration order; avoid
floating-point in the signature path where an integer hash will do.

## Normalization is the lever

Most of a clone recipe's behavior is in its **normalization** — what it strips
before hashing. Record the normalization in the value (as `bytecode-hash` does
with its `normalization` string, and `ast-sketch` with its `basis`), and only
compare signatures produced under the **same** normalization. Examples:

- Bytecode: strip the CBOR metadata trailer (last two bytes are its length) and
  mask `PUSH` immediates before hashing.
- Source/AST: abstract identifiers, literals, and types so renamed clones match.

## Granularity

State the unit a signature names — contract, function, or sub-function snippet —
because it determines what a match means. A function-level signature catches a
vulnerable function copied into a larger contract; a snippet-level one catches a
few vulnerable lines pasted anywhere.

## A signature surfaces a candidate, not an exploit

A clone/signature match shows that code *consistent with* a known pattern is
present. It does **not** establish exploitability — empirically, only a small
fraction of code flagged "vulnerable" is ever exploited. Keep recipe messages and
docs to "surfaces a candidate," never "is exploitable."

## Naming

- Recipes: a short, descriptive, hyphenated name for what is surfaced
  (`bytecode-hash`, `ast-sketch`, `bytecode-sketch`). Versions are semver, bumped
  on any behavior change (the version is recorded in every signature's
  provenance).
- Shapes: lowercase, hyphenated (`bytecode-hash`, `ast-sketch`).
- Packages: the package directory and its `name` match the recipe (or shape) it
  provides.
