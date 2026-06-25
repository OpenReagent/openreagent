# OpenReagent

OpenReagent is a framework for specifying recurring smart-contract
vulnerabilities as *signatures* and matching them against Solidity code. A
signature names a *recipe*; the recipe pins both how the signature was extracted
from a source and how it is matched against code. Matching is deterministic and
uses no LLM. OpenReagent is **not** a model of attacker intent or end-to-end
exploitability, **not** a replacement for an audit, and it ships **no** bundled
baseline corpus — it surfaces code consistent with a signature so a human can
look closer.

The framework is the product. Detectors and shapes are distributed as
installable **packages** (a small registry, like "npm for detectors and
shapes"), and signatures live behind a remote server you match against without
downloading them.

## Install

```bash
pip install openreagent                 # core (scan a file/dir pool, extract, CLI)
pip install 'openreagent[bytecode]'     # + bytecode recipes (solc, pyevmasm)
pip install 'openreagent[sketch]'       # + the ast-sketch near-duplicate recipe
pip install 'openreagent[server,store]' # + run a server (FastAPI/uvicorn + pg8000)
pip install 'openreagent[all]'          # everything
```

Python 3.11+ is required. The core scan path has only three dependencies
(`pydantic`, `typer`, `rich`) and runs anywhere — including the **client** that
talks to a server, which is stdlib-only. Heavier libraries used by individual
recipes, or to *run* a server, are optional extras.

## How detection works (the scan path)

Detection is a pool of signatures run against your code:

1. OpenReagent loads the **pool** — a directory of signature records (matched
   in-process) *or*, with `--store`, queries a remote **server** that holds the
   signatures — validating every signature against its recipe's shape.
2. For each signature whose recipe is enabled, the recipe's **matcher** runs
   over the target Solidity. Each matcher is a deterministic function of
   `(signature value, code)`. **No matcher uses an LLM.**
3. Findings are returned in a stable order and emitted as JSON, SARIF 2.1.0, or
   Markdown.

The same pool and the same input produce byte-identical findings every run.
Production recipes are enabled by default; experimental and journey recipes are
off by default and enabled explicitly.

```bash
openreagent scan ./contracts                       # default pool + production recipes
openreagent scan ./contracts -f sarif -o out.sarif # SARIF to a file
openreagent scan ./contracts --enable '*'          # enable every recipe
openreagent scan ./contracts --pool ./mypool       # use a directory pool
openreagent scan ./contracts --store               # match against the remote server
```

## Detectors and shapes are installable packages

A package is a self-contained bundle — a manifest, an entry module that
registers a shape and/or a recipe, and any assets it needs (a recipe's canonical
references live **inside** the package). Install one from a local path, a zip, an
http(s) zip, or a GitHub repository:

```bash
openreagent install ./my-detector             # local directory
openreagent install ./my-detector.zip         # local zip
openreagent install https://host/pkg.zip      # remote zip
openreagent install github:owner/repo         # GitHub repo (default branch)
openreagent install github:owner/repo@v1.2.0  # at a branch / tag / sha
openreagent packages                          # list built-in + installed packages
openreagent uninstall my-detector
```

Built-in packages ship with OpenReagent; user-installed packages live under
`$OPENREAGENT_HOME` (default `~/.openreagent`) and override a built-in of the
same name. See [docs/packages.md](docs/packages.md).

## How extraction works (the extract path)

Extraction turns one source (a contract, a build artifact) into one signature
record. It is kept separate from scanning, runs offline, and is **deterministic
and uses no LLM** — it reduces the source to the recipe's hashable value. Every
extraction is recorded in the signature's provenance.

```bash
openreagent extract finding.json --recipe bytecode-hash -o sig.json
openreagent extract finding.json --recipe ast-sketch --to-store
```

## The server (and its store)

Signatures live behind a **remote server**. Clients talk to the server over
HTTP and never touch the database; the server keeps signatures in PostgreSQL.
This split is deliberate: the server's `POST /match` endpoint is the seam where
a **privacy-preserving** (PSI) protocol will later replace plaintext comparison,
so a client need not download the signature set and the server need not see the
client's code.

Clients only set a URL (the client is stdlib-only, no extra):

```bash
export OPENREAGENT_SERVER_URL=http://localhost:8000
openreagent sig add sig.json                  # add a record (or a dir of them)
openreagent sig pull github:owner/sig-repo    # fetch signatures into the server
openreagent sig list                          # list stored signatures
openreagent scan ./contracts --store          # match against the server
```

Run a server (needs the `server` + `store` extras and a database; a
`docker-compose.yml` is bundled):

```bash
docker compose up -d
export OPENREAGENT_DB_URL=postgresql://openreagent:openreagent@localhost:5432/openreagent
openreagent serve --port 8000
```

For a quick, server-free run, scan a directory pool instead:
`scan ./contracts --pool ./mypool`. See [docs/storage.md](docs/storage.md).

## Schema in one minute

A signature record is four fields: an `id`, a `recipe` reference, a `value` that
conforms to the recipe's shape, and a list of `provenance` sources. Everything
about *how* a signature is extracted and matched lives in the recipe, not on each
record. Each detector is its own recipe over a shared shape — the recipe identity
*is* the detector. See [docs/schema.md](docs/schema.md) and
[docs/architecture.md](docs/architecture.md).

## CLI guide

| command | what it does |
|---------|--------------|
| `scan <path>` | load pool/store, run matchers, emit findings (deterministic, no LLM) |
| `detect <path>` | report the target's build framework — Foundry / Hardhat / Vanilla (no build) |
| `build <path>` | build the target at arm's length (forge / hardhat / solc); report artifacts |
| `extract <finding>` | one source → one signature record (offline; deterministic, no LLM) |
| `install <source>` | install a detector/shape package (dir, zip, url, `github:owner/repo`) |
| `uninstall <name>` | remove an installed package |
| `packages` | list built-in and installed packages |
| `recipes` | list registered recipes with maturity status |
| `serve` | run the OpenReagent server (the store API; needs `server`+`store` extras) |
| `sig add/pull/list/remove/clear` | manage signatures on the remote server |
| `validate <file>` | check a signature value against its recipe's shape |

Run `openreagent <command> --help` for all options.

## Status reporting

Recipes report **maturity only** — `production`, `experimental`, or `journey`.
This repository publishes no precision, recall, or CI figures; see
[docs/evaluation.md](docs/evaluation.md).

## Community

- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Direction and open design questions: [docs/roadmap.md](docs/roadmap.md) and
  [docs/open-questions.md](docs/open-questions.md).
- OpenReagent is developed in the open under the Linux Foundation Decentralized
  Trust (LFDT). Working-group, chat, and recording links are on the project's
  LFDT page. *(Fill these in for your deployment.)*

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
