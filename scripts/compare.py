"""Compare two measured environments and write the comparison.

Usage: ``python scripts/compare.py results/pinned results/head --out results``

Writes ``comparison.json``, ``comparison.csv`` and ``comparison.md`` into
``--out`` and prints the Markdown.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import compare_values  # noqa: E402


def load(directory: Path, name: str) -> dict:
    return json.loads((directory / name).read_text())


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
        other = index.get((row["period"], row["id"]), {})
        out = {
            "period": row["period"],
            "id": row["id"],
            "variable": row["variable"],
            "kind": row["kind"],
            **compare_values(row.get("value"), other.get("value")),
            "baseline_error": row.get("error"),
            "tested_error": other.get("error"),
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
        "computed_and_stored_baseline": baseline["computed_variable"],
        "computed_and_stored_tested": tested["computed_variable"],
        "tested_required_source_inputs_missing": tested.get("required_source_inputs_missing"),
        "tested_rejected_inputs_stored": tested.get("rejected_inputs_stored"),
        "baseline_required_source_inputs_missing": baseline.get("required_source_inputs_missing"),
        "baseline_rejected_inputs_stored": baseline.get("rejected_inputs_stored"),
    }


def money(value: float | None, kind: str) -> str:
    if value is None:
        return "n/a"
    if kind == "sum" and abs(value) >= 1e8:
        return f"{value / 1e9:,.2f}bn"
    return f"{value:,.0f}"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.2f}%"


def markdown(base_env: dict, test_env: dict, rows: list[dict], contract: dict, wic: dict) -> str:
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
        f"Model-named columns only the tested release does not define ({len(contract['not_a_variable_only_in_tested'])}): "
        + (", ".join(f"`{c}`" for c in contract["not_a_variable_only_in_tested"]) or "none"),
        "",
        f"Model-named columns only the baseline does not define ({len(contract['not_a_variable_only_in_baseline'])}): "
        + (", ".join(f"`{c}`" for c in contract["not_a_variable_only_in_baseline"]) or "none"),
        "",
        f"Model-named columns neither defines ({len(contract['not_a_variable_in_both'])}): "
        + (", ".join(f"`{c}`" for c in contract["not_a_variable_in_both"]) or "none"),
        "",
    ]
    for label, key in (("Tested", "tested"), ("Baseline", "baseline")):
        missing = contract[f"{key}_required_source_inputs_missing"]
        rejected = contract[f"{key}_rejected_inputs_stored"]
        lines.append(
            f"{label} release's own declarations: required source inputs missing from the data: "
            f"{'not declared in this release' if missing is None else (', '.join(missing) or 'none')}; "
            f"stored columns it says a dataset must not store: "
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
        ("Take-up input share true, as loaded (January 2024, weighted)", "take_up_share_as_loaded", "share"),
        ("WIC, 2024, with the stored draw applied", "wic_with_stored_draw", "sum"),
        ("Take-up input share true, stored draw applied", "take_up_share_with_stored_draw", "share"),
    ):
        cells = []
        for side in ("baseline", "tested"):
            value = wic[side].get(key)
            if value is None:
                cells.append("n/a")
            elif kind == "flag":
                cells.append("yes" if value else "no")
            elif kind == "share":
                cells.append(f"{value * 100:.1f}%")
            else:
                cells.append(money(value, "sum"))
        lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
    lines.append("")
    for period in sorted({r["period"] for r in rows}):
        lines += [
            f"## Panel, {period}",
            "",
            "| Row | Variable | Baseline | Tested | Difference | Relative |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            if r["period"] != period:
                continue
            note = ""
            if r["baseline_error"] or r["tested_error"]:
                note = f" ({r['baseline_error'] or 'ok'} / {r['tested_error'] or 'ok'})"
            lines.append(
                f"| {r['id']} | `{r['variable']}` | {money(r['baseline'], r['kind'])} | {money(r['tested'], r['kind'])} | "
                f"{money(r['difference'], r['kind'])} | {percent(r['relative_difference'])}{note} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("tested", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    base_env, test_env = load(args.baseline, "environment.json"), load(args.tested, "environment.json")
    if base_env["dataset"]["sha256"] != test_env["dataset"]["sha256"]:
        raise SystemExit("the two runs measured different dataset bytes")
    rows = panel_rows(load_panel(args.baseline), load_panel(args.tested))
    contract = contract_diff(load(args.baseline, "contract.json"), load(args.tested, "contract.json"))
    wic = {"baseline": load_wic(args.baseline), "tested": load_wic(args.tested)}

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.json").write_text(
        json.dumps(
            {"baseline": base_env, "tested": test_env, "panel": rows, "contract": contract, "wic": wic},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with (args.out / "comparison.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    text = markdown(base_env, test_env, rows, contract, wic)
    (args.out / "comparison.md").write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
