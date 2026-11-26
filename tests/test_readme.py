"""The figures the README quotes recompute from the committed results.

Each test computes figures from ``results/`` and requires the README to quote
them as written. When a new measurement changes a figure, a test here fails
until the README changes with it. Figures the README takes from the releases'
source, such as Medicare spending per enrollee, are not results and are not
checked here.
"""

import json
import math
import re
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


def release(run: str) -> str:
    return load(run, "environment.json")["packages"]["policyengine-us"]


PINNED, HEAD = release("pinned"), release("head")

# The Measure run recorded before this one, kept in results/earlier/. Its note
# names the head release it measured, the core release with it and the commit
# that held its results; every earlier run held that head release
# (EARLIER_RELEASES in tests/test_results.py).
EARLIER_RUN = "run-44907751024-panel-rows.json"
EARLIER_NOTE = re.search(
    r"\(results/provenance\.json at commit (\w+)\), with policyengine-us (\S+) and policyengine-core (\S+) as head",
    json.loads((RESULTS / "earlier" / EARLIER_RUN).read_text())["note"],
)
EARLIER_COMMIT, EARLIER_HEAD, EARLIER_CORE = EARLIER_NOTE.groups()
REPOSITORY = "https://github.com/PolicyEngine/us-model-version-drift"

# The Score run recorded before this one, kept in results/critical-targets/
# earlier/. Its note names the releases it scored.
EARLIER_SCORES = "run-45207756243-rows.json"
EARLIER_SCORE_RELEASES = re.search(
    r"which scored policyengine-us (\d+\.\d+\.\d+) against (\d+\.\d+\.\d+)",
    json.loads((RESULTS / "critical-targets" / "earlier" / EARLIER_SCORES).read_text())["note"],
).groups()


def pct(value: float, places: int = 1) -> str:
    return f"{value * 100:+.{places}f}%".replace("-", "−")


def bn(value: float, places: int = 2) -> str:
    return f"${abs(value) / 1e9:,.{places}f}bn"


def test_environments():
    for run in RUNS:
        packages = load(run, "environment.json")["packages"]
        quoted(f"| `{run}` | {packages['policyengine-us']} | {packages['policyengine-core']} | {packages['spm-calculator']} |")
    # The day and version come from the requirements file that chose them.
    day, version = re.search(
        r"The newest policyengine-us on PyPI on (\S+) \((\S+), uploaded", (ROOT / "envs" / "head.txt").read_text()
    ).groups()
    assert version == HEAD
    core = load("head", "environment.json")["packages"]["policyengine-core"]
    quoted(
        f"`head` holds {HEAD}, the newest policyengine-us on PyPI on {day}, and policyengine-core {core}, the newest "
        f"core release that day and the lowest that {HEAD} accepts"
    )


def test_release_labels():
    """Every policyengine-us release the README names is one the results
    name, so a label cannot go stale after the next measurement."""
    assert set(re.findall(r"\b2\.\d+\.\d+\b", README)) == {PINNED, HEAD, EARLIER_HEAD}


