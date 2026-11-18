"""Invariants of the scoring helpers.

- Deriving the scorer's diagnostics adds the SPM selection and changes nothing
  else: undoing it gives back the input, for any diagnostics.
- A row counts as within tolerance exactly when its error's size does not
  exceed the tolerance, and the tally's counts follow from the rows.
- The wheels fetched for scoring carry the versions the measured run recorded.
"""

import copy
import json
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
    result = critical_targets.build_result(drift, {"exact_critical_rows": 2}, {"dataset": {}}, ["ctc_amount", "eitc_amount", "missing_one"])
    assert [row["requirement_id"] for row in result["exact"]["rows"]] == ["ctc_amount", "eitc_amount"]
    assert result["unscored_requirements"] == ["missing_one"]
    assert result["exact"]["tally"]["leaving_tolerance"] == ["target:eitc_amount"]
    assert result["table_1_4"]["tally"]["entering_tolerance"] == [f"target:{critical_targets.TABLE_1_4}"]
    text = critical_targets.markdown(result)
    assert "| eitc_amount |" in text and "OUT" in text and "missing_one" in text
    assert "policyengine-us 2.0.0" in text and "SNAP benefits" in text
    json.dumps(result)
