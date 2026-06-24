# Extending OpenReagent

The registry is open and distributed as packages. You author a package — a
directory with a manifest and an entry module — and install it from a local
path, a zip, an http(s) zip, or a GitHub repository. A package can provide a
shape, a recipe, or both, and bundles any assets it needs inside itself.

## Anatomy of a package

```
comment-hash/
  openreagent.json     # manifest
  detector.py          # entry module: registers a shape + recipe on import
  references/          # (optional) assets the recipe loads relative to itself
```

`openreagent.json`:

```json
{
  "name": "comment-hash",
  "version": "1.0.0",
  "kind": "recipe",
  "entry": "detector.py",
  "requires": [],
  "description": "Exact clone by a comment-stripped source-text hash.",
  "provides": { "recipes": ["comment-hash"], "shapes": ["comment-hash"] }
}
```

`detector.py` — a worked, self-contained, hashable recipe (registers its own
shape; deterministic; no LLM). It hashes a normalized source view and flags an
exact match:

```python
from pydantic import BaseModel, ConfigDict
from openreagent._hashing import keccak256
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import make_finding
from openreagent.shapes import Shape, ShapeRef, register_shape
from openreagent.solidity import _mask

NAME, VERSION = "comment-hash", "1.0.0"


class CommentHashV1(BaseModel):           # the value shape
    model_config = ConfigDict(extra="forbid")
    digest: str


register_shape(Shape(name="comment-hash", version="1.0.0", model=CommentHashV1))


def _normalize(text: str) -> str:         # strip comments/strings, collapse ws
    return " ".join(_mask(text).split())


class CommentHashExtractor(Extractor):    # source -> value (deterministic)
    impl = "comment-hash"
    version = "1.0.0"

    def extract(self, source):
        text = source.get("source") or ""
        return {"digest": keccak256(_normalize(text).encode("utf-8"))}


class CommentHashMatcher(Matcher):        # (value, code) -> findings (no LLM)
    impl = "comment-hash"
    version = "1.0.0"

    def match(self, value, sources, signature):
        out = []
        for src in sources:
            if keccak256(_normalize(src.text).encode("utf-8")) == value.get("digest"):
                fn0 = src.functions[0] if src.functions else None
                out.append(make_finding(
                    NAME, VERSION, signature, src, fn0 or src, (fn0.start_line if fn0 else 1),
                    1.0, message=f"comment-stripped clone of {getattr(signature, 'id', '?')}",
                ))
        return out


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="comment-hash", version="1.0.0"),
    extractor=CommentHashExtractor(), matcher=CommentHashMatcher(),
    status=Status.EXPERIMENTAL, note="exact comment-stripped source clone",
))
```

Install and use it:

```bash
openreagent install ./comment-hash
openreagent recipes                 # comment-hash now appears
openreagent scan ./contracts --enable comment-hash
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

Load assets relative to the entry module's `__file__` so they travel with the
package when it is installed; there is no global references directory.

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
