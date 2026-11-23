"""Invariants of the scoring helpers.

- Deriving the scorer's diagnostics adds the SPM selection and changes nothing
  else: undoing it gives back the input, for any diagnostics.
- A row counts as within tolerance exactly when its error's size does not
  exceed the tolerance, and the tally's counts follow from the rows.
- The wheels fetched for scoring carry the versions the measured run recorded.
- The committed tables rebuild byte for byte from the committed ``drift.json``,
  the scores came from the scoring code in this tree, and they used the
  measured releases and dataset.
- Microcosm's batched scorer and this repository's whole-file panel give the
  same 2024 totals, for exactly the 13 totals both compute.
- Every committed score file still has the hash the record holds. Recording
  took those hashes from the run's artifact, so the committed files are the
  ones the recorded run uploaded; the tests do not download it again. The
  estimates are named for the build that made them.
- Four earlier runs agree with the committed scores to within rounding. The
  first two, whose installs were not constrained, differed in five packages;
  the other two ran under the constraints and earlier scoring code.
"""

import copy
import json
import math
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import critical_targets  # noqa: E402
import fetch_wheels  # noqa: E402
import prepare_scoring  # noqa: E402
import provenance  # noqa: E402
from rules import stamped_by_one_run  # noqa: E402

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text(max_size=5),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=4), children, max_size=3),
    max_leaves=12,
)
diagnostics = st.fixed_dictionaries(
    {"build": st.dictionaries(st.text(max_size=4).filter(lambda k: k != "post_export_scoring"), json_values, max_size=3)},
    optional={"targets": st.lists(json_values, max_size=3), "options": json_values},
)


@given(diagnostics)
def test_derive_adds_only_the_selection(original):
    before = copy.deepcopy(original)
    derived = prepare_scoring.derive(original)
    assert original == before, "derive must not change its input"
    assert derived["build"]["post_export_scoring"] == {"spm": prepare_scoring.SPM_SELECTION}
    restored = prepare_scoring.restore(derived)
    restored["build"].pop("post_export_scoring")
    assert restored == before
    assert json.loads(json.dumps(derived)) == derived


def test_derive_refuses_diagnostics_that_already_have_a_selection():
    with pytest.raises(ValueError):
        prepare_scoring.derive({"build": {"post_export_scoring": {"spm": {"geography_kind": "national"}}}})
    with pytest.raises(ValueError):
        prepare_scoring.derive({"targets": []})


def test_report_names_the_measured_dataset():
    measured = json.loads((ROOT / "results" / "pinned" / "environment.json").read_text())["dataset"]
    report = prepare_scoring.report()["dataset"]
    assert report["sha256"] == measured["sha256"] == prepare_scoring.DATASET_SHA256
    assert report["filename"] == measured["file"]


@pytest.mark.parametrize("run", ("pinned", "head"))
def test_wheels_carry_the_measured_versions(run):
    environment = json.loads((ROOT / "results" / run / "environment.json").read_text())
    pins = fetch_wheels.pins(environment)
    assert set(pins) == set(fetch_wheels.PACKAGES)
    assert all(pins[name] == environment["packages"][name] for name in pins)


def test_pins_refuse_an_environment_without_a_version():
    with pytest.raises(ValueError):
        fetch_wheels.pins({"packages": {"policyengine-us": "1", "policyengine-core": "2", "spm-calculator": None}})


def drift_row(requirement, target, baseline, tested, tolerance):
    row = {
        "metric_id": f"target:{requirement}",
        "label": requirement,
        "unit": "usd",
        "requirement_id": requirement,
        "baseline": baseline,
        "tested": tested,
        "difference": tested - baseline,
        "relative_difference": None if baseline == 0 else (tested - baseline) / abs(baseline),
        "target": target,
        "build_estimate": target,
    }
    if target:
        errors = {"baseline": (baseline - target) / abs(target), "tested": (tested - target) / abs(target)}
        row["target_relative_error"] = errors
        row["tolerance"] = tolerance
        row["within_tolerance"] = {side: abs(error) <= tolerance for side, error in errors.items()}
    return row


