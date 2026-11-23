"""Combine Microcosm score documents into a table of critical-target fit.

Microcosm's scorer writes one score document for each engine. Microcosm's own
``combine_drift`` joins them with the target rows of the calibration
diagnostics and marks each critical row inside or outside its publication
tolerance. This script calls it and writes the result as JSON, CSV and
Markdown.

The baseline here is the release the ``policyengine`` bundle pins. Microcosm's
function calls its baseline "the parent's built-with engine" and checks that
the baseline scores ran it; this script passes the baseline run's own
versions for that check, which is the only use the function makes of them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_scoring import stamp  # noqa: E402
from rules import relative_difference  # noqa: E402

TABLE_1_4 = "soi_table_1_4_national_dollar_rows"


def versions(scores: dict) -> dict[str, str]:
    return {name: package["version"] for name, package in scores["runtime"]["packages"].items()}


def newly_read_columns(tested: dict) -> list[str]:
    """Stored columns the tested engine reads that no engine read before."""
    return sorted(item["column"] for item in tested["engine"]["column_changes"]["read"])


def source(name: str) -> str:
    """The publication a target row comes from: its first three name parts.

    ``target:irs_soi.ty2022.historic_table_2.us.all.ctc_amount@2024`` comes
    from ``irs_soi ty2022 historic_table_2``.
    """
    bare = name.removeprefix("target:").split("@", 1)[0]
    return " ".join(bare.split(".")[:3])


def requirement_rows(drift: dict) -> list[dict]:
    """One row for each scored target that belongs to a critical requirement."""
    rows = []
    for row in drift["rows"]:
        if not row.get("requirement_id"):
            continue
        error = row.get("target_relative_error") or {}
        within = row.get("within_tolerance") or {}
        rows.append(
            {
                "requirement_id": row["requirement_id"],
                "source": source(row["metric_id"]),
                "metric_id": row["metric_id"],
                "label": row["label"],
                "unit": row["unit"],
                "target": row.get("target"),
                "build_estimate": row.get("build_estimate"),
                "build_error": relative_difference(row.get("target"), row.get("build_estimate")),
                "baseline": row["baseline"],
                "tested": row["tested"],
                "baseline_error": error.get("baseline"),
                "tested_error": error.get("tested"),
                "tolerance": row.get("tolerance"),
                "baseline_within": within.get("baseline"),
                "tested_within": within.get("tested"),
                "newly_read_inputs_effect": row.get("newly_read_inputs_effect"),
                "other_engine_changes_effect": row.get("other_engine_changes_effect"),
            }
        )
    return rows


def headline_rows(drift: dict) -> list[dict]:
    """The scorer's programme totals, which belong to no requirement."""
    return [
        {
            key: row.get(key)
            for key in (
                "metric_id",
                "label",
                "unit",
                "baseline",
                "tested",
                "difference",
                "relative_difference",
                "newly_read_inputs_effect",
            )
        }
        for row in drift["rows"]
        if not row.get("requirement_id")
    ]


def tally(rows: list[dict]) -> dict:
    """How many rows each engine holds within tolerance, and which it does not."""
    judged = [row for row in rows if row["tolerance"] is not None]
    out = {"rows": len(rows), "rows_with_a_tolerance": len(judged)}
    for side in ("baseline", "tested"):
        outside = sorted(row["metric_id"] for row in judged if row[f"{side}_within"] is False)
        out[f"{side}_within"] = sum(1 for row in judged if row[f"{side}_within"] is True)
        out[f"{side}_outside"] = outside
    out["leaving_tolerance"] = sorted(
        row["metric_id"] for row in judged if row["baseline_within"] is True and row["tested_within"] is False
    )
    out["entering_tolerance"] = sorted(
        row["metric_id"] for row in judged if row["baseline_within"] is False and row["tested_within"] is True
    )
    out["same_under_both"] = sum(
        1
        for row in rows
        if row["baseline"] is not None
        and row["tested"] is not None
        and math.isclose(row["baseline"], row["tested"], rel_tol=1e-9, abs_tol=0.0)
    )
    margins = [
        (row["tolerance"] - abs(row["tested_error"]), row["metric_id"])
        for row in judged
        if row["tested_error"] is not None
    ]
    out["smallest_tested_margin"] = None if not margins else {"metric_id": min(margins)[1], "margin": min(margins)[0]}
    return out


