# Extending OpenReagent

The registry is open and distributed as packages. You author a package — a
directory with a manifest and an entry module — and install it from a local
path, a zip, an http(s) zip, or a GitHub repository. A package can provide a
shape, a recipe, or both, and bundles any assets it needs inside itself.

## Anatomy of a package

```
missing-deadline/
  openreagent.json     # manifest
  detector.py          # entry module: registers the recipe on import
  references/          # (optional) assets the recipe loads relative to itself
```

`openreagent.json`:

```json
{
  "name": "missing-deadline",
  "version": "1.0.0",
  "kind": "recipe",
  "entry": "detector.py",
  "requires": ["slot-spec"],
  "description": "Flags a function with no deadline check.",
  "provides": { "recipes": ["missing-deadline"], "shapes": [] }
}
```

`detector.py` — a worked recipe over the shared `slot-spec` shape:

```python
from openreagent.matching import function_in_scope, marker_present, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME, VERSION = "missing-deadline", "1.0.0"
DEADLINE_MARKERS = ["deadline", "block.timestamp", "expiry", "expired"]


class DeadlineExtractor(SlotFillExtractor):
    impl = "missing-deadline-slot-fill"
    version = "1.0.0"
    slot_keys = ("site",)


class DeadlineMatcher(Matcher):
    impl = "missing-deadline-detector"
    version = "1.0.0"

    def match(self, value, sources, signature):
        funcs, files = site_targets(slot(value, "site"))
        out = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            if marker_present(fn, DEADLINE_MARKERS):
                continue  # a deadline check is present
            out.append(make_finding(
                NAME, VERSION, signature, src, fn, fn.start_line, 0.7,
                message=f"{fn.name} has no deadline check", details={},
            ))
        return out


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=DeadlineExtractor(), matcher=DeadlineMatcher(),
    status=Status.EXPERIMENTAL, note="function missing a deadline check",
))
```

Install and use it:

```bash
openreagent install ./missing-deadline
openreagent recipes                 # missing-deadline now appears
openreagent scan ./contracts --enable missing-deadline
```

### Rules every recipe must follow

- **The matcher never uses an LLM.** `Matcher.uses_llm` stays `False`; the
  constructor rejects a recipe whose matcher sets it `True`.
- **The matcher is a pure function of `(value, code)`.** No shared mutable state,
  no I/O beyond the supplied sources. This preserves determinism and isolation.
- **The extractor produces a value that conforms to the shape.** Extraction
  validates against the shape before a record is written.
- **Version your package and recipe** with semver and bump on behavior changes;
  the recipe version is recorded in every signature's provenance.

## Bundle assets inside the package (e.g. references)

A recipe owns its assets. Load them relative to the entry module so they travel
with the package when installed:

```python
from pathlib import Path
REFERENCES_DIR = Path(__file__).resolve().parent / "references"
```

The built-in `canonical-divergence` package does exactly this; there is no global
references directory.

## Add a shape (its own package, or bundled with a recipe)

A shape is a pydantic model registered with `register_shape`. Ship it as a `kind:
"shape"` package that recipes depend on via `requires`, or register it in the
same entry module as a self-contained recipe (as `bytecode-hash` and `ast-sketch`
do):

```python
from pydantic import BaseModel, ConfigDict
from openreagent.shapes import Shape, register_shape


class RegexRuleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str
    flags: str = ""


register_shape(Shape(name="regex-rule", version="1.0.0", model=RegexRuleV1))
```

## Publish and install

Push the package directory (or a repo of several packages) to GitHub, or
distribute a zip:

```bash
openreagent install github:owner/my-detectors          # default branch
openreagent install github:owner/my-detectors@v1.0.0   # a tag/branch/sha
openreagent install https://host/my-detector.zip
openreagent install ./my-detector.zip
openreagent install ./my-detector                      # local directory
```

A source may contain more than one package (a repo of detectors); each
`openreagent.json` found is installed. Dependencies are resolved at load time
against the union of built-in and installed packages, so install a recipe's
required shape package too if it is not built in.

## Test your package

Add a fixture contract and a test that scans it with your recipe enabled and
asserts the expected findings. The existing `tests/` show the pattern, including
the determinism, isolation, and no-LLM guards your recipe must keep passing, plus
`tests/test_packages.py` for installing from a directory and a zip.