amounts = st.floats(min_value=1.0, max_value=1e12, allow_nan=False)
tolerances = st.sampled_from([0.05, 0.10, 0.15, 0.20, 0.25])


@given(st.lists(st.tuples(amounts, amounts, amounts, tolerances), min_size=1, max_size=8))
def test_tally_follows_from_the_rows(values):
    drift = {
        "rows": [drift_row(f"r{i}", t, b, x, tol) for i, (t, b, x, tol) in enumerate(values)]
        + [{"metric_id": "snap_total", "label": "SNAP", "unit": "usd", "requirement_id": None, "baseline": 1.0, "tested": 2.0}]
    }
    rows = critical_targets.requirement_rows(drift)
    assert len(rows) == len(values)
    for row in rows:
        assert row["baseline_within"] == (abs(row["baseline_error"]) <= row["tolerance"])
        assert row["tested_within"] == (abs(row["tested_error"]) <= row["tolerance"])
        assert row["build_error"] == 0
    tally = critical_targets.tally(rows)
    assert tally["rows"] == tally["rows_with_a_tolerance"] == len(values)
    for side in ("baseline", "tested"):
        assert tally[f"{side}_within"] + len(tally[f"{side}_outside"]) == len(values)
    assert set(tally["leaving_tolerance"]) <= set(tally["tested_outside"])
    assert set(tally["entering_tolerance"]) <= set(tally["baseline_outside"])
    assert not set(tally["leaving_tolerance"]) & set(tally["entering_tolerance"])
    assert len(critical_targets.headline_rows(drift)) == 1


def test_known_tolerance_edges():
    rows = critical_targets.requirement_rows(
        {"rows": [drift_row("a", 100.0, 105.0, 106.0, 0.05), drift_row("b", 100.0, 80.0, 90.0, 0.15)]}
    )
    tally = critical_targets.tally(rows)
    assert tally["leaving_tolerance"] == ["target:a"]
    assert tally["entering_tolerance"] == ["target:b"]
    assert tally["baseline_within"] == 1 and tally["tested_within"] == 1


def test_newly_read_columns_come_from_the_tested_score():
    tested = {"engine": {"column_changes": {"read": [{"column": "b"}, {"column": "a"}], "ignored": []}}}
    assert critical_targets.newly_read_columns(tested) == ["a", "b"]


def score_document(version):
    return {
        "runtime": {
            "packages": {
                "policyengine-us": {"version": version},
                "policyengine-core": {"version": "3.0.0"},
                "spm-calculator": {"version": "1.1.0"},
            }
        },
        "scoring": {"n_households": 10, "period": 2024, "spm": {"geography_kind": "county"}},
        "code": {"git_commit": "0" * 40},
        "engine": {
            "stored_input_verdict": {"passed": False, "refused": ["would_claim_wic"]},
            "column_changes": {"read": [], "ignored": []},
        },
    }