def amount(value, unit: str) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    if unit == "usd":
        return f"{sign}${abs(value) / 1e9:,.1f}bn"
    return f"{sign}{abs(value) / 1e6:,.2f}m"


def percent(value) -> str:
    return "n/a" if value is None else f"{value * 100:+.1f}%"


def verdict(value) -> str:
    return {True: "in", False: "OUT", None: "n/a"}[value]


def names(columns) -> str:
    return ", ".join(f"`{c}`" for c in columns) or "none"


def side_text(result: dict, side: str) -> str:
    versions = result[side]["versions"]
    return (
        f"policyengine-us {versions['policyengine-us']}, policyengine-core {versions['policyengine-core']}, "
        f"spm-calculator {versions['spm-calculator']}"
    )


def markdown(result: dict) -> str:
    exact, table = result["exact"], result["table_1_4"]
    built = result["inputs"]["estimates_from"]
    requirements = len(result["exact_requirement_ids"])
    lines = [
        "# Critical targets",
        "",
        f"- Baseline: {side_text(result, 'baseline')}",
        f"- Tested: {side_text(result, 'tested')}",
        f"- Dataset sha256 `{result['dataset_sha256'][:12]}…`, {result['households']:,} households, period {result['period']}",
        f"- Targets and tolerances: the dataset's published calibration diagnostics and Microcosm's "
        f"critical-target requirements at commit `{result['microcosm_commit'][:12]}`",
        f"- Build estimates: Microcosm build `{built['build_id']}`, made with policyengine-us "
        f"{built['policyengine-us']} and policyengine-core {built['policyengine-core']}. The dataset carries "
        "that build's calibration diagnostics unchanged.",
        f"- Stored columns the tested engine newly reads: {names(result['newly_read_columns'])}",
        "",
        f"## The {requirements} exact requirements",
        "",
        f"{exact['tally']['rows_with_a_tolerance']} scored target rows serve the {requirements} requirements: "
        "a requirement can name more than one publication. Within tolerance: "
        f"{exact['tally']['baseline_within']} under the baseline, {exact['tally']['tested_within']} under the tested release.",
        "",
        "| Requirement | Source | Target | Build estimate | Baseline | Tested | Tolerance | Baseline | Tested |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in exact["rows"]:
        if row["tolerance"] is None:
            lines.append(
                f"| {row['requirement_id']} | `{row['source']}` | {amount(row['target'], row['unit'])} | n/a | "
                f"{amount(row['baseline'], row['unit'])} | {amount(row['tested'], row['unit'])} | n/a | n/a | n/a |"
            )
            continue
        lines.append(
            f"| {row['requirement_id']} | `{row['source']}` | {amount(row['target'], row['unit'])} | "
            f"{amount(row['build_estimate'], row['unit'])} ({percent(row['build_error'])}) | "
            f"{amount(row['baseline'], row['unit'])} ({percent(row['baseline_error'])}) | "
            f"{amount(row['tested'], row['unit'])} ({percent(row['tested_error'])}) | "
            f"±{row['tolerance'] * 100:.0f}% | {verdict(row['baseline_within'])} | {verdict(row['tested_within'])} |"
        )
    margin = exact["tally"]["smallest_tested_margin"]
    lines += [
        "",
        "Each estimate's error against the target follows it in brackets.",
        "",
    ]
    if margin is not None:
        closest = next(row for row in exact["rows"] if row["metric_id"] == margin["metric_id"])
        lines += [
            f"Smallest margin under the tested release: {closest['requirement_id']} (`{closest['source']}`), "
            f"{margin['margin'] * 100:.1f} percentage points inside its tolerance.",
            "",
        ]
    unscored = result["unscored_critical_rows"]
    lines += [
        f"Requirements with no scored row: {', '.join(result['unscored_requirements']) or 'none'}.",
        "",
        f"Critical target rows the scorer did not score ({len(unscored)}): "
        + (", ".join(f"{row['requirement_id']} (`{row['target_name']}`)" for row in unscored) or "none")
        + ".",
        "",
        "## SOI Table 1.4 national dollar rows",
        "",
        f"{table['tally']['rows_with_a_tolerance']} scored rows, tolerance ±25%. Within tolerance: "
        f"{table['tally']['baseline_within']} under the baseline, {table['tally']['tested_within']} under the tested release. "
        f"{table['tally']['same_under_both']} of the {table['tally']['rows']} rows have the same estimate under both releases, "
        "to nine significant figures.",
        "",
        "| Row | Target | Baseline | Tested | Baseline | Tested |",
        "|---|---|---|---|---|---|",
    ]
    for row in table["rows"]:
        lines.append(
            f"| {row['label'].split('.all.', 1)[-1].split('@', 1)[0]} | {amount(row['target'], row['unit'])} | "
            f"{amount(row['baseline'], row['unit'])} ({percent(row['baseline_error'])}) | "
            f"{amount(row['tested'], row['unit'])} ({percent(row['tested_error'])}) | "
            f"{verdict(row['baseline_within'])} | {verdict(row['tested_within'])} |"
        )
    lines += ["", "## What each engine does with the stored columns", ""]
    for side in ("baseline", "tested"):
        verdict_ = result["stored_input_verdict"][side]
        changes = result["column_changes"][side]
        lines.append(
            f"- {side.capitalize()}: Microcosm's stored-input check "
            f"{'passed' if verdict_['passed'] else 'failed'}; columns it refused: {names(verdict_['refused'])}. "
            f"Stored columns this engine ignores: {names(item['column'] for item in changes['ignored'])}."
        )
    roles = result["tax_unit_roles"]
    if roles:
        lines += ["", "People whose tax-unit role in the engine differs from the stored role:", ""]
        for side in ("baseline", "tested"):
            if side in roles:
                item = roles[side]
                lines.append(
                    f"- {side.capitalize()}: {item['persons_differing']:,} of {item['persons']:,} people "
                    f"({item['weighted_persons_differing'] / 1e6:,.1f}m weighted), in {item['tax_units_differing']:,} tax units "
                    f"({item['weighted_tax_units_differing'] / 1e6:,.1f}m weighted)"
                )
    lines += [
        "",
        "## Programme totals the scorer also reports",
        "",
        "The last column is the part of the change that comes from the stored columns the tested engine newly reads.",
        "",
        "| Row | Baseline | Tested | Relative | From newly read columns |",
        "|---|---|---|---|---|",
    ]
    for row in result["headline"]:
        lines.append(
            f"| {row['label']} | {amount(row['baseline'], row['unit'])} | {amount(row['tested'], row['unit'])} | "
            f"{percent(row['relative_difference'])} | {amount(row['newly_read_inputs_effect'], row['unit'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_result(drift: dict, summary: dict, inputs: dict, exact_ids: list[str]) -> dict:
    rows = requirement_rows(drift)
    exact_rows = [row for row in rows if row["requirement_id"] != TABLE_1_4]
    table_rows = [row for row in rows if row["requirement_id"] == TABLE_1_4]
    order = {name: index for index, name in enumerate(exact_ids)}
    exact_rows.sort(key=lambda row: (order.get(row["requirement_id"], len(order)), row["metric_id"]))
    scores = drift["scores"]
    return {
        "baseline": {"versions": versions(scores["baseline"])},
        "tested": {"versions": versions(scores["tested"])},
        "dataset_sha256": drift["dataset_sha256"],
        "households": scores["baseline"]["scoring"]["n_households"],
        "period": scores["baseline"]["scoring"]["period"],
        "spm": scores["baseline"]["scoring"]["spm"],
        "microcosm_commit": scores["baseline"]["code"]["git_commit"],
        "newly_read_columns": drift["newly_read_columns"],
        "stored_input_verdict": {side: scores[side]["engine"]["stored_input_verdict"] for side in ("baseline", "tested")},
        "column_changes": {side: scores[side]["engine"]["column_changes"] for side in ("baseline", "tested")},
        "tax_unit_roles": drift.get("tax_unit_roles"),
        "unscored_critical_rows": drift["unscored_critical_rows"],
        "exact_requirement_ids": list(exact_ids),
        "unscored_requirements": sorted(set(exact_ids) - {row["requirement_id"] for row in exact_rows}),
        "exact": {"rows": exact_rows, "tally": tally(exact_rows)},
        "table_1_4": {"rows": table_rows, "tally": tally(table_rows)},
        "headline": headline_rows(drift),
        "microcosm_summary": summary,
        "inputs": inputs,
    }


def write_outputs(out: Path, drift: dict, result: dict) -> str:
    out.mkdir(parents=True, exist_ok=True)
    (out / "drift.json").write_text(json.dumps(drift, indent=2, sort_keys=True) + "\n")
    (out / "critical_targets.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    rows = result["exact"]["rows"] + result["table_1_4"]["rows"]
    with (out / "critical_targets.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    text = markdown(result)
    (out / "critical_targets.md").write_text(text + "\n")
    return text


def render(directory: Path, out: Path) -> str:
    """Rebuild the tables from a committed ``drift.json`` without Microcosm.

    ``drift.json`` holds Microcosm's output; the rest is a pure function of it
    and of three values ``critical_targets.json`` records.
    """
    drift = json.loads((directory / "drift.json").read_text())
    previous = json.loads((directory / "critical_targets.json").read_text())
    exact_ids = previous.get("exact_requirement_ids") or list(
        dict.fromkeys(row["requirement_id"] for row in previous["exact"]["rows"])
    ) + previous["unscored_requirements"]
    result = build_result(drift, previous["microcosm_summary"], previous["inputs"], exact_ids)
    return write_outputs(out, drift, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", type=Path, help="rebuild the tables from the drift.json in this folder")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--tested", type=Path)
    parser.add_argument("--counterfactual", type=Path, help="the tested engine without its newly read columns")
    parser.add_argument("--diagnostics", type=Path, help="the derived calibration_diagnostics.json")
    parser.add_argument("--inputs", type=Path, help="scoring_inputs.json from a scoring job")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.render is not None:
        print(render(args.render, args.out))
        return 0
    missing = [name for name in ("baseline", "tested", "diagnostics", "inputs") if getattr(args, name) is None]
    if missing:
        parser.error(f"scoring needs --{', --'.join(missing)}")

    from microcosm.data import compatibility_recertification as recert
    from microcosm.data.us_critical_targets import US_EXACT_CRITICAL_TARGET_FIT_REQUIREMENTS

    baseline = json.loads(args.baseline.read_text())
    tested = json.loads(args.tested.read_text())
    inputs = json.loads(args.inputs.read_text())
    diagnostics = json.loads(args.diagnostics.read_text())
    diagnostics_sha256 = hashlib.sha256(args.diagnostics.read_bytes()).hexdigest()
    if diagnostics_sha256 != inputs["derived_diagnostics"]["sha256"]:
        raise SystemExit("the derived diagnostics here differ from the ones the scoring jobs read")
    newly_read = newly_read_columns(tested)
    counterfactual = None
    if newly_read:
        if args.counterfactual is None or not args.counterfactual.exists():
            raise SystemExit(f"the tested engine newly reads {newly_read}; pass its counterfactual scores")
        counterfactual = json.loads(args.counterfactual.read_text())
    base_versions = versions(baseline)
    drift = recert.combine_drift(
        calibration_diagnostics=diagnostics,
        dataset_sha256=inputs["dataset"]["sha256"],
        baseline=baseline,
        tested=tested,
        counterfactual=counterfactual,
        baseline_engine={
            "model": {"version": base_versions["policyengine-us"]},
            "core": {"version": base_versions["policyengine-core"]},
        },
        tested_packages=tested["runtime"]["packages"],
        newly_read_columns=newly_read,
        diagnostics_sha256=diagnostics_sha256,
        expected_households=inputs["dataset"]["households"],
    )
    exact_ids = [item.requirement_id for item in US_EXACT_CRITICAL_TARGET_FIT_REQUIREMENTS]
    result = build_result(drift, recert.drift_summary(drift), inputs, exact_ids)
    print(write_outputs(args.out, drift, result))
    # The combining job's own stamp, beside the three scoring jobs' stamps.
    (args.out / "combine.json").write_text(json.dumps(stamp(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
