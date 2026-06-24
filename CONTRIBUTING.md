# Contributing to OpenReagent

OpenReagent is developed in the open under the Linux Foundation Decentralized
Trust (LFDT). Contributions of packages (detectors and shapes), references,
fixtures, and documentation are welcome.

## Ways to contribute

- **Author a package** (the most common contribution): a deterministic, hashable
  detector recipe over a new or existing shape, or a shape on its own. A package
  is one directory with an `openreagent.json` manifest and an entry module. See
  [docs/extending.md](docs/extending.md) for a worked example and
  [docs/packages.md](docs/packages.md) for the format.
- **Bundle reference data** a recipe needs inside its own package, loaded relative
  to the entry module's `__file__` (never a global directory).
- **Improve documentation** in `docs/`.

## Development setup

```bash
git clone <this-repo> && cd openreagent
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'      # add ',bytecode,sketch' to test the journey recipes
pytest
```

Python 3.11+ is required. Built-in packages live under `packages/`; each is a
self-contained directory loaded in dependency order.

## Authoring a package — checklist

1. Create `packages/<your-package>/` with an `openreagent.json` manifest and an
   entry module that registers your shape and/or recipe.
2. Keep the two invariants: a matcher uses **no LLM**, and a matcher is a **pure
   function** of `(value, code)` (no shared mutable state, no I/O beyond the
   supplied sources). The determinism and isolation guards in `tests/` must keep
   passing.
3. Declare dependencies in `requires` (a recipe over a separate shape package
   requires that shape package; a self-contained recipe requires nothing).
4. Bundle any assets (references) **inside** the package and load them relative
   to the entry module.
5. Choose a `status` honestly: `experimental` for a new recipe; `production` only
   after substantial review (a maintainer decision).
6. Add a fixture contract under `tests/fixtures/` and a test that scans it and
   asserts the expected findings. Add an install test if your package has unusual
   structure (`tests/test_packages.py` shows the pattern).
7. Add a row to [docs/recipes.md](docs/recipes.md). **Do not** add precision,
   recall, or CI numbers to any public file (see
   [docs/evaluation.md](docs/evaluation.md)).
8. Run `pytest`. All guards must pass.

## Running the tests

```bash
pytest                       # the full suite, including:
                             #  - determinism (same pool + input -> identical output)
                             #  - no LLM client imported on the scan path
                             #  - shape conformance on every pool/store signature at load
                             #  - package discovery, dependency order, install (dir + zip)
                             #  - recipe isolation
                             #  - end-to-end on the Solidity fixtures
                             #  - the SQLite signature store and scan --store
```

## Review expectations

- A package is reviewed for correctness, determinism, isolation, clarity of its
  matcher, and that its manifest and dependencies are honest. Reviewers will ask
  what the recipe surfaces and what it does **not** claim (it surfaces candidates;
  it does not assert exploitability).
- Promotion from `experimental` to `production` is a separate, explicit decision
  based on review depth — not on a number.
- Keep prose free of marketing language and free of precision/CI figures.

## Pull requests

1. Branch from `main`.
2. Make the change with tests and a docs row where relevant.
3. Open a pull request describing what the package surfaces and the review you
   have done. Sign off your commits per the project's DCO if required by the
   working group.
4. Bring larger design questions to the LFDT working group first (links on the
   project's LFDT page).

## License of contributions

By contributing, you agree your contributions are licensed under Apache-2.0, the
license of this project.