def test_result_and_markdown_render_from_a_drift_document():
    drift = {
        "dataset_sha256": "ab" * 32,
        "newly_read_columns": ["tax_unit_role_input"],
        "unscored_critical_rows": [],
        "rows": [
            drift_row("eitc_amount", 100.0, 105.0, 120.0, 0.15),
            drift_row("ctc_amount", 200.0, 190.0, 195.0, 0.15),
            drift_row(critical_targets.TABLE_1_4, 50.0, 80.0, 51.0, 0.25),
            {
                "metric_id": "snap_total",
                "label": "SNAP benefits",
                "unit": "usd",
                "requirement_id": None,
                "baseline": 1e11,
                "tested": 9e10,
                "difference": -1e10,
                "relative_difference": -0.1,
            },
        ],
        "scores": {"baseline": score_document("1.0.0"), "tested": score_document("2.0.0")},
    }
    built = {"build_id": "build-x", "policyengine-us": "0.9.0", "policyengine-core": "0.1.0"}
    inputs = {"dataset": {}, "estimates_from": built}
    result = critical_targets.build_result(drift, {"exact_critical_rows": 2}, inputs, ["ctc_amount", "eitc_amount", "missing_one"])
    assert [row["requirement_id"] for row in result["exact"]["rows"]] == ["ctc_amount", "eitc_amount"]
    assert result["unscored_requirements"] == ["missing_one"]
    assert result["exact"]["tally"]["leaving_tolerance"] == ["target:eitc_amount"]
    assert result["table_1_4"]["tally"]["entering_tolerance"] == [f"target:{critical_targets.TABLE_1_4}"]
    text = critical_targets.markdown(result)
    assert "| eitc_amount |" in text and "OUT" in text and "missing_one" in text
    assert "policyengine-us 2.0.0" in text and "SNAP benefits" in text
    assert "`build-x`, made with policyengine-us 0.9.0" in text
    json.dumps(result)


def test_source_is_the_first_three_name_parts():
    assert critical_targets.source("target:irs_soi.ty2022.historic_table_2.us.all.ctc_amount@2024") == (
        "irs_soi ty2022 historic_table_2"
    )
    assert critical_targets.source("plain") == "plain"


SCORED = ROOT / "results" / "critical-targets"


def test_committed_tables_regenerate_from_drift(tmp_path):
    critical_targets.render(SCORED, tmp_path)
    for name in ("drift.json", "critical_targets.json", "critical_targets.csv", "critical_targets.md"):
        assert (tmp_path / name).read_bytes() == (SCORED / name).read_bytes(), name


def test_scores_used_the_measured_releases_and_dataset():
    result = json.loads((SCORED / "critical_targets.json").read_text())
    inputs = json.loads((SCORED / "scoring_inputs-pinned.json").read_text())
    for side, run in (("baseline", "pinned"), ("tested", "head")):
        environment = json.loads((ROOT / "results" / run / "environment.json").read_text())
        assert result[side]["versions"] == fetch_wheels.pins(environment)
        assert environment["dataset"]["sha256"] == result["dataset_sha256"] == inputs["dataset"]["sha256"]
    assert result["households"] == inputs["dataset"]["households"]
    assert inputs["published_diagnostics"]["sha256"] == prepare_scoring.PUBLISHED_DIAGNOSTICS_SHA256


# The scorer's programme totals that the 2024 panel also measures. The
# scorer's fourteenth, the Part B income-related surcharge, has no panel row.
SHARED_TOTALS = {
    "income_tax_net",
    "ctc_total",
    "eitc_total",
    "social_security_total",
    "snap_total",
    "snap_units",
    "ssi_total",
    "medicaid_enrollment",
    "medicaid_total",
    "state_income_tax_total",
    "medicare_part_d_irmaa_total",
    "medicare_cost_total",
    "adjusted_gross_income_total",
}


def test_scorer_totals_equal_the_measured_panel():
    """Two harnesses, one dataset: Microcosm's batched scorer and this
    repository's whole-file panel give the same 2024 totals."""
    result = json.loads((SCORED / "critical_targets.json").read_text())
    panels = {
        side: {row["id"]: row["value"] for row in json.loads((ROOT / "results" / run / "panel-2024.json").read_text())["rows"]}
        for side, run in (("baseline", "pinned"), ("tested", "head"))
    }
    shared = [row for row in result["headline"] if row["metric_id"] in panels["baseline"]]
    assert {row["metric_id"] for row in shared} == SHARED_TOTALS
    assert {row["metric_id"] for row in result["headline"]} - SHARED_TOTALS == {"medicare_part_b_irmaa_total"}
    for row in shared:
        for side in ("baseline", "tested"):
            measured = panels[side][row["metric_id"]]
            assert abs(row[side] - measured) <= 1e-8 * max(abs(measured), 1.0), (row["metric_id"], side)


