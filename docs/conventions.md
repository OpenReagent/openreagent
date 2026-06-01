# Conventions

Guidance for authoring signatures and recipes: how detectors relate, how to fill
slots well, and how the built-in marker vocabularies work.

## Detector adjacency

Detectors are not disjoint. A finding often sits near a boundary, and the right
recipe is a judgement. A few recurring adjacencies, by recipe name:

- **`internal-absence` ↔ `canonical-divergence`.** Both are about a *missing*
  element. Use **`internal-absence`** when the missing element is defined by the
  project's own internal contract (an invariant the codebase establishes
  elsewhere). Use **`canonical-divergence`** when the missing element is defined
  by an *external* canonical pattern (a standard such as a TWAP oracle or a
  two-step ownership transfer). If the audit cites an external reference, prefer
  `canonical-divergence`; if it cites the project's own other functions, prefer
  `internal-absence`.
- **`operand-mismatch` ↔ `operator-direction`.** `operand-mismatch` is the
  *wrong quantity* in an otherwise correct comparison; `operator-direction` is
  the *right quantity* compared the *wrong way*. If the operands are correct but
  the inequality points the wrong direction, it is `operator-direction`.
- **`unbound-caller-value` ↔ `internal-absence`.** An unbound caller-supplied
  value is a kind of absence (a missing bound). Use `unbound-caller-value` when
  the missing thing is specifically a constraint on a parameter; use
  `internal-absence` when it is a broader required element (an access-control
  guard, a pause check).
- **`ordering-violation` ↔ `aggregated-state`.** `ordering-violation` is about
  the order of two operations within a function; `aggregated-state` is about two
  pieces of state that must move together. A reentrancy-style "external call
  before state update" is `ordering-violation`.
- **`generic-slot`.** When a finding is expressible in the slot vocabulary but
  fits no specific detector, use `generic-slot`. It is a fallback, not a
  catch-all to reach for first; prefer a specific recipe whenever one fits.

## Filling slots well (for extractor authors)

The slot-spec vocabulary is `operation`, `attribute`, `operator`, `site`,
`intended_order`, `canonical_reference`, plus any recipe-specific keys, and a
`freeform` string. Guidance:

- **`site` is the strongest signal.** Provide it as a structured object —
  `{"function": "...", "file": "..."}` (or `"functions"` / `"files"` lists), not
  as prose. A named function and file lets a matcher target precisely and score a
  match higher. Prose in `site` is ignored for targeting.
- **Prefer enumerable tokens over sentences.** `operation`, `attribute`, and
  `intended_order` are matched as tokens or substrings. `"access_control"` is
  better than `"there should be an access control check here"`. Put narrative in
  `freeform`.
- **Make `operator` explicit.** `{"intended": ">=", "wrong": "<="}` is
  unambiguous; a single `{"intended": ">="}` lets the matcher infer the reverse.
- **Name the reference for `canonical-divergence`.** `canonical_reference` must
  resolve to a record bundled inside the `canonical-divergence` package (a bare
  id string or `{"reference_id": "..."}`).
- **Override markers when you know them.** Where a recipe consults a built-in
  marker table (below), you can supply explicit markers in `attribute` to extend
  or replace the defaults for a specific signature.

## Built-in marker vocabularies

The slot recipes decide "is this element present?" using small, public marker
tables in `openreagent/_markers.py`. A *marker* is a lowercase token or substring
whose presence in a function body is evidence the element is implemented (matched
case-insensitively, as an identifier/call token or a body substring, so
`onlyOwner`, `address(0)`, and `balances[` all work). The tables cover common
required elements (access control, zero-address checks, reentrancy guards,
deadline and slippage checks, …), keyed state, and aggregate state. They encode
**convention, not measurement**; edit them freely and send a pull request if a
vocabulary is missing a common spelling.

## Naming

- Recipes: a short, descriptive, hyphenated name for what is surfaced
  (`canonical-divergence`, `unbound-caller-value`, `bytecode-hash`). Versions are
  semver.
- Shapes: lowercase, hyphenated (`slot-spec`, `bytecode-hash`, `ast-sketch`).
- Reference ids: `<vendor>/<pattern>` (`uniswap_v2/twap`).
- Packages: the package directory and its `name` match the recipe (or shape) it
  provides.
