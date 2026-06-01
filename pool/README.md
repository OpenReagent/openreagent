# Pool

A *pool* is a directory of signature records (`*.json`). The scan path loads
the pool, validates every signature against its recipe's shape, and runs the
matchers.

This shipped pool is **empty by default**, apart from a few hand-authored sample
signatures under `samples/`:

- `samples/sig-missing-access-control.json` — one per production recipe
- `samples/sig-amm-spot-price.json`

The samples were written from scratch for documentation. They are **not**
extracted from any licensed corpus or audit report, and they carry no
measurement data — only the slots a matcher needs.

You can point the CLI at any pool directory:

```bash
openreagent scan ./contracts                 # uses this shipped pool
openreagent scan ./contracts --pool ./mypool # uses your own pool
openreagent scan ./contracts --pool ./empty  # an empty directory: no findings, no error
```

Signatures you extract with `openreagent extract` can be written here (or into
a local pool of your own). Local pools that you do not want tracked can live
under `pool/local/` (git-ignored).