def test_scores_come_from_this_scoring_code():
    assert not provenance.is_stale("score"), "scoring code changed since these scores: run Score again"
    record = json.loads((SCORED / "provenance.json").read_text())
    assert record["workflow"] == "Score"
    assert record["artifacts"] == ["results-critical-targets"]
    assert provenance.scores_differ_from_measured() == []


def test_every_score_file_is_the_recorded_runs_artifact():
    record = json.loads((SCORED / "provenance.json").read_text())
    assert provenance.files_differ_from_record("score") == []
    assert set(record["files"]) == set(provenance.committed("score"))
    for name in ("drift.json", "critical_targets.json", "combine.json"):
        assert f"results/critical-targets/{name}" in record["files"]


def test_estimates_are_named_for_the_build_that_made_them():
    inputs = json.loads((SCORED / "critical_targets.json").read_text())["inputs"]
    built = inputs["estimates_from"]
    assert built["manifest"]["sha256"] == prepare_scoring.PARENT_MANIFEST_SHA256
    assert inputs["published_diagnostics"]["sha256"] == prepare_scoring.PUBLISHED_DIAGNOSTICS_SHA256
    assert (built["policyengine-us"], built["policyengine-core"]) == ("1.764.6", "3.26.11")
    assert built["build_id"] in (SCORED / "critical_targets.md").read_text()


def test_a_parent_listing_other_diagnostics_is_refused():
    parent = {
        "artifacts": {"calibration_diagnostics": {"sha256": "a" * 64}},
        "build": {
            "build_id": "b",
            "built_at": "t",
            "built_with_model_package": {"version": "1"},
            "built_with_core_package": {"version": "2"},
        },
    }
    assert prepare_scoring.estimates_from(parent, "a" * 64)["policyengine-us"] == "1"
    with pytest.raises(ValueError):
        prepare_scoring.estimates_from(parent, "b" * 64)


def test_scores_are_stale_when_the_measured_releases_change(tmp_path):
    for run in ("pinned", "head"):
        (tmp_path / "results" / run).mkdir(parents=True)
        (tmp_path / "results" / run / "environment.json").write_bytes((ROOT / "results" / run / "environment.json").read_bytes())
    (tmp_path / "results" / "critical-targets").mkdir()
    (tmp_path / "results" / "critical-targets" / "critical_targets.json").write_bytes((SCORED / "critical_targets.json").read_bytes())
    assert provenance.scores_differ_from_measured(tmp_path) == []
    environment = json.loads((tmp_path / "results" / "head" / "environment.json").read_text())
    environment["packages"]["policyengine-us"] = "9.9.9"
    (tmp_path / "results" / "head" / "environment.json").write_text(json.dumps(environment))
    assert provenance.scores_differ_from_measured(tmp_path) != []


def test_every_scoring_job_names_the_recorded_run_and_code():
    """The three scoring jobs and the combining job each stamped their own
    output. All four name the recorded run and carry the hashes of the
    scoring code in this tree."""
    record = json.loads((SCORED / "provenance.json").read_text())
    stamps = provenance.stamps("score")
    assert len(stamps) == len(prepare_scoring.SCORING_JOBS) + 1
    assert stamped_by_one_run(stamps, provenance.REPOSITORY, record["workflow_run"]) == record["code_sha256"]
    assert record["code_sha256"] == provenance.code_hashes("score")


def test_the_scoring_jobs_read_the_same_inputs():
    files = [json.loads((SCORED / f"scoring_inputs-{name}.json").read_text()) for name in prepare_scoring.SCORING_JOBS]
    for key in ("dataset", "published_diagnostics", "derived_diagnostics"):
        assert files[0][key] == files[1][key] == files[2][key], key
    embedded = json.loads((SCORED / "critical_targets.json").read_text())["inputs"]
    assert embedded == files[0]


