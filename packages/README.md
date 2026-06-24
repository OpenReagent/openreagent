# Packages

OpenReagent's detectors and shapes are distributed as **packages** — self-
contained bundles you can install from a local path, a zip, an http(s) zip, or a
GitHub repository (think "npm for detectors and shapes"). Each package is a
directory with an `openreagent.json` manifest, an entry module that registers
its shapes and/or recipes on import, and any assets it needs bundled inside it
(a recipe's canonical references live *in the package*, never in a global
directory).

## Manifest (`openreagent.json`)

```json
{
  "name": "bytecode-hash",
  "version": "1.0.0",
  "kind": "recipe",
  "entry": "detector.py",
  "requires": [],
  "description": "…",
  "provides": { "recipes": ["bytecode-hash"], "shapes": ["bytecode-hash"] }
}
```

`requires` lists other packages that must load first (a recipe over a separate
shape package requires that shape package). Loading is dependency-ordered.

## Built-in packages

All built-in recipes are deterministic and hashable (no LLM, no ML).

| package | kind | requires | provides |
|---------|------|----------|----------|
| `bytecode-hash` | bundle | — | shape + recipe: exact/near-exact clones (journey) |
| `ast-sketch` | bundle | — | shape + recipe: lightly modified near-duplicates (journey) |

Built-in packages ship inside the wheel. User-installed packages live under
`$OPENREAGENT_HOME` (default `~/.openreagent/packages`) and override a built-in
of the same name.

## Installing

```bash
openreagent install ./my-detector            # local directory
openreagent install ./my-detector.zip        # local zip
openreagent install https://host/pkg.zip     # remote zip
openreagent install github:owner/repo        # GitHub repo (default branch)
openreagent install github:owner/repo@v1.2.0 # at a branch / tag / sha
openreagent packages                         # list installed + built-in
openreagent uninstall my-detector
```

A source may contain more than one package (a repo of detectors); each is
installed. See [../docs/packages.md](../docs/packages.md) and
[../docs/extending.md](../docs/extending.md) to author one.
