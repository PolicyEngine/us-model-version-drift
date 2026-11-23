"""The figures the README quotes recompute from the committed results.

Each test computes figures from ``results/`` and requires the README to quote
them as written. When a new measurement changes a figure, a test here fails
until the README changes with it. Figures the README takes from the releases'
source, such as Medicare spending per enrollee, are not results and are not
checked here.
"""

import json
import math
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


@pytest.mark.parametrize(
    "figure",
    ("16 of the 19", "15 of 20", "33 to 47 minutes", "Nothing here attributes a row's movement to a particular change."),
)
def test_superseded_figures_are_gone(figure):
    assert figure not in README


SCORED = RESULTS / "critical-targets"


def scored(name: str) -> dict:
    return json.loads((SCORED / name).read_text())


def test_scoring_run_and_counts():
    record = scored("provenance.json")
    quoted(f"Scored on {record['started'][:10]}: [workflow run {record['workflow_run']}]")
    result = scored("critical_targets.json")
    exact, table = result["exact"]["tally"], result["table_1_4"]["tally"]
    assert exact["rows"] == exact["baseline_within"] == exact["tested_within"]
    assert table["rows"] == table["baseline_within"] == table["tested_within"]
    tolerances = {row["tolerance"] for row in result["table_1_4"]["rows"]}
    assert len(tolerances) == 1
    quoted(
        f"Both releases keep all {exact['rows']} scored target rows of Microcosm's "
        f"{len(result['exact_requirement_ids'])} exact critical requirements within tolerance",
        f"Both also keep within ±{tolerances.pop() * 100:.0f}% all {table['rows']} national dollar rows of SOI Table 1.4",
    )


def closest(rows: list[dict], side: str) -> dict:
    return min(rows, key=lambda row: row["tolerance"] - abs(row[f"{side}_error"]))


def test_rows_closest_to_their_tolerance():
    result = scored("critical_targets.json")
    rows = result["exact"]["rows"]
    tested, baseline = closest(rows, "tested"), closest(rows, "baseline")
    assert f"target:{tested['label']}" == result["exact"]["tally"]["smallest_tested_margin"]["metric_id"]
    assert tested["label"].endswith("historic_table_2.us.all.income_tax_liability_amount@2024")
    assert baseline["requirement_id"] == "social_security_benefits"
    margin = tested["tolerance"] - abs(tested["tested_error"])
    quoted(
        f"Under 2.144.4 the row closest to its tolerance is federal income tax liability against SOI historic table 2: "
        f"{pct(tested['tested_error'])} against ±{tested['tolerance'] * 100:.0f}%, {margin * 100:.1f} points inside it. "
        f"Under 2.2.2 that row's error is {pct(tested['baseline_error'])}, and the row closest to its tolerance is "
        f"Social Security benefits, at {pct(baseline['baseline_error'])} against ±{baseline['tolerance'] * 100:.0f}%."
    )


def test_table_1_4_movement():
    table = scored("critical_targets.json")["table_1_4"]
    moved = [row for row in table["rows"] if not math.isclose(row["baseline"], row["tested"], rel_tol=1e-9)]
    assert len(moved) == table["tally"]["rows"] - table["tally"]["same_under_both"] == 1
    (row,) = moved
    assert row["label"].endswith("taxable_social_security_amount@2024")
    quoted(
        f"{table['tally']['same_under_both']} of the {table['tally']['rows']} Table 1.4 rows have the same estimate "
        "under both releases, to nine significant figures",
        f"Only taxable Social Security moves, from {pct(row['baseline_error'])} to {pct(row['tested_error'])}.",
    )


def test_programme_totals():
    headline = {row["metric_id"]: row for row in scored("critical_targets.json")["headline"]}
    panel_ids = set(panel(2024))
    shared = sorted(set(headline) & panel_ids)
    (alone,) = set(headline) - panel_ids
    part_b = headline[alone]
    assert alone == "medicare_part_b_irmaa_total" and part_b["baseline"] == 0
    quoted(
        f"{len(shared)} of the scorer's {len(headline)} programme and income totals are also rows",
        f"and a test checks all {len(shared)}",
        f"It is $0 under 2.2.2 and {bn(part_b['tested'])} under 2.144.4",
    )