def test_a_stamp_names_the_run_and_the_scoring_code():
    stamp = prepare_scoring.stamp()
    assert set(stamp) == {"run", "code_sha256"}
    assert set(stamp["code_sha256"]) == set(prepare_scoring.SCORING_CODE)
    assert {"scripts/critical_targets.py", "scripts/rules.py", ".github/workflows/score.yml"} <= set(prepare_scoring.SCORING_CODE)
    assert provenance.KINDS["score"]["code"] is prepare_scoring.SCORING_CODE


@pytest.mark.parametrize("name, run", (("pinned", "pinned"), ("head", "head"), ("head-without-newly-read", "head")))
def test_each_scoring_environment_was_the_constrained_one(name, run):
    """Every PyPI package sat at its constrained version. The only other
    installs were the measured run's three engine wheels and Microcosm's two
    packages."""
    lines = (SCORED / f"freeze-{name}.txt").read_text().splitlines()
    constraints = (ROOT / "envs" / "score.constraints.txt").read_text().splitlines()
    assert [line for line in lines if "==" in line] == constraints
    others = [line for line in lines if "==" not in line]
    editable = [line for line in others if line.startswith("-e ")]
    assert sorted(line.rsplit("/", 1)[-1] for line in editable) == ["microcosm-data", "microcosm-diagnostics"]
    environment = json.loads((ROOT / "results" / run / "environment.json").read_text())
    wheels = {line.split(" @ ", 1)[0]: line for line in others if " @ file://" in line}
    assert set(wheels) == set(fetch_wheels.PACKAGES)
    for package, version in fetch_wheels.pins(environment).items():
        assert wheels[package].endswith(f"/{package.replace('-', '_')}-{version}-py3-none-any.whl"), package
    assert len(others) == len(editable) + len(wheels)


EARLIER_RUNS = (44345993218, 44903905024, 44910821596, 45199019867)
# The two earlier runs whose installs were not constrained.
UNCONSTRAINED_RUNS = EARLIER_RUNS[:2]


@pytest.mark.parametrize("run", EARLIER_RUNS)
def test_an_earlier_scoring_run_gave_the_same_rows(run):
    """Earlier runs, the first two under installs that were not constrained
    and the others under earlier scoring code, agree with the committed scores:
    every estimate to within 1 part in 10^15, and every target, tolerance and
    verdict exactly."""
    earlier = json.loads((SCORED / "earlier" / f"run-{run}-rows.json").read_text())
    record = json.loads((SCORED / "provenance.json").read_text())
    assert earlier["workflow_run"] == run != record["workflow_run"]
    assert earlier["date"] < record["started"]
    now = {row["metric_id"]: row for row in json.loads((SCORED / "drift.json").read_text())["rows"]}
    assert set(now) == {row["metric_id"] for row in earlier["rows"]}
    for row in earlier["rows"]:
        current = now[row["metric_id"]]
        for key in ("baseline", "tested", "without_newly_read_inputs"):
            assert math.isclose(current[key], row[key], rel_tol=1e-15, abs_tol=0.0), (row["metric_id"], key)
        for key in ("requirement_id", "target", "tolerance", "within_tolerance"):
            assert current.get(key) == row[key], (row["metric_id"], key)


def exact_pins(path: Path) -> dict[str, str]:
    return dict(line.split("==", 1) for line in path.read_text().splitlines() if "==" in line)


@pytest.mark.parametrize("job", prepare_scoring.SCORING_JOBS)
def test_the_earlier_runs_installs_differed_in_five_packages(job):
    first, second = (exact_pins(SCORED / "earlier" / f"run-{run}-freeze-{job}.txt") for run in UNCONSTRAINED_RUNS)
    assert set(first) == set(second)
    assert sorted(name for name in first if first[name] != second[name]) == [
        "certifi",
        "decorator",
        "pydantic",
        "pydantic-core",
        "pyyaml",
    ]
