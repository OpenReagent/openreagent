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
  "name": "canonical-divergence",
  "version": "1.0.0",
  "kind": "recipe",
  "entry": "detector.py",
  "requires": ["slot-spec"],
  "description": "…",
  "provides": { "recipes": ["canonical-divergence"], "shapes": [] }
}
```

`requires` lists other packages that must load first (a recipe over `slot-spec`
requires the `slot-spec` shape package). Loading is dependency-ordered.

## Built-in packages

| package | kind | requires | provides |
|---------|------|----------|----------|
| `slot-spec` | shape | — | shape `slot-spec/v1` |
| `internal-absence` | recipe | `slot-spec` | a required element absent at a named site (production) |
| `canonical-divergence` | recipe | `slot-spec` | divergence from a bundled canonical reference (production) |
| `operand-mismatch` | recipe | `slot-spec` | operation reads the wrong operand (experimental) |
| `operator-direction` | recipe | `slot-spec` | comparison operator the wrong way (experimental) |
| `unbound-caller-value` | recipe | `slot-spec` | caller value used without a binding (experimental) |
| `ordering-violation` | recipe | `slot-spec` | two operations in the wrong order (experimental) |
| `aggregated-state` | recipe | `slot-spec` | aggregate vs keyed state inconsistency (experimental) |
| `generic-slot` | recipe | `slot-spec` | expressible but unclassified fallback (experimental) |
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