def test_previous_measurement_links():
    """The README links the previous measurement's README and results at the
    commit that held them, and names the head release they measured."""
    assert EARLIER_HEAD != HEAD
    quoted(
        f"Commit `{EARLIER_COMMIT}` keeps the [README]({REPOSITORY}/blob/{EARLIER_COMMIT}/README.md) and "
        f"[results]({REPOSITORY}/tree/{EARLIER_COMMIT}/results) of the previous measurement, which had "
        f"policyengine-us {EARLIER_HEAD} as head.",
        f"### What moved between {EARLIER_HEAD} and {HEAD}",
        f"The previous measurement held policyengine-us {EARLIER_HEAD} and policyengine-core {EARLIER_CORE} as head "
        f"([README]({REPOSITORY}/blob/{EARLIER_COMMIT}/README.md) and "
        f"[results]({REPOSITORY}/tree/{EARLIER_COMMIT}/results) at commit `{EARLIER_COMMIT}`)",
    )
    scores = json.loads((RESULTS / "critical-targets" / "earlier" / EARLIER_SCORES).read_text())
    assert EARLIER_SCORE_RELEASES == (PINNED, EARLIER_HEAD)
    quoted(
        f"`results/earlier/{EARLIER_RUN}` keeps that run's panel rows, and "
        f"`results/critical-targets/earlier/{EARLIER_SCORES}` keeps the scores from Score run "
        f"{scores['workflow_run']}, which scored {EARLIER_HEAD}. Against that Measure run,"
    )
    # Head changed both packages between the two measurements.
    assert EARLIER_CORE != load("head", "environment.json")["packages"]["policyengine-core"]
    quoted("Head changed both packages, so a move can come from either.")


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
    assert all(wic[run]["take_up_share_as_loaded"] == 1 for run in RUNS)
    quoted(
        "As loaded, the take-up input defaults to true for every person.",
        f"Applying the stored draw sets the January 2024 take-up input to true for {weighted} of people, counting "
        "each at their person weight.",
        f"Unweighted, {unweighted} of stored person rows carry a true draw.",
    )
    people = {wic[run]["person_ids_in_simulation"] for run in RUNS}
    assert len(people) == 1
    quoted(f"the table and the simulation hold the same {people.pop():,} ids")
    quoted(f"| WIC, 2024 | {PINNED} | {HEAD} |")
    for run in RUNS:
        join = wic[run]["join"]
        assert join["stored_ids_unique"] and join["simulation_ids_unique"] and join["same_id_sets"], run
        assert join["same_row_order"], run
        assert join["check_column"] == "age" and join["check_column_rows_that_differ"] == 0, run
        assert wic[run]["stored_draw_missing"] == 0, run
    quoted(
        "Under both releases, no id repeats in the stored table or in the simulation",
        "and the stored table lists them in the simulation's order. Each matched person's stored `age` equals the simulation's",
    )


def test_column_contract():
    contracts = {run: load(run, "contract.json") for run in RUNS}
    assert contracts["pinned"]["stored_columns"] == contracts["head"]["stored_columns"]
    quoted(f"The dataset stores {contracts['pinned']['stored_columns']} distinct columns")
    quoted(f"| Class of stored column | {PINNED} | {HEAD} |")
    labels = {
        "input_variable": "Defined as an input",
        "computed_variable": "Defined as computed",
        "not_a_variable": "Not defined, with a model-style name",
        "raw_field": "Not defined, a raw field named outside the model's convention",
    }
    for name, label in labels.items():
        quoted(f"| {label} | {contracts['pinned']['counts'][name]} | {contracts['head']['counts'][name]} |")
    unmatched = ", ".join(
        f"{contracts[run]['counts']['not_a_variable'] + contracts[run]['counts']['raw_field']} under {release(run)}" for run in RUNS
    )
    quoted(f"({unmatched})")
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
    quoted(f"The table gives the change from `pinned` to `head` for ten of the {len(rows[2024])} rows")
    for label, metric_id in ROWS.items():
        changes = " | ".join(pct(rows[period][metric_id]["relative_difference"]) for period in (2024, 2026))
        quoted(f"| {label} | {changes} |")


# The one row that cannot move between these releases: Social Security in
# 2024 equals the stored values under both. Medicaid spending moves, because
# the head release adds a year of state spending totals.
FIXED = {2024: {"social_security_total"}, 2026: set()}


