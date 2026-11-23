"""The figures the README quotes recompute from the committed results.

Each test computes figures from ``results/`` and requires the README to quote
them as written. When a new measurement changes a figure, a test here fails
until the README changes with it. Figures the README takes from the releases'
source, such as Medicare spending per enrollee, are not results and are not
checked here.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
README = (ROOT / "README.md").read_text()
RUNS = ("pinned", "head")


def load(*parts: str) -> dict:
    return json.loads(RESULTS.joinpath(*parts).read_text())


def quoted(*figures: str) -> None:
    for figure in figures:
        assert figure in README, figure


def panel(period: int) -> dict[str, dict]:
    return {row["id"]: row for row in load("comparison.json")["panel"] if row["period"] == period}


def pct(value: float, places: int = 1) -> str:
    return f"{value * 100:+.{places}f}%".replace("-", "−")


def bn(value: float, places: int = 2) -> str:
    return f"${abs(value) / 1e9:,.{places}f}bn"


def test_environments():
    for run in RUNS:
        packages = load(run, "environment.json")["packages"]
        quoted(f"| `{run}` | {packages['policyengine-us']} | {packages['policyengine-core']} | {packages['spm-calculator']} |")


def test_wic_table_and_shares():
    wic = {run: {**load(run, "wic-loaded.json"), **load(run, "wic-stored.json")} for run in RUNS}
    loaded = " | ".join(bn(wic[run]["wic_as_loaded"]) for run in RUNS)
    stored = " | ".join(bn(wic[run]["wic_with_stored_draw"]) for run in RUNS)
    gaps = []
    for run in RUNS:
        gap = wic[run]["wic_as_loaded"] - wic[run]["wic_with_stored_draw"]
        gaps.append(f"{bn(gap)} ({gap / wic[run]['wic_with_stored_draw'] * 100:+.0f}%)")
    quoted(
        f"| As the release loads the dataset | {loaded} |",
        f"| With the stored draw applied | {stored} |",
        f"| Difference, relative to the total with the stored draw | {' | '.join(gaps)} |",
    )
    shares = {(f"{wic[run]['take_up_share_with_stored_draw'] * 100:.2f}%", f"{wic[run]['stored_draw_share_true_unweighted'] * 100:.2f}%") for run in RUNS}
    assert len(shares) == 1, "the README quotes one share for both releases"
    weighted, unweighted = shares.pop()
    quoted(f"true for {weighted} of people, weighted", f"true for {unweighted} of stored person rows")
    people = {wic[run]["person_ids_in_simulation"] for run in RUNS}
    assert len(people) == 1
    quoted(f"both hold the same {people.pop():,} ids")


def test_column_contract():
    contracts = {run: load(run, "contract.json") for run in RUNS}
    assert contracts["pinned"]["stored_columns"] == contracts["head"]["stored_columns"]
    quoted(f"The dataset stores {contracts['pinned']['stored_columns']} distinct columns")
    labels = {
        "input_variable": "Defined as an input",
        "computed_variable": "Defined as computed",
        "not_a_variable": "Not defined, with a model-style name",
        "raw_field": "Not defined, a raw field named outside the model's convention",
    }
    for name, label in labels.items():
        quoted(f"| {label} | {contracts['pinned']['counts'][name]} | {contracts['head']['counts'][name]} |")
    unmatched = " and ".join(str(contracts[run]["counts"]["not_a_variable"] + contracts[run]["counts"]["raw_field"]) for run in RUNS)
    quoted(f"({unmatched} here)")
    neither = set(contracts["pinned"]["not_a_variable"]) & set(contracts["head"]["not_a_variable"])
    quoted(f"Neither release defines {len(neither)} of the model-style names")


ROWS = {
    "Federal income tax": "income_tax_net",
    "Child Tax Credit": "ctc_total",
    "Earned Income Tax Credit": "eitc_total",
    "SNAP": "snap_total",
    "SSI": "ssi_total",
    "TANF": "tanf_total",
    "State income tax": "state_income_tax_total",
    "Net value of Medicare coverage (`medicare_cost`)": "medicare_cost_total",
    "Household net income": "household_net_income_total",
    "People in poverty under the model's Supplemental Poverty Measure (`person_in_poverty`)": "people_in_spm_poverty",
}


def test_panel_table():
    rows = {period: panel(period) for period in (2024, 2026)}
    assert len(rows[2024]) == 20
    quoted(f"The table shows ten of the {len(rows[2024])} rows")
    for label, metric_id in ROWS.items():
        changes = " | ".join(pct(rows[period][metric_id]["relative_difference"]) for period in (2024, 2026))
        quoted(f"| {label} | {changes} |")


# Rows that cannot move between these releases: Medicaid spending is a fixed
# state total in both, and Social Security in 2024 is the stored value.
FIXED = {2024: {"medicaid_total", "social_security_total"}, 2026: {"medicaid_total"}}


def test_stability_counts():
    for period, fixed in FIXED.items():
        rows = panel(period)
        for metric_id in fixed:
            assert abs(rows[metric_id]["relative_difference"]) < 1e-6, (period, metric_id)
    assert panel(2024)["social_security_total"]["difference"] == 0
    counts = {}
    for period, fixed in FIXED.items():
        ratios = [row["relative_difference"] for metric_id, row in panel(period).items() if metric_id not in fixed and row["relative_difference"] is not None]
        counts[period] = (sum(abs(ratio) < 0.025 for ratio in ratios), len(ratios))
    quoted(
        f"{counts[2024][0]} of the {counts[2024][1]} rows with a ratio moved less than 2.5% in 2024, "
        f"and {counts[2026][0]} of {counts[2026][1]} did in 2026"
    )
    medicaid = {period: panel(period)["medicaid_total"] for period in (2024, 2026)}
    assert {bn(row[side]) for row in medicaid.values() for side in ("baseline", "tested")} == {"$880.02bn"}
    quoted("it stays at $880.02bn in both years")
    eitc = panel(2026)["eitc_total"]["relative_difference"]
    quoted(f"shown as {pct(eitc)}, moved {eitc * 100:.2f}%")
    assert abs(eitc) >= 0.025


def test_part_d_surcharge():
    rows = {period: panel(period)["medicare_part_d_irmaa_total"] for period in (2024, 2026)}
    assert rows[2024]["baseline"] == 0 and rows[2024]["relative_difference"] is None
    assert [row["relative_difference"] for row in panel(2024).values()].count(None) == 1
    quoted(
        f"is $0 under 2.2.2 and {bn(rows[2024]['tested'])} under 2.144.4",
        f"2.2.2 gives {bn(rows[2026]['baseline'])} and 2.144.4 {bn(rows[2026]['tested'])}",
    )


def test_dollar_and_people_changes():
    rows = panel(2024)
    poverty = rows["people_in_spm_poverty"]
    quoted(
        f"federal income tax rose ${rows['income_tax_net']['difference'] / 1e9:.0f}bn",
        f"state income tax fell ${-rows['state_income_tax_total']['difference'] / 1e9:.0f}bn",
        f"fell from {poverty['baseline'] / 1e6:.1f} million to {poverty['tested'] / 1e6:.1f} million",
    )
    medicare = rows["medicare_cost_total"]
    quoted(f"it rose ${medicare['difference'] / 1e9:.0f}bn ({pct(medicare['relative_difference'])}) in 2024")


def test_run_times():
    seconds = {run: [load(run, f"panel-{period}.json")["seconds"] for period in (2024, 2026)] for run in RUNS}
    quoted(
        f"took {seconds['pinned'][0]:.0f} and {seconds['pinned'][1]:.0f} seconds on 2.2.2, "
        f"and {seconds['head'][0]:.0f} and {seconds['head'][1]:.0f} seconds on 2.144.4"
    )
    runs = [seconds]
    for path in sorted((RESULTS / "earlier").glob("*.json")):
        earlier = json.loads(path.read_text())
        if "panel_seconds" in earlier:
            runs.append({run: [earlier["panel_seconds"][run][str(period)] for period in (2024, 2026)] for run in RUNS})
    assert len(runs) == 3
    quoted(f"Across this run and the {('one', 'two', 'three')[len(runs) - 2]} earlier complete runs")
    span = {run: (min(s for r in runs for s in r[run]), max(s for r in runs for s in r[run])) for run in RUNS}
    quoted(
        f"a panel year took {span['pinned'][0]:.0f} to {span['pinned'][1]:.0f} seconds on 2.2.2 "
        f"and {span['head'][0]:.0f} to {span['head'][1]:.0f} seconds on 2.144.4"
    )
    ratios = [r["head"][i] / r["pinned"][i] for r in runs for i in range(2)]
    quoted(f"between {min(ratios):.1f} and {max(ratios):.1f} times as long")


def test_measurement_duration():
    record = load("provenance.json")
    started, completed = (datetime.fromisoformat(record[key].replace("Z", "+00:00")) for key in ("started", "completed"))
    quoted(f"The recorded run took {(completed - started).total_seconds() / 60:.0f} minutes")
    quoted(f"workflow run {record['workflow_run']}]")


def test_earlier_row_count():
    total = sum(sum(len(rows) for rows in json.loads(path.read_text())["rows"].values()) for path in (RESULTS / "earlier").glob("*.json"))
    quoted(f"{total} in all")


@pytest.mark.parametrize("figure", ("16 of the 19", "15 of 20", "33 to 47 minutes"))
def test_superseded_figures_are_gone(figure):
    assert figure not in README
