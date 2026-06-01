# Packages

OpenReagent's detectors and shapes are distributed as **packages** — self-
contained, installable bundles. The model is deliberately npm-like: a small
manifest, an entry that registers what the package provides, declared
dependencies, and a registry you install from local paths, zips, URLs, or
GitHub.

## What a package is

A directory containing:

- `openreagent.json` — the manifest;
- an **entry module** (default `detector.py`) that registers a shape and/or a
  recipe when imported;
- any **assets** the recipe needs, bundled inside the package (a recipe's
  canonical references live here, never in a global directory).

## Manifest

```json
{
  "name": "canonical-divergence",
  "version": "1.0.0",
  "kind": "recipe",
  "entry": "detector.py",
  "requires": ["slot-spec"],
  "description": "Flags divergence from a canonical reference.",
  "provides": { "recipes": ["canonical-divergence"], "shapes": [] }
}
```

| field | meaning |
|-------|---------|
| `name` | unique package name; the install directory uses it |
| `version` | semver |
| `kind` | `recipe`, `shape`, or `bundle` (registers both) |
| `entry` | module imported to perform registration |
| `requires` | other packages that must load first (e.g. a shape a recipe uses) |
| `provides` | informational index of recipe/shape names |

## Dependency resolution

Loading discovers every available package and topologically sorts by `requires`,
so a shape package loads before any recipe that depends on it. A missing
dependency or a cycle is an error. Resolution spans **both** built-in and
installed packages, so a recipe installed from GitHub can depend on a built-in
`slot-spec`, or on another package you install alongside it.

## Where packages live

- **Built-in** packages ship inside the wheel (`openreagent/_data/packages`) and
  are always available.
- **Installed** packages live under `$OPENREAGENT_HOME/packages` (default
  `~/.openreagent/packages`). An installed package **overrides** a built-in of
  the same name, so you can pin or patch a detector locally.

Set `OPENREAGENT_HOME` to relocate both the installed packages and the signature
store.

## Installing

```bash
openreagent install ./my-detector             # local directory
openreagent install ./my-detector.zip         # local zip
openreagent install https://host/pkg.zip      # remote zip
openreagent install github:owner/repo         # GitHub repo (default branch)
openreagent install github:owner/repo@v1.2.0  # at a branch / tag / sha
openreagent install https://github.com/owner/repo
```

A single source may contain several packages (a repo of detectors); every
`openreagent.json` found under it is installed.

```bash
openreagent packages          # list built-in + installed (origin column)
openreagent packages --json
openreagent uninstall my-detector
```

## Ad-hoc loading without installing

For development, load a directory of packages for a single scan without copying
them into the store:

```bash
openreagent scan ./contracts --recipe-dir ./my-detectors --enable '*'
```

## Transport

Fetching is handled by `openreagent.sources` using only the standard library.
GitHub sources download a codeload zip of the requested ref; http(s) sources are
plain zip downloads; `file://` and local paths are read directly. Nothing in the
package or transport layer is imported by the scan path.