def test_stability_counts():
    # FIXED holds exactly the rows that did not move.
    unmoved = {
        period: {metric_id for metric_id, row in panel(period).items() if row["relative_difference"] is not None and abs(row["relative_difference"]) < 1e-6}
        for period in FIXED
    }
    assert unmoved == FIXED
    assert panel(2024)["social_security_total"]["difference"] == 0
    count = sum(map(len, FIXED.values()))
    quoted(f"{('One', 'Two', 'Three')[count - 1]} row{'s' if count > 1 else ''} cannot move between these releases")
    counts = {}
    for period, fixed in FIXED.items():
        ratios = [row["relative_difference"] for metric_id, row in panel(period).items() if metric_id not in fixed and row["relative_difference"] is not None]
        counts[period] = (sum(abs(ratio) < 0.025 for ratio in ratios), len(ratios))
    quoted(
        f"Leaving that row out, {counts[2024][0]} of the {counts[2024][1]} rows with a ratio "
        f"moved less than 2.5% in 2024, and {counts[2026][0]} of {counts[2026][1]} did in 2026"
    )
    # Every row the table shows as 2.5% that moved 2.5% or more, which the
    # README names so the counts do not read as wrong.
    shown_at_the_limit = sorted(
        (period, metric_id)
        for period, fixed in FIXED.items()
        for metric_id, row in panel(period).items()
        if metric_id not in fixed
        and row["relative_difference"] is not None
        and abs(row["relative_difference"]) >= 0.025
        and pct(row["relative_difference"])[1:] == "2.5%"
    )
    assert shown_at_the_limit == [(2024, "snap_total"), (2026, "eitc_total")]
    eitc, snap = panel(2026)["eitc_total"]["relative_difference"], panel(2024)["snap_total"]["relative_difference"]
    assert f"{abs(eitc) * 100:.2f}" == f"{abs(snap) * 100:.2f}"
    quoted(
        f"The Earned Income Tax Credit in 2026 (shown as {pct(eitc)}) and SNAP in 2024 (shown as {pct(snap)}) "
        f"each moved {abs(eitc) * 100:.2f}%"
    )


def test_medicaid_spending_and_enrollment():
    medicaid = {period: panel(period)["medicaid_total"] for period in (2024, 2026)}
    baseline = {bn(row["baseline"]) for row in medicaid.values()}
    tested = {bn(row["tested"]) for row in medicaid.values()}
    change = {pct(row["relative_difference"]) for row in medicaid.values()}
    assert len(baseline) == len(tested) == len(change) == 1, "the README quotes one figure for both years"
    enrollment = {period: panel(period)["medicaid_enrollment"]["relative_difference"] for period in (2024, 2026)}
    assert enrollment[2024] < 0 < enrollment[2026]
    quoted(
        f"Medicaid spending rises from {baseline.pop()} to {tested.pop()} ({change.pop()}) in both years, while "
        f"enrollment falls {-enrollment[2024] * 100:.1f}% in 2024 and rises {enrollment[2026] * 100:.1f}% in 2026."
    )


def test_part_d_surcharge():
    rows = {period: panel(period)["medicare_part_d_irmaa_total"] for period in (2024, 2026)}
    assert rows[2024]["baseline"] == 0 and rows[2024]["relative_difference"] is None
    assert [row["relative_difference"] for row in panel(2024).values()].count(None) == 1
    quoted(
        f"{PINNED} puts Medicare's income-related surcharge on Part D premiums "
        f"(`income_adjusted_part_d_premium_surcharge`) at $0 and {HEAD} at {bn(rows[2024]['tested'])}.",
        f"so {PINNED} sets every surcharge to zero",
        f"In 2026, when the surcharge reads 2024 income, {PINNED} gives {bn(rows[2026]['baseline'])} and {HEAD} "
        f"{bn(rows[2026]['tested'])}.",
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
        f"took {seconds['pinned'][0]:.0f} and {seconds['pinned'][1]:.0f} seconds on {PINNED}, "
        f"and {seconds['head'][0]:.0f} and {seconds['head'][1]:.0f} seconds on {HEAD}"
    )
    runs = [seconds]
    for path in sorted((RESULTS / "earlier").glob("*.json")):
        earlier = json.loads(path.read_text())
        if "panel_seconds" in earlier:
            runs.append({run: [earlier["panel_seconds"][run][str(period)] for period in (2024, 2026)] for run in RUNS})
    assert len(runs) == 4
    quoted(f"Across this run and the {('one', 'two', 'three')[len(runs) - 2]} earlier runs in `results/earlier/` that finished both years")
    span = {run: (min(s for r in runs for s in r[run]), max(s for r in runs for s in r[run])) for run in RUNS}
    # The head span mixes two releases, and the README says which.
    quoted(
        f"a panel year took {span['pinned'][0]:.0f} to {span['pinned'][1]:.0f} seconds on {PINNED} "
        f"and {span['head'][0]:.0f} to {span['head'][1]:.0f} seconds on the head release "
        f"({EARLIER_HEAD} in the earlier runs, {HEAD} in this one)"
    )
    ratios = [r["head"][i] / r["pinned"][i] for r in runs for i in range(2)]
    quoted(f"the head release took between {min(ratios):.1f} and {max(ratios):.1f} times as long as {PINNED}.")


