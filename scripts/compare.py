"""Compare two measured environments and write the comparison.

Usage: ``python scripts/compare.py results/pinned results/head --out results``

Writes ``comparison.json``, ``comparison.csv`` and ``comparison.md`` into
``--out`` and prints the Markdown.

It refuses two runs that are not complete and alike: a missing file, a panel
row measured in one run and not the other, a row in error, or a row whose
variable, kind or unit differs between the runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import compare_values  # noqa: E402


RUN_FILES = ("environment.json", "contract.json", "wic-loaded.json", "wic-stored.json")
WIC_VALUES = ("wic_as_loaded", "take_up_share_as_loaded", "wic_with_stored_draw", "take_up_share_with_stored_draw")
UNIT_NAMES = {"usd": "dollars", "spm_units": "SPM units", "people": "people"}


def load(directory: Path, name: str) -> dict:
    return json.loads((directory / name).read_text())


def problems(baseline: Path, tested: Path) -> list[str]:
    """Everything that makes two runs incomplete or not comparable."""
    found: list[str] = []
    for directory in (baseline, tested):
        for name in RUN_FILES:
            if not (directory / name).exists():
                found.append(f"{directory}: no {name}")
        if not list(directory.glob("panel-*.json")):
            found.append(f"{directory}: no panel-<period>.json")
    if found:
        return found
    panels = []
    for directory in (baseline, tested):
        rows = load_panel(directory)
        keys = [(row["period"], row["id"]) for row in rows]
        if len(set(keys)) != len(keys):
            found.append(f"{directory}: a panel row appears twice")
        for row in rows:
            value = row.get("value")
            if row.get("error") is not None or value is None or not math.isfinite(value):
                found.append(f"{directory}: {row['period']} {row['id']} has no value ({row.get('error')})")
        panels.append({(row["period"], row["id"]): row for row in rows})
        wic = load_wic(directory)
        for key in WIC_VALUES:
            value = wic.get(key)
            if value is None or not math.isfinite(value):
                found.append(f"{directory}: no {key}")
    for key in sorted(set(panels[0]) ^ set(panels[1])):
        found.append(f"panel row {key} is in one run only")
    for key in sorted(set(panels[0]) & set(panels[1])):
        for field in ("variable", "kind", "unit"):
            if panels[0][key].get(field) != panels[1][key].get(field):
                found.append(f"panel row {key}: the runs disagree on its {field}")
    return found


def load_panel(directory: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(directory.glob("panel-*.json")):
        rows.extend(json.loads(path.read_text())["rows"])
    if not rows:
        raise SystemExit(f"no panel-<period>.json in {directory}")
    return rows


def load_wic(directory: Path) -> dict:
    out: dict = {}
    for name in ("wic-loaded.json", "wic-stored.json"):
        path = directory / name
        if path.exists():
            out.update(json.loads(path.read_text()))
    return out


def panel_rows(baseline: list[dict], tested: list[dict]) -> list[dict]:
    index = {(r["period"], r["id"]): r for r in tested}
    rows = []
    for row in baseline:
        other = index[(row["period"], row["id"])]
        out = {
            "period": row["period"],
            "id": row["id"],
            "variable": row["variable"],
            "kind": row["kind"],
            "unit": row["unit"],
            **compare_values(row.get("value"), other.get("value")),
        }
        rows.append(out)
    return rows


def contract_diff(baseline: dict, tested: dict) -> dict:
    base_unknown = set(baseline["not_a_variable"])
    test_unknown = set(tested["not_a_variable"])
    return {
        "stored_columns": baseline["stored_columns"],
        "baseline_counts": baseline["counts"],
        "tested_counts": tested["counts"],
        "not_a_variable_in_both": sorted(base_unknown & test_unknown),
        "not_a_variable_only_in_baseline": sorted(base_unknown - test_unknown),
        "not_a_variable_only_in_tested": sorted(test_unknown - base_unknown),
        "baseline_columns_not_variables": baseline["counts"]["not_a_variable"] + baseline["counts"]["raw_field"],
        "tested_columns_not_variables": tested["counts"]["not_a_variable"] + tested["counts"]["raw_field"],
        "computed_and_stored_baseline": baseline["computed_variable"],
        "computed_and_stored_tested": tested["computed_variable"],
        "tested_required_source_inputs_missing": tested.get("required_source_inputs_missing"),
        "tested_rejected_inputs_stored": tested.get("rejected_inputs_stored"),
        "baseline_required_source_inputs_missing": baseline.get("required_source_inputs_missing"),
        "baseline_rejected_inputs_stored": baseline.get("rejected_inputs_stored"),
    }


def amount(value: float | None, unit: str) -> str:
    """Dollars in billions, counts in millions."""
    if value is None:
        return "n/a"
    sign = "−" if value < 0 else ""
    if unit == "usd":
        return f"{sign}${abs(value) / 1e9:,.2f}bn"
    return f"{sign}{abs(value) / 1e6:,.2f}m"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.2f}%"


def wic_gaps(wic: dict) -> dict:
    """WIC as loaded against WIC with the stored draw applied, per side."""
    return {
        side: compare_values(values.get("wic_with_stored_draw"), values.get("wic_as_loaded"))
        for side, values in wic.items()
    }


def names(columns: list[str]) -> str:
    return ", ".join(f"`{c}`" for c in columns) or "none"


def markdown(base_env: dict, test_env: dict, rows: list[dict], contract: dict, wic: dict, gaps: dict) -> str:
    def versions(env: dict) -> str:
        p = env["packages"]
        return (
            f"policyengine-us {p['policyengine-us']}, policyengine-core {p['policyengine-core']}, "
            f"spm-calculator {p['spm-calculator']}"
        )

    lines = [
        "# Comparison",
        "",
        f"- Baseline (`{base_env['label']}`): {versions(base_env)}",
        f"- Tested (`{test_env['label']}`): {versions(test_env)}",
        f"- Dataset: `{base_env['dataset']['file']}` at `{base_env['dataset']['revision']}`, "
        f"sha256 `{base_env['dataset']['sha256'][:12]}…`, the same bytes in both runs",
        "",
        "## Column contract",
        "",
        f"The dataset stores {contract['stored_columns']} distinct columns across six tables.",
        "",
        "| Class | Baseline | Tested |",
        "|---|---|---|",
    ]
    for name in ("input_variable", "computed_variable", "not_a_variable", "raw_field"):
        lines.append(f"| {name} | {contract['baseline_counts'][name]} | {contract['tested_counts'][name]} |")
    lines += [
        "",
        "The classes describe how each release defines a stored column's name. They do not show what the "
        "loader does with the column: policyengine-core can load stored values for a variable that has a formula.",
        "",
        f"Model-named columns only the tested release does not define ({len(contract['not_a_variable_only_in_tested'])}): "
        + (", ".join(f"`{c}`" for c in contract["not_a_variable_only_in_tested"]) or "none"),
        "",
        f"Model-named columns only the baseline does not define ({len(contract['not_a_variable_only_in_baseline'])}): "
        + (", ".join(f"`{c}`" for c in contract["not_a_variable_only_in_baseline"]) or "none"),
        "",
        f"Model-named columns neither defines ({len(contract['not_a_variable_in_both'])}): "
        + (", ".join(f"`{c}`" for c in contract["not_a_variable_in_both"]) or "none"),
        "",
        "Stored columns that are not variables of the release, raw fields included: "
        f"{contract['baseline_columns_not_variables']} (baseline), {contract['tested_columns_not_variables']} (tested).",
        "",
        "Stored columns whose variable the release defines as computed (policyengine-core's "
        "`is_input_variable()` is false for it):",
        "",
        f"- Baseline ({len(contract['computed_and_stored_baseline'])}): {names(contract['computed_and_stored_baseline'])}",
        f"- Tested ({len(contract['computed_and_stored_tested'])}): {names(contract['computed_and_stored_tested'])}",
        "",
    ]
    for label, key in (("Tested", "tested"), ("Baseline", "baseline")):
        missing = contract[f"{key}_required_source_inputs_missing"]
        rejected = contract[f"{key}_rejected_inputs_stored"]
        lines.append(
            f"{label} release, the two lists in `policyengine_us.spm`, checked by column name: "
            f"`DATASET_SOURCE_INPUTS` names missing from the data: "
            f"{'not declared in this release' if missing is None else (', '.join(missing) or 'none')}; "
            f"`REJECTED_DATASET_INPUTS` names the data stores: "
            f"{'not declared in this release' if rejected is None else (', '.join(rejected) or 'none')}."
        )
        lines.append("")
    lines += ["## WIC take-up", ""]
    lines += [
        "| | Baseline | Tested |",
        "|---|---|---|",
    ]
    for label, key, kind in (
        ("`would_claim_wic` is a variable", "would_claim_wic_is_a_variable", "flag"),
        ("WIC, 2024, as the release loads the data", "wic_as_loaded", "sum"),
        ("WIC, 2024, with the stored draw applied", "wic_with_stored_draw", "sum"),
        ("Take-up input true, as loaded: share of all people, person-weighted, January 2024", "take_up_share_as_loaded", "share"),
        (
            "Take-up input true, stored draw applied: share of all people, person-weighted, January 2024",
            "take_up_share_with_stored_draw",
            "share",
        ),
        ("Stored draw true: share of stored person rows, unweighted", "stored_draw_share_true_unweighted", "share"),
        ("People in the simulation", "person_ids_in_simulation", "count"),
        ("Stored person rows", "stored_draw_rows", "count"),
    ):
        cells = []
        for side in ("baseline", "tested"):
            value = wic[side].get(key)
            if value is None:
                cells.append("n/a")
            elif kind == "flag":
                cells.append("yes" if value else "no")
            elif kind == "share":
                cells.append(f"{value * 100:.2f}%")
            elif kind == "count":
                cells.append(f"{value:,}")
            else:
                cells.append(amount(value, "usd"))
        lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
    lines.append(
        "| As loaded minus stored draw | "
        + " | ".join(amount(gaps[side]["difference"], "usd") for side in ("baseline", "tested"))
        + " |"
    )
    lines.append(
        "| As loaded, relative to stored draw | "
        + " | ".join(percent(gaps[side]["relative_difference"]) for side in ("baseline", "tested"))
        + " |"
    )
    lines += [
        "",
        "The stored draw is matched to the simulation's people on `person_id`. The measurement stops unless "
        "each side's ids are unique and the two sides hold the same ids.",
        "",
    ]
    for period in sorted({r["period"] for r in rows}):
        lines += [
            f"## Panel, {period}",
            "",
            "| Row | Variable | Counts | Baseline | Tested | Difference | Relative |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            if r["period"] != period:
                continue
            lines.append(
                f"| {r['id']} | `{r['variable']}` | {UNIT_NAMES[r['unit']]} | {amount(r['baseline'], r['unit'])} | "
                f"{amount(r['tested'], r['unit'])} | {amount(r['difference'], r['unit'])} | "
                f"{percent(r['relative_difference'])} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("tested", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    found = problems(args.baseline, args.tested)
    if found:
        raise SystemExit("the two runs are not complete and alike:\n  " + "\n  ".join(found))
    base_env, test_env = load(args.baseline, "environment.json"), load(args.tested, "environment.json")
    if base_env["dataset"]["sha256"] != test_env["dataset"]["sha256"]:
        raise SystemExit("the two runs measured different dataset bytes")
    rows = panel_rows(load_panel(args.baseline), load_panel(args.tested))
    contract = contract_diff(load(args.baseline, "contract.json"), load(args.tested, "contract.json"))
    wic = {"baseline": load_wic(args.baseline), "tested": load_wic(args.tested)}
    gaps = wic_gaps(wic)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.json").write_text(
        json.dumps(
            {
                "baseline": base_env,
                "tested": test_env,
                "panel": rows,
                "contract": contract,
                "wic": wic,
                "wic_as_loaded_against_stored_draw": gaps,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with (args.out / "comparison.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    text = markdown(base_env, test_env, rows, contract, wic, gaps)
    (args.out / "comparison.md").write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
