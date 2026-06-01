# Bundled references (canonical-divergence)

These canonical references belong to the `canonical-divergence` recipe and ship
**inside** this package. The recipe loads them relative to its own module, so
installing the package from GitHub or a zip brings the references with it — there
is no global reference directory.

A reference declares:

| field | meaning |
|-------|---------|
| `reference_id` | stable id; a signature's `canonical_reference` slot names this |
| `name`, `category`, `description` | human-facing documentation |
| `site_match.name_patterns` | glob patterns used only as a fallback locator |
| `site_match.body_match_tokens` | body tokens used as a fallback locator |
| `required_markers` | markers a conforming implementation must contain; absence is divergence |
| `forbidden_markers` | markers a conforming implementation must not contain; presence is divergence |

Markers match case-insensitively, as identifier/call tokens or as body
substrings (so `pendingOwner` and `address(0)` both work). Add a reference by
dropping a `<vendor>/<pattern>.json` file here; it is discovered automatically.
The shipped references are illustrative and written from scratch for
documentation.