def test_measurement_duration():
    record = load("provenance.json")
    started, completed = (datetime.fromisoformat(record[key].replace("Z", "+00:00")) for key in ("started", "completed"))
    quoted(f"The recorded run took {(completed - started).total_seconds() / 60:.0f} minutes")
    quoted(f"workflow run {record['workflow_run']}]")
    quoted(f"Measured on {record['started'][:10]}: [workflow run {record['workflow_run']}]({record['url']})")


def test_scoring_duration():
    record = scored("provenance.json")
    started, completed = (datetime.fromisoformat(record[key].replace("Z", "+00:00")) for key in ("started", "completed"))
    quoted(
        f"The recorded run took {(completed - started).total_seconds() / 60:.0f} minutes, from its start to the end "
        "of its last job (`results/critical-targets/provenance.json`)"
    )


def test_earlier_row_count():
    """The earlier runs measured 2.2.2 as pinned, as this run did, and another
    head release. The README counts their rows by release and claims equal
    digits only for the release both measured."""
    earlier = [json.loads(path.read_text()) for path in sorted((RESULTS / "earlier").glob("*.json"))]
    rows = {run: sum(len(each["rows"][run]) for each in earlier) for run in RUNS}
    assert EARLIER_HEAD != HEAD
    now = {(row["period"], row["id"]): row["baseline"] for row in load("comparison.json")["panel"]}
    for each in earlier:
        for row in each["rows"]["pinned"]:
            assert now[(row["period"], row["id"])] == row["value"], row
    # Only run 44907751024's note names the head release. Every other earlier
    # run's head rows equal its rows exactly, so they measured that release too.
    named = {(row["period"], row["id"]): row["value"] for row in load("earlier", EARLIER_RUN)["rows"]["head"]}
    for each in earlier:
        for row in each["rows"]["head"]:
            assert named[(row["period"], row["id"])] == row["value"], (each["workflow_run"], row)
    # The first run stopped partway into 2026; the others hold every row.
    assert max(each["workflow_run"] for each in earlier) == load("earlier", EARLIER_RUN)["workflow_run"]
    first, *rest = sorted(earlier, key=lambda each: each["workflow_run"])
    assert all(len(each["rows"][run]) == len(now) for each in rest for run in RUNS)
    assert {row["period"] for row in first["rows"]["head"]} == {2024, 2026} and len(first["rows"]["head"]) < len(now)
    quoted(
        f"{('One', 'Two', 'Three', 'Four', 'Five')[len(earlier) - 1]} earlier runs, from 2026-11-17 to 2026-11-21 and "
        f"under earlier versions of this code, measured the same panel with {EARLIER_HEAD} as head. "
        f"The first, {first['workflow_run']}, stopped partway into 2026 (see the last section).",
        f"Of the rows they measured, {sum(rows.values())} in all, the {rows['pinned']} under {PINNED} equal this "
        "run's in every digit",
        f"The other {rows['head']} rows came from {EARLIER_HEAD}, and each equals the matching row of the last of those "
        f"runs in every digit; the subsection on {EARLIER_HEAD} and {HEAD} compares that run with this one.",
        f"The earlier runs in `results/earlier/` gave exactly this run's panel rows for {PINNED}, the release both measured.",
        f"[{first['workflow_run']}]({first['url']}), held two panel years in one process",
    )


