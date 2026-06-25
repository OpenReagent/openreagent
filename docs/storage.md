# Signatures: the server and its store

Signatures live behind a **remote server** — the OpenReagent service. Clients
(the CLI, `scan`) talk to the server over HTTP; they never touch the database
directly. The server keeps signatures in a **PostgreSQL database**, but that is
an internal detail of the service.

This split exists so that matching can become **privacy-preserving**. The
server's `POST /match` endpoint is the seam where a Private Set Intersection
(PSI) protocol will later replace today's plaintext comparison, so that a client
need not download the signature set and the server need not see the client's
code. Putting a server in front of the database now is what makes that change a
swap at one boundary rather than a rewrite. See
[architecture.md](architecture.md) and [open-questions.md](open-questions.md).

```
  client (CLI / scan)  ──HTTP──▶  server  ──▶  PostgreSQL
   sends fingerprints            /match           signatures
   gets matches back          (PSI seam)
```

There is **no local file-based store**: a server is required for any `sig`
command and for `scan --store`. (You can still scan a directory/file **pool** of
`*.json` records with no server at all; see the pool below.)

## Talk to a server (clients)

Point clients at a running server:

```bash
export OPENREAGENT_SERVER_URL=http://localhost:8000
# optional bearer token, if the server was started with one:
export OPENREAGENT_SERVER_TOKEN=…
```

The client ships in the **core** package — it uses only the standard library, so
no extra is needed to talk to a server. If `OPENREAGENT_SERVER_URL` is unset (and
`--server-url` is not given), every client command exits with a clear error;
there is no local fallback.

```bash
openreagent sig add sig.json                  # a single record, an array, or JSONL
openreagent sig add ./signatures/             # every *.json under a directory
openreagent sig pull https://host/sigs.json   # fetch remote signatures into the server
openreagent sig pull github:owner/sig-repo    # …or from a GitHub repo of records
openreagent sig list                          # table of id / recipe / version
openreagent sig remove <id>
openreagent sig clear                         # empty the store (prompts unless --yes)
openreagent extract finding.json -r bytecode-hash --to-store
```

Each command reads `OPENREAGENT_SERVER_URL`; override per-invocation with
`--server-url`.

## Run a server

The server needs the `server` and `store` extras and a configured database:

```bash
pip install 'openreagent[server,store]'
export OPENREAGENT_DB_URL=postgresql://user:password@host:5432/openreagent
openreagent serve --host 0.0.0.0 --port 8000
```

- `server` extra: **FastAPI** + **uvicorn** (the HTTP service).
- `store` extra: **pg8000** (pure-Python, BSD) — the PostgreSQL driver.
- `OPENREAGENT_DB_URL` is read by the **server only**; clients never see it.
- `OPENREAGENT_SERVER_TOKEN`, if set, requires a matching `Bearer` token on every
  request.

### A database in one command (Docker)

A `docker-compose.yml` is bundled for local development:

```bash
docker compose up -d
export OPENREAGENT_DB_URL=postgresql://openreagent:openreagent@localhost:5432/openreagent
openreagent serve            # in one shell
# in another:
export OPENREAGENT_SERVER_URL=http://localhost:8000
openreagent sig list
```

The `signatures` table is created on first connect.

## Endpoints

| method & path | purpose |
|---|---|
| `GET /healthz` | liveness |
| `POST /signatures` | add signatures (`{"signatures": [record, …]}`) |
| `GET /signatures[?recipe=]` | list (optionally filtered by recipe) |
| `GET /signatures/{id}` | fetch one |
| `DELETE /signatures/{id}` | remove one |
| `DELETE /signatures` | clear all |
| `POST /match` | compare client candidates vs stored signatures (**PSI seam**) |

`/match` takes `{"candidates": {recipe: [value, …]}}` — the client's per-recipe
candidate fingerprints — and returns only the matches
(`{"matches": [{signature_id, recipe, candidate, score}, …]}`). It reveals
nothing about non-matching signatures, and the client sends fingerprints, never
its source.

## Schema (server-internal)

One row per signature:

| column | meaning |
|--------|---------|
| `id` | signature id (primary key) |
| `recipe_name`, `recipe_version` | the recipe reference |
| `value` | the value, as JSON text |
| `provenance` | the provenance list, as JSON text |
| `record` | the full canonical record, as JSON text |
| `added_at` | insert timestamp (`timestamptz`) |

On insert, the value is validated against its recipe's shape — the same check the
file pool performs at load time. A non-conforming or recipe-less signature is
rejected.

## Scanning against the server

```bash
openreagent scan ./contracts --store                          # match via $OPENREAGENT_SERVER_URL
openreagent scan ./contracts --server-url http://host:8000    # an explicit server
```

The client extracts candidate fingerprints from the target (re-running each
enabled recipe's deterministic extractor over each unit — file, function, or
contract), sends them to `/match`, and turns the returned matches into findings.
Comparison is shape-aware (digest equality / MinHash Jaccard / hash-set
containment), deterministic, and never involves an LLM. The reported `pool_size`
is the number of candidate fingerprints queried, not the server's signature count
(which the client is not told).

**v1 limitation.** Parametric recipes (MinHash `num_perm`/`ngram`, snippet
`ngram`) are compared assuming the **default** recipe parameters, which the
built-in extractors use. Signatures stored with non-default parameters may not
compare. See [open-questions.md](open-questions.md).

## Pool vs. server

For a quick, server-free run, point `--pool` at a directory or file of `*.json`
signature records:

```bash
openreagent scan ./contracts --pool ./mypool
```

The pool needs no server and matches fully in-process; the **server** is the
shared, remote source of truth.

## Provenance and sharing

Each record keeps its own provenance (source kind, source ref, and the recipe
version and timestamp of each extraction), so a store assembled from several pulls
remains auditable. Note the open question in
[open-questions.md](open-questions.md) about distributing signatures without
redistributing the underlying audit material: a `source_ref` points at material a
recipient may or may not be able to access.
