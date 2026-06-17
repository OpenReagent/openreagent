# Architecture

OpenReagent has two layers — a small, stable **record** and an open **registry**
of shapes and recipes — and two paths over them: **scan** (deterministic, no LLM)
and **extract** (offline, may use an LLM). The registry is distributed as
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
  solidity.py      dependency-free Solidity reader for the match path
  matching.py      shared, pure matcher helpers (site targeting, tiers, markers)
  recipe_lib.py    building blocks for recipe authors (slot-fill extractor, findings)
  scan.py          the scan engine — imports no LLM client
  extract.py       the extract engine
  llm.py           pluggable LLM client (imported only on the extract path)
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
points inside the package — that is how `canonical-divergence` loads its bundled
references. Installed packages override a built-in of the same name. See
[packages.md](packages.md).

## The scan path, end to end

```
target .sol ─┐
             ├─> solidity.load_target ─> [SourceFile, …]            (sorted, deterministic)
pool / store ┴─> pool.load_pool ───────> [Signature, …]            (shape-validated at load)

for each Signature whose recipe is enabled:
    recipe = registry.get(signature.recipe)
    findings += recipe.matcher.match(signature.value, sources, signature)

findings.sort()  ─> formatters.{json,sarif,markdown}
```

The pool comes either from a directory/file of JSON records or from the SQLite
store (`--store`). Properties that hold by construction:

- **Deterministic.** Sources and pool are processed in sorted order; every
  matcher is a pure function of `(value, code)`; output is sorted and carries no
  timestamps. The same inputs produce byte-identical findings.
- **No LLM at match time.** `scan.py` imports no LLM client, directly or
  transitively. Recipe modules import `openreagent.llm` lazily, inside the
  extractor's `extract`, which the scan path never calls. A test runs a scan in a
  fresh subprocess and asserts neither `anthropic` nor `openreagent.llm` was
  imported.
- **Shape-validated input.** Both the file pool and the store validate every
  signature's value against its recipe's shape before any matcher runs.
- **Recipe-isolated.** Recipes hold no shared mutable state, so enabling or
  disabling one recipe never changes another's output.

## The extract path, end to end

```
audit finding (json) ─> recipe.extractor.extract(finding) ─> value
                          (uses_llm? only if slots not pre-supplied)
value ─> shape.validate(value)                              (must conform)
      ─> assemble Signature with provenance.extracted_by{recipe,version,timestamp}
      ─> write signature .json  and/or  add to the store
```

A finding that already carries structured `slots` is converted with no LLM at
all. A prose-only finding is filled by the configured client
(`openreagent.llm.default_client`): an `AnthropicClient` when `ANTHROPIC_API_KEY`
is set, or a `ReplayClient` over a JSONL file for offline, reproducible
extraction.

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
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=MyExtractor(),   # source -> value (may set uses_llm=True)
    matcher=MyMatcher(),       # (value, code) -> [Finding]   (never uses an LLM)
    status=Status.EXPERIMENTAL,
))
```

`load()` imports packages in dependency order; registration is the import side
effect. Built-ins ship in the wheel under `openreagent/_data/packages`; installed
packages live under `$OPENREAGENT_HOME`. See [extending.md](extending.md).