# Build-framework detection and building

Before scanning, OpenReagent determines how a target is *meant to be built* and
then builds it. This is the toolchain-integration work on the
[roadmap](roadmap.md): detection and automatic build are in place; feeding the
build artifacts to matchers is the next step. **Detection** is deterministic and
performs no build — it only inspects the filesystem — so it is always safe;
**building** runs the real toolchain at arm's length and is best-effort.

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

## Building

Once a single framework is resolved, OpenReagent builds the target by running the
project's real toolchain **as a separate process** — never importing a compiler
into the scan process, so the core stays dependency-light:

| framework | command | artifacts read from |
|-----------|---------|---------------------|
| **Foundry** | `forge build` | `out/**/*.json` |
| **Hardhat** | `npx hardhat compile` | `artifacts/build-info/*.json` |
| **Vanilla** | `solc` via the `bytecode` extra (`py-solc-x`) | compiler standard-JSON output |

Each build yields compiled **bytecode** and, where the toolchain emits it, the
**AST** per source. Foundry and Vanilla share one solc standard-JSON parser.

Building is **best-effort and never aborts a scan**. A missing toolchain, the
absent `bytecode` extra, an ambiguous (unresolved) layout, or a build failure is
recorded as a stable status (`ok` / `skipped` / `failed` / `disabled`) with a
reason category — and the scan continues on the lexical source view. Skip the
build entirely with `--no-build`.

**solc fallback.** The goal is artifacts, not a particular toolchain. So when a
framework toolchain is *unavailable* — no `forge`, no Hardhat install, no
`package.json` — the build falls back to compiling the discovered `.sol`
directly with `solc`. A self-contained project (no external imports) therefore
yields bytecode/AST even without its framework set up; a project that relies on
the framework's import resolution (Foundry `lib/`, Hardhat `node_modules`) simply
fails the fallback gracefully. The report shows the fallback in the build reason.

**Installing toolchains.** By default a scan stays **offline**: the vanilla path
uses only an already-installed `solc`, and Hardhat must already have its
`node_modules`. With `--install` OpenReagent fetches what's missing — a
pragma-matching `solc` (via `py-solc-x`) for vanilla, and the project's
`npm install` for Hardhat. A bare Hardhat project (just a `hardhat.config.*`
with no `package.json`) is bootstrapped with `npm install hardhat`; a TypeScript
config additionally pulls `ts-node`/`typescript` and is compiled with `ts-node`
pinned to CommonJS, so **no `tsconfig.json` is required**. `openreagent build` does this **by default** (it's an
explicit compile request); `openreagent scan` keeps it **off by default** (pass
`--install` to enable) so plain scans stay offline and deterministic. The vanilla
compiler is chosen to satisfy the source `pragma solidity` (the same way
forge/hardhat pick one). Foundry fetches its own `solc` via `svm`; `forge` itself
must be installed by you.

## CLI

```bash
openreagent detect ./project                 # table: detected / ambiguous / resolved
openreagent detect ./project --json          # machine-readable
openreagent detect ./project --framework foundry   # force a choice
openreagent build ./project                  # build (auto-installs missing solc / node deps)
openreagent build ./project --no-install     # build but stay offline
openreagent build ./project --json           # status, compiler, artifact summaries
openreagent build ./project --debug          # show the raw compiler output on failure
openreagent scan ./project                   # scan detects + builds (offline), then matches
openreagent scan ./project --install         # allow fetching solc / node deps for the build
openreagent scan ./project --framework hardhat     # override the framework
openreagent scan ./project --no-build        # scan the lexical source view only
openreagent scan ./project --debug           # also print the build log to stderr
```

The scan report carries the detection and build under a `target` object
(`framework`, `ambiguous`, `project_root`, `detected`, `manifests`,
`resolved_by`, and a `build` summary: `status`, `compiler`, `artifacts`,
`reason`).

## Not yet supported

Truffle (`truffle-config.js`) and Brownie (`brownie-config.yaml`) are **not** yet
recognized and currently fall back to Vanilla. Adding them is tracked as future
work (see [roadmap.md](roadmap.md)).
