# Architecture

OpenReagent has two layers — a small, stable **record** and an open **registry**
of shapes and recipes — and two paths over them: **scan** (deterministic, no LLM)
and **extract** (offline, deterministic). The registry is distributed as
installable **packages**, and signatures live in a local **store**. This document
walks the components, traces each path end to end, and shows how a package plugs
in.

## Components

```
openreagent/
  models.py        the signature record (Part A): Signature, Provenance, RecipeRef
  shapes.py        Shape base + registry + conformance validator (Part B.1)
  recipes.py       Recipe / Extractor / Matcher / Finding + registry (Part B.2/B.3)
  packages.py      the package system: manifest, discovery, dependency-ordered load, install
  sources.py       fetch sources from local path, zip, http(s) zip, github:owner/repo
  loader.py        thin facade: load the whole registry, resolve the sample pool
  store.py         SQLite signature store + parse/pull of remote signatures
  pool.py          load a pool from a directory, a file, or the store
  solidity.py      dependency-free Solidity reader 
  frameworks.py    deterministic build-framework detection (Foundry/Hardhat/Vanilla)
  building.py      arm's-length build (forge/hardhat/solc) -> Bytecode/AST/ABI artifacts
  codeview.py      the unified scan input: Code + Bytecode + AST + ABI
  matching.py      shared, pure matcher helpers (site targeting, tiers, artifacts)
  recipe_lib.py    building blocks for recipe authors (the make_finding helper)
  scan.py          the scan engine — deterministic, no LLM
  extract.py       the extract engine (offline, deterministic)
  formatters.py    JSON / SARIF 2.1.0 / Markdown
  cli.py           the `openreagent` command-line interface
packages/          one directory per package; each self-contained (a recipe's
                   references are bundled inside its own package directory)
pool/              sample signature records
```

The **record layer** (`models.py`) knows nothing about a value's internals: a
value is an opaque mapping there. The **registry layer** (`shapes.py`,
`recipes.py`) defines shapes and recipes once and shares them. Keeping the two
apart is what lets a record stay four fields while the registry grows.

## The package system

Detectors and shapes are distributed as packages — self-contained bundles with
an `openreagent.json` manifest, an entry module that registers shapes/recipes on
import, and any assets bundled inside (a recipe's canonical references live in
the package, not in a global directory).

```
discover()        gather manifests from built-in packages + $OPENREAGENT_HOME/packages
resolve_order()   topologically sort by `requires` (a shape loads before a recipe needing it)
load()            import each package's entry module in order; registration is the side effect
install(source)   materialize a source (sources.py) and copy its package(s) under $OPENREAGENT_HOME
```

A package is imported from its own directory, so its entry module's `__file__`
points inside the package — that is how a package loads any bundled assets
(e.g. reference data) relative to itself. Installed packages override a built-in
of the same name. See
[packages.md](packages.md).

## The scan path, end to end

```
target ─┬─> frameworks.detect ─> building.build ─> [Artifact, …]   (Bytecode/AST/ABI; best-effort)
        └─> solidity.load_target ─> [SourceFile, …]                (the lexical Code view)
                         │
                         └─> codeview.CodeView(sources, build)      (unified: Code+Bytecode+AST+ABI)
pool / store ─> pool.load_pool ───────────> [Signature, …]         (shape-validated at load)

for each Signature whose recipe is enabled:
    recipe = registry.get(signature.recipe)
    findings += recipe.matcher.match(signature.value, code, signature)   # code = CodeView

findings.sort()  ─> formatters.{json,sarif,markdown}
```

The matcher receives a `CodeView` — a `list[SourceFile]` (so existing matchers are
unchanged) that also carries the build's per-source Bytecode/AST/ABI. Recipes that
want artifacts read them via `matching.artifacts_for/ast_for/...`; when a target
was not built (no toolchain, offline, partial code) there are no artifacts and the
recipe falls back to the lexical Code view. The lexical reader (`solidity.py`) is
thus the **fallback**, not the primary structural source.

The pool comes either from a directory/file of JSON records or from the SQLite
store (`--store`). Properties that hold by construction:

- **Deterministic.** Sources and pool are processed in sorted order; every
  matcher is a pure function of `(value, code)`; output is sorted and carries no
  timestamps. The same inputs produce byte-identical findings.
- **No LLM, anywhere.** Recipes are deterministic and hashable on both paths;
  the package ships no LLM client. A test runs a scan in a fresh subprocess and
  asserts no LLM module (e.g. `anthropic`) was imported.
- **Shape-validated input.** Both the file pool and the store validate every
  signature's value against its recipe's shape before any matcher runs.
- **Recipe-isolated.** Recipes hold no shared mutable state, so enabling or
  disabling one recipe never changes another's output.

## The extract path, end to end

```
source (json: contract / build artifact) ─> recipe.extractor.extract(source) ─> value
value ─> shape.validate(value)                              (must conform)
      ─> assemble Signature with provenance.extracted_by{recipe,version,timestamp}
      ─> write signature .json  and/or  add to the store
```

Extraction is **deterministic and offline**: it reduces the source to the
recipe's hashable value (e.g. a normalized digest or a MinHash signature) with no
LLM. The same source yields the same value every run.

## The signature store

`store.py` is a SQLite-backed collection of signature records
(`$OPENREAGENT_HOME/signatures.db`). It validates a value against its recipe's
shape on insert (the same check the file pool does at load), can be scanned
directly (`scan --store`), and can be filled from a remote source — a JSON/JSONL
URL, a zip, a GitHub repo, or a local directory — via `sig pull`. See
[storage.md](storage.md).

## How a package plugs in

A package is a directory with a manifest and an entry module that registers a
shape and/or a recipe:

```python
# packages/my-recipe/detector.py
register_recipe(Recipe(
    name="my-recipe", version="1.0.0",
    shape=ShapeRef(name="my-shape", version="1.0.0"),
    extractor=MyExtractor(),   # source -> value   (deterministic, no LLM)
    matcher=MyMatcher(),       # (value, code) -> [Finding]   (never uses an LLM)
    status=Status.EXPERIMENTAL,
))
```

`load()` imports packages in dependency order; registration is the import side
effect. Built-ins ship in the wheel under `openreagent/_data/packages`; installed
packages live under `$OPENREAGENT_HOME`. See [extending.md](extending.md).