def test_newly_read_column_and_roles():
    result = scored("critical_targets.json")
    assert result["newly_read_columns"] == ["tax_unit_role_input"]
    roles = result["tax_unit_roles"]
    assert roles["tested"]["persons_differing"] == 0 == roles["tested"]["weighted_persons_differing"]
    agi = {row["metric_id"]: row for row in result["headline"]}["adjusted_gross_income_total"]
    assert agi["newly_read_inputs_effect"] < 0 < agi["difference"]
    quoted(
        "2.144.4 reads one stored column that 2.2.2 does not define, `tax_unit_role_input`",
        f"differ from the stored ones for {roles['baseline']['persons_differing']:,} people "
        f"({roles['baseline']['weighted_persons_differing'] / 1e6:.1f} million weighted); under 2.144.4, for none",
        f"lowers adjusted gross income under 2.144.4 by {bn(agi['newly_read_inputs_effect'], 1)}: "
        f"the rise between the releases is {bn(agi['difference'], 1)} with it and "
        f"{bn(agi['difference'] - agi['newly_read_inputs_effect'], 1)} without it",
    )
    ctc = {row["metric_id"]: row for row in result["headline"]}["ctc_total"]
    assert 0 < ctc["newly_read_inputs_effect"] < ctc["difference"]
    quoted(
        f"Reading it also accounts for {bn(ctc['newly_read_inputs_effect'])} of the {bn(ctc['difference'])} "
        "rise in the Child Tax Credit"
    )
    rows = [row for part in ("exact", "table_1_4") for row in result[part]["rows"]]
    without = {row["metric_id"]: row["without_newly_read_inputs"] for row in scored("drift.json")["rows"]}
    within = [abs(without[row["metric_id"]] / row["target"] - 1) <= row["tolerance"] for row in rows]
    assert all(within)
    quoted(f"With it withheld, 2.144.4 still keeps all {len(within)} scored rows within tolerance.")
    quoted("Nothing here attributes any other movement to a particular change.")


def test_refused_columns():
    verdict = scored("critical_targets.json")["stored_input_verdict"]
    assert not verdict["baseline"]["passed"] and not verdict["tested"]["passed"]
    both = sorted(set(verdict["baseline"]["refused"]) & set(verdict["tested"]["refused"]))
    only_tested = sorted(set(verdict["tested"]["refused"]) - set(verdict["baseline"]["refused"]))
    assert set(verdict["baseline"]["refused"]) <= set(verdict["tested"]["refused"])
    assert both == ["medicare_part_b_premiums", "would_claim_wic"]
    assert only_tested == ["first_home_mortgage_interest", "second_home_mortgage_interest"]
    quoted("`would_claim_wic` and `medicare_part_b_premiums` under both, and under 2.144.4 also the two mortgage-interest columns")


def test_scope_of_the_critical_rows():
    result = scored("critical_targets.json")
    names = [row["label"] for part in ("exact", "table_1_4") for row in result[part]["rows"]]
    names += [row["target_name"] for row in result["unscored_critical_rows"]]
    assert all(name.endswith("@2024") and name.split(".")[0] in ("irs_soi", "ssa_supplement") for name in names)
    years = {name: name.split(".")[1] for name in names}
    current = sorted(name for name, year in years.items() if year in ("ty2024", "cy2024"))
    assert len(current) == 3
    assert sum(".filing_season_" in name and "earned_income_credit" in name for name in current) == 2
    assert sum(name.startswith("ssa_supplement.") and "social_security_benefits" in name for name in current) == 1
    assert {year for name, year in years.items() if name not in current} == {"ty2022", "ty2023"}
    quoted(
        "Only three are 2024 data: Social Security benefits and the two EITC rows from SOI's filing-season "
        "statistics for tax year 2024. The other SOI rows come from tax-year 2022 and 2023 publications."
    )
    moves = sorted(
        (row for row in panel(2024).values() if row["relative_difference"] is not None),
        key=lambda row: -abs(row["relative_difference"]),
    )
    top = [row["id"] for row in moves[:5]]
    assert top == ["medicare_cost_total", "people_in_spm_poverty", "state_income_tax_total", "snap_total", "ssi_total"]
    part_d = panel(2024)["medicare_part_d_irmaa_total"]
    assert part_d["baseline"] == 0 and part_d["relative_difference"] is None
    quoted(
        "None covers Medicare, poverty, state income tax, SNAP or SSI (the five panel rows with a ratio that moved "
        f"most in 2024), Medicare's Part D surcharge (which went from $0 to {bn(part_d['tested'])} and so has no ratio), or WIC."
    )


def test_earlier_scoring_runs():
    now = {row["metric_id"]: row for row in scored("drift.json")["rows"]}
    runs = [json.loads(path.read_text()) for path in sorted((SCORED / "earlier").glob("run-*-rows.json"))]
    worst = 0.0
    for run in runs:
        for row in run["rows"]:
            for key in ("baseline", "tested", "without_newly_read_inputs"):
                a, b = now[row["metric_id"]][key], row[key]
                if a != b:
                    worst = max(worst, abs(a - b) / max(abs(a), abs(b)))
    assert 0 < worst < 1e-15
    dates = sorted(run["date"][:10] for run in runs)
    quoted(
        f"{('Two', 'Three', 'Four', 'Five')[len(runs) - 2]} earlier scoring runs, from {dates[0]} to {dates[-1]}, "
        "gave the same verdict for every row",
        f"Every estimate agrees with this run's to within {math.ceil(worst * 1e16)} parts in 10¹⁶",
    )