def test_moves_since_the_previous_head():
    """The head rows of the run recorded before this one, against this run's."""
    earlier = load("earlier", EARLIER_RUN)
    assert EARLIER_HEAD != HEAD
    now = {
        run: {(row["period"], row["id"]): row[side] for row in load("comparison.json")["panel"]}
        for run, side in (("pinned", "baseline"), ("head", "tested"))
    }
    before = {run: {(row["period"], row["id"]): row["value"] for row in earlier["rows"][run]} for run in RUNS}
    assert {run: set(before[run]) for run in RUNS} == {run: set(now[run]) for run in RUNS}
    assert all(before["pinned"][key] == now["pinned"][key] for key in before["pinned"])
    same = [key for key in before["head"] if before["head"][key] == now["head"][key]]
    quoted(
        f"none of the {len(before['pinned'])} pinned rows moved, and {len(same)} of the {len(before['head'])} "
        "head rows stayed the same to every digit"
    )
    change = {key: now["head"][key] / before["head"][key] - 1 for key in before["head"]}
    spending = {period: (before["head"][(period, "medicaid_total")], now["head"][(period, "medicaid_total")]) for period in (2024, 2026)}
    shown = {(f"{change[(period, 'medicaid_total')] * 100:.1f}%", bn(old), bn(new)) for period, (old, new) in spending.items()}
    assert len(shown) == 1, "the README quotes one figure for both years"
    rise, old, new = shown.pop()
    # The previous head gave the pinned release's total, so the rise from the
    # pinned release came in this step.
    assert {bn(now["pinned"][(period, "medicaid_total")]) for period in (2024, 2026)} == {old}
    quoted(
        f"Medicaid spending rose {rise} in both years, from {old} to {new}. {EARLIER_HEAD} gave the same total as "
        f"{PINNED}, so the whole rise since {PINNED} came with {HEAD}, for the reason the aggregate panel gives."
    )
    enrolled = {period: change[(period, "medicaid_enrollment")] for period in (2024, 2026)}
    assert all(value < 0 for value in enrolled.values())
    assert len({f"{-value * 100:.1f}" for value in enrolled.values()}) == 1
    quoted(
        f"{HEAD} enrolls {-enrolled[2024] * 100:.1f}% fewer people in Medicaid than {EARLIER_HEAD} did, in both years "
        f"({now['head'][(2024, 'medicaid_enrollment')]:,.0f} against {before['head'][(2024, 'medicaid_enrollment')]:,.0f} in 2024)",
        "The panel cannot split the fall among these changes, or between them and policyengine-core.",
    )
    others = {key: value for key, value in change.items() if key[1] not in ("medicaid_total", "medicaid_enrollment")}
    largest = max(others, key=lambda key: abs(others[key]))
    assert abs(others[largest]) < 0.003 and largest == (2026, "snap_total") and others[largest] < 0
    quoted("Every other head row moved less than 0.3%.", f"SNAP in 2026 fell most, by {-others[largest] * 100:.2f}%.")
    medicare = [key for key in before["head"] if key[1] in ("medicare_cost_total", "medicare_part_d_irmaa_total")]
    assert len(medicare) == 4 and all(key in same for key in medicare)
    quoted(
        "The four Medicare rows stayed the same to every digit: `medicare_cost` and the Part D surcharge, in 2024 and 2026."
    )


@pytest.mark.parametrize(
    "figure",
    (
        "16 of the 19",
        "15 of 20",
        "33 to 47 minutes",
        "Nothing here attributes a row's movement to a particular change.",
        "Nothing here attributes any other movement",
        "One movement is attributed to a cause",
        # Figures of the measurement with 2.144.4 as head.
        "204 in all",
        "it stays at $880.02bn",
        "Two rows cannot move",
        "Four earlier scoring runs",
        "in three places",
        "about 15 minutes",
        "seconds on 2.144.4",
        "under 2.144.4, for none",
        # Wording a review replaced.
        "for promotion",
        "Times vary a lot",
        "comes to",
    ),
)
def test_superseded_figures_are_gone(figure):
    assert figure not in README


SCORED = RESULTS / "critical-targets"


def scored(name: str) -> dict:
    return json.loads((SCORED / name).read_text())


def test_scoring_run_and_counts():
    record = scored("provenance.json")
    quoted(f"Scored on {record['started'][:10]}: [workflow run {record['workflow_run']}]({record['url']})")
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
    assert math.isclose(margin, result["exact"]["tally"]["smallest_tested_margin"]["margin"], rel_tol=1e-12)
    quoted(
        f"Under {HEAD}, federal income tax liability against SOI Historic Table 2 comes closest to its tolerance: "
        f"{pct(tested['tested_error'])} against ±{tested['tolerance'] * 100:.0f}%, {margin * 100:.1f} points inside it. "
        f"{PINNED} puts that row's error at {pct(tested['baseline_error'])} and comes closest to tolerance on Social "
        f"Security benefits, at {pct(baseline['baseline_error'])} against ±{baseline['tolerance'] * 100:.0f}%."
    )


