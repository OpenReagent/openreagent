# Build-framework detection

Before scanning, OpenReagent determines how a target is *meant to be built*. This
is the first step of the toolchain-integration work on the [roadmap](roadmap.md):
detection now; automatic build and artifact-fed recipes next. Detection itself is
**deterministic and performs no build** — it only inspects the filesystem — so it
is safe to run on every scan.

## What is detected

| framework | signal |
|-----------|--------|
| **Foundry** | a `foundry.toml` manifest |
| **Hardhat** | a `hardhat.config.{js,ts,cjs,mjs}` manifest |
| **Vanilla** | loose `.sol` with no recognized manifest |

Detection walks **upward** from the scan target to the nearest enclosing project
root, stopping at a `.git` boundary so it never escapes into an unrelated parent.
Scanning a subdirectory (e.g. a Foundry project's `src/`) therefore resolves to
the project root that owns it. When no manifest is found, the result is Vanilla,
rooted at the scanned directory.

## Ambiguous layouts

A project can carry both a `foundry.toml` and a `hardhat.config.*`. Detection
records **both** and marks the result `ambiguous`; it never guesses a single
framework. A single framework is chosen only by:

- an explicit `--framework foundry|hardhat|vanilla` override, or
- an interactive prompt (`openreagent detect` on a terminal).

In non-interactive use (CI, `--json`), an ambiguous target stays unresolved
(`framework: null`) rather than guessing — pass `--framework` to resolve it.

## CLI

```bash
openreagent detect ./project                 # table: detected / ambiguous / resolved
openreagent detect ./project --json          # machine-readable
openreagent detect ./project --framework foundry   # force a choice
openreagent scan ./project                   # scan also reports the detected framework
openreagent scan ./project --framework hardhat     # override for the scan
```

The scan report carries the detection under a `target` object (`framework`,
`ambiguous`, `project_root`, `detected`, `manifests`, `resolved_by`).

## Not yet supported

Truffle (`truffle-config.js`) and Brownie (`brownie-config.yaml`) are **not** yet
recognized and currently fall back to Vanilla. Adding them is tracked as future
work (see [roadmap.md](roadmap.md)).
