"""Output formatters for scan findings: JSON, SARIF 2.1.0, Markdown.

All formatters are pure functions of a ``ScanReport`` and produce deterministic
text (stable key order, no timestamps), so two runs over the same input yield
identical bytes.
"""
from __future__ import annotations

import json

from openreagent.scan import ScanReport

_TIER_TO_SARIF_LEVEL = {"HIGH": "error", "MEDIUM": "warning", "LOW": "note"}


def to_json(report: ScanReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def to_sarif(report: ScanReport) -> str:
    rule_ids = sorted({f.recipe for f in report.findings} | set(report.enabled_recipes))
    rules = [
        {
            "id": rid,
            "name": rid,
            "shortDescription": {"text": f"OpenReagent recipe '{rid}'"},
        }
        for rid in rule_ids
    ]
    results = []
    for f in report.findings:
        results.append(
            {
                "ruleId": f.recipe,
                "level": _TIER_TO_SARIF_LEVEL.get(f.tier, "note"),
                "message": {"text": f.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.file},
                            "region": {"startLine": max(f.line, 1)},
                        }
                    }
                ],
                "properties": {
                    "score": f.score,
                    "signature_id": f.signature_id,
                    "recipe_version": f.recipe_version,
                    "function": f.function,
                    **f.details,
                },
            }
        )
    doc = {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "OpenReagent",
                        "informationUri": "https://github.com/openreagent/openreagent",
                        "version": "0.1.0",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(doc, indent=2, sort_keys=True)


def to_markdown(report: ScanReport) -> str:
    lines: list[str] = []
    lines.append("# OpenReagent scan findings")
    lines.append("")
    lines.append(
        f"Scanned {report.files_scanned} file(s) against a pool of "
        f"{report.pool_size} signature(s) using "
        f"{len(report.enabled_recipes)} enabled recipe(s)."
    )
    lines.append("")
    if not report.findings:
        lines.append("No findings.")
        lines.append("")
        return "\n".join(lines)
    lines.append("| Tier | Recipe | File | Line | Function | Signature | Detail |")
    lines.append("|------|--------|------|------|----------|-----------|--------|")
    for f in report.findings:
        detail = f.message.replace("|", "\\|")
        lines.append(
            f"| {f.tier} | {f.recipe} | {f.file} | {f.line} | "
            f"{f.function} | {f.signature_id} | {detail} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_report(report: ScanReport, fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "json":
        return to_json(report)
    if fmt == "sarif":
        return to_sarif(report)
    if fmt in ("md", "markdown"):
        return to_markdown(report)
    raise ValueError(f"unknown format: {fmt}")