def test_table_1_4_movement():
    table = scored("critical_targets.json")["table_1_4"]
    moved = [row for row in table["rows"] if not math.isclose(row["baseline"], row["tested"], rel_tol=1e-9)]
    assert len(moved) == table["tally"]["rows"] - table["tally"]["same_under_both"] == 1
    (row,) = moved
    assert row["label"].endswith("taxable_social_security_amount@2024")
    quoted(
        f"{table['tally']['same_under_both']} of the {table['tally']['rows']} SOI Table 1.4 rows have the same estimate "
        "under both releases, to nine significant figures",
        f"Only taxable Social Security moves, from {pct(row['baseline_error'])} to {pct(row['tested_error'])}.",
    )


def test_programme_totals():
    headline = {row["metric_id"]: row for row in scored("critical_targets.json")["headline"]}
    panel_ids = set(panel(2024))
    shared = sorted(set(headline) & panel_ids)
    (alone,) = set(headline) - panel_ids
    part_b = headline[alone]
    assert alone == "medicare_part_b_irmaa_total" and part_b["baseline"] == 0 < part_b["tested"]
    quoted(
        f"{len(shared)} of the scorer's {len(headline)} programme and income totals also appear as rows",
        f"and a test checks all {len(shared)}",
        f"The scorer puts it at $0 under {PINNED} and {bn(part_b['tested'])} under {HEAD}",
    )
    part_d = panel(2024)["medicare_part_d_irmaa_total"]
    assert part_d["baseline"] == 0 < part_d["tested"]
    quoted(
        f"so {PINNED} puts both at zero in 2024, for the reason above. The panel has no Part B row; Microcosm's "
        "scorer measures the Part B surcharge (below)."
    )


def test_newly_read_column_and_roles():
    result = scored("critical_targets.json")
    assert result["newly_read_columns"] == ["tax_unit_role_input"]
    roles = result["tax_unit_roles"]
    assert roles["tested"]["persons_differing"] == 0 == roles["tested"]["weighted_persons_differing"]
    agi = {row["metric_id"]: row for row in result["headline"]}["adjusted_gross_income_total"]
    assert agi["newly_read_inputs_effect"] < 0 < agi["difference"]
    quoted(
        f"{HEAD} reads one stored column that {PINNED} does not define, `tax_unit_role_input`",
        f"Under {PINNED}, the tax-unit roles the engine assigns differ from the stored ones for "
        f"{roles['baseline']['persons_differing']:,} people "
        f"({roles['baseline']['weighted_persons_differing'] / 1e6:.1f} million weighted); under {HEAD}, for none",
        f"lowers adjusted gross income under {HEAD} by {bn(agi['newly_read_inputs_effect'], 1)}: "
        f"adjusted gross income rises {bn(agi['difference'], 1)} between the releases with it and "
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
    quoted(f"With it withheld, {HEAD} still keeps all {len(within)} scored rows within tolerance.")
    quoted(
        "- The panel measures how far each total moved between the releases, not why. The README names causes of "
        f"movements in five places, all above. Scoring {HEAD} without the stored column it newly reads, "
        "`tax_unit_role_input`, measures that column's effect on every scored total. The releases' source shows why "
        f"{PINNED} puts both Medicare surcharges at zero in 2024, and why Medicaid spending rose. It shows which "
        "Medicare definitions and rules changed, though the panel "
        "cannot split the Medicare rise among them. And it shows which Medicaid eligibility rules changed between "
        f"{EARLIER_HEAD} and {HEAD}, though the panel cannot split the fall in enrollment among them. The README "
        "attributes no other movement to a cause."
    )


def test_refused_columns():
    verdict = scored("critical_targets.json")["stored_input_verdict"]
    assert not verdict["baseline"]["passed"] and not verdict["tested"]["passed"]
    both = sorted(set(verdict["baseline"]["refused"]) & set(verdict["tested"]["refused"]))
    only_tested = sorted(set(verdict["tested"]["refused"]) - set(verdict["baseline"]["refused"]))
    assert set(verdict["baseline"]["refused"]) <= set(verdict["tested"]["refused"])
    assert both == ["medicare_part_b_premiums", "would_claim_wic"]
    assert only_tested == ["first_home_mortgage_interest", "second_home_mortgage_interest"]
    quoted(f"`would_claim_wic` and `medicare_part_b_premiums` under both, and under {HEAD} also the two mortgage-interest columns")


def test_scope_of_the_critical_rows():
    result = scored("critical_targets.json")
    names = [row["label"] for part in ("exact", "table_1_4") for row in result[part]["rows"]]
    names += [row["target_name"] for row in result["unscored_critical_rows"]]
    assert all(name.endswith("@2024") and name.split(".")[0] in ("irs_soi", "ssa_supplement") for name in names)
    years = {name: name.split(".")[1] for name in names}
    current = sorted(name for name, year in years.items() if year in ("ty2024", "cy2024"))
    assert len(current) == 3
    assert sum(name.startswith("irs_soi.ty2024.filing_season_") and "earned_income_credit" in name for name in current) == 2
    assert sum(name.startswith("ssa_supplement.cy2024.") and "social_security_benefits" in name for name in current) == 1
    assert {year for name, year in years.items() if name not in current} == {"ty2022", "ty2023"}
    quoted(
        "Every critical row targets a 2024 national total, and IRS Statistics of Income (SOI) or the Social Security "
        "Administration supplies each target. Only three targets come from 2024 data: Social Security benefits, from "
        "the Social Security Administration's figures for calendar year 2024, and the two EITC targets, from SOI's "
        "filing-season statistics for tax year 2024. The other SOI targets come from tax-year 2022 and 2023 publications."
    )
    moves = sorted(
        (row for row in panel(2024).values() if row["relative_difference"] is not None),
        key=lambda row: -abs(row["relative_difference"]),
    )
    top = [row["id"] for row in moves[:6]]
    assert top == ["medicare_cost_total", "people_in_spm_poverty", "medicaid_total", "state_income_tax_total", "snap_total", "ssi_total"]
    part_d = panel(2024)["medicare_part_d_irmaa_total"]
    assert part_d["baseline"] == 0 and part_d["relative_difference"] is None
    quoted(
        "None covers Medicare, poverty, Medicaid spending, state income tax or SNAP (the five panel rows with a ratio "
        f"that moved most in 2024), SSI, Medicare's Part D surcharge (which went from $0 to {bn(part_d['tested'])} and "
        "so has no ratio), or WIC. Passing these rows therefore leaves those movements untested against outside figures."
    )


# The releases every earlier scoring run scored (EARLIER_RELEASES in
# tests/test_scoring.py), from the note of the last of them: the pinned
# release as baseline, and the head release the previous measurement held as
# tested.
SCORED_EARLIER = dict(zip(("baseline", "tested"), EARLIER_SCORE_RELEASES))
COUNT = ("one", "two", "three", "four", "five", "six")


def relative(a: float, b: float) -> float:
    return 0.0 if a == b else abs(a - b) / max(abs(a), abs(b))


def test_earlier_scoring_runs():
    """The README compares the earlier runs with this one only for the side
    that scored the same release, and the earlier runs with one another on
    the release they all scored as tested."""
    assert SCORED_EARLIER["tested"] == EARLIER_HEAD
    result = scored("critical_targets.json")
    same = [side for side in SCORED_EARLIER if result[side]["versions"]["policyengine-us"] == SCORED_EARLIER[side]]
    assert same == ["baseline"], "the README compares the earlier runs with this one on the baseline only"
    now = {row["metric_id"]: row for row in scored("drift.json")["rows"]}
    runs = sorted(
        (json.loads(path.read_text()) for path in (SCORED / "earlier").glob("run-*-rows.json")),
        key=lambda run: run["workflow_run"],
    )
    last = {row["metric_id"]: row for row in json.loads((SCORED / "earlier" / EARLIER_SCORES).read_text())["rows"]}
    assert runs[-1]["workflow_run"] == json.loads((SCORED / "earlier" / EARLIER_SCORES).read_text())["workflow_run"]
    worst = {"baseline": 0.0, "tested": 0.0}
    for run in runs:
        assert {row["metric_id"] for row in run["rows"]} == set(last) == set(now)
        for row in run["rows"]:
            worst["baseline"] = max(worst["baseline"], relative(now[row["metric_id"]]["baseline"], row["baseline"]))
            for key in ("tested", "without_newly_read_inputs"):
                worst["tested"] = max(worst["tested"], relative(last[row["metric_id"]][key], row[key]))
            if row["within_tolerance"] is not None:
                assert now[row["metric_id"]]["within_tolerance"]["baseline"] == row["within_tolerance"]["baseline"]
                assert last[row["metric_id"]]["within_tolerance"] == row["within_tolerance"]
    assert 0 < worst["baseline"] < 1e-15 and 0 < worst["tested"] < 1e-15
    dates = sorted(run["date"][:10] for run in runs)
    # The runs whose installs were not constrained came first, and the
    # repository keeps their freezes.
    free = [run for run in runs if "installs were not constrained" in run["note"]]
    assert free == runs[: len(free)] and len(free) == 2
    freezes = [
        {
            side: dict(line.split("==") for line in (SCORED / "earlier" / f"run-{run['workflow_run']}-freeze-{side}.txt").read_text().splitlines() if "==" in line)
            for side in ("pinned", "head", "head-without-newly-read")
        }
        for run in free
    ]
    changed = {side: {name for name in freezes[0][side] if freezes[0][side][name] != freezes[1][side].get(name)} for side in freezes[0]}
    assert len({frozenset(names) for names in changed.values()}) == 1
    assert all(set(freezes[0][side]) == set(freezes[1][side]) for side in freezes[0])
    quoted(
        f"{COUNT[len(runs) - 1].capitalize()} earlier scoring runs, from {dates[0]} to {dates[-1]}, scored "
        f"{SCORED_EARLIER['baseline']} against {SCORED_EARLIER['tested']}, each with an earlier version of this "
        "repository's scoring code.",
        f"The first {COUNT[len(free) - 1]} installed packages without `envs/score.constraints.txt`, and "
        f"{COUNT[len(changed['pinned']) - 1]} package versions differ between those two installs; "
        f"`results/critical-targets/earlier/` keeps their freezes. The other {COUNT[len(runs) - len(free) - 1]} "
        "installed under that file.",
        f"For {PINNED} they gave the same verdict for every row as this run, and every estimate agrees with this "
        f"run's to within {math.ceil(worst['baseline'] * 1e16)} parts in 10¹⁶; a test checks them to 1 part in 10¹⁵.",
        f"For {EARLIER_HEAD}, with and without `tax_unit_role_input`, the {COUNT[len(runs) - 1]} runs gave one another "
        f"the same verdicts and agree to within {math.ceil(worst['tested'] * 1e16)} parts in 10¹⁶.",
        f"The next subsection compares the last run's {EARLIER_HEAD} scores with this run's {HEAD} scores.",
        f"the earlier scoring runs in `results/critical-targets/earlier/` agree with this one for {PINNED}, the release "
        "both scored.",
    )


def test_scores_since_the_previous_head():
    """The previous run's scores of its head release, against this run's."""
    assert EARLIER_HEAD != HEAD
    result = scored("critical_targets.json")
    before = {row["metric_id"]: row for row in json.loads((SCORED / "earlier" / EARLIER_SCORES).read_text())["rows"]}
    rows = [row for part in ("exact", "table_1_4") for row in result[part]["rows"]]
    assert all(row["tested_within"] for row in rows)
    assert all(before[row["metric_id"]]["within_tolerance"]["tested"] for row in rows)
    worst = max(abs(row["tested"] / before[row["metric_id"]]["tested"] - 1) for row in rows)
    quoted(
        f"In the scores, {HEAD} keeps every scored row within tolerance, as {EARLIER_HEAD} did. Its estimates for the "
        f"{len(rows)} scored rows differ from {EARLIER_HEAD}'s by at most {math.ceil(worst * 1e4) / 100:.2f}%."
    )
