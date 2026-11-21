"""Invariants of the pure rules.

- Classification partitions the stored columns: every distinct column lands in
  exactly one class.
- A name the release defines takes its class from the definition, whatever
  its spelling. An undefined name is a missing variable when it follows the
  model's convention and a raw field when it does not. The names are built
  to be inside or outside the convention, so the test does not lean on the
  rule's own pattern.
- A comparison's difference and ratio follow from its two values, and
  swapping the sides flips the sign of the difference.
- Aligning stored values by id puts each value on the row with its id, and
  refuses repeated or unmatched ids.
- The comparison refuses runs that are incomplete or not alike.
- Results are stale exactly when a measurement file differs from the record.
"""

import json
import math
import string
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import compare  # noqa: E402
import measure  # noqa: E402
import provenance  # noqa: E402
from rules import (  # noqa: E402
    CLASSES,
    classify_column,
    classify_columns,
    compare_values,
    relative_difference,
)

names = st.text(alphabet="abcXYZ_019", min_size=1, max_size=6)
# Names built to follow the model's convention: a lower-case letter, then
# lower-case letters, digits or underscores.
model_style = st.builds(
    lambda first, rest: first + rest,
    st.sampled_from(string.ascii_lowercase),
    st.text(alphabet=string.ascii_lowercase + string.digits + "_", max_size=8),
)
# Names built to break it: an upper-case letter somewhere, or a first
# character that is not a lower-case letter.
with_upper = st.builds(
    lambda head, upper, tail: head + upper + tail,
    st.text(alphabet=string.ascii_lowercase + string.digits + "_", max_size=4),
    st.sampled_from(string.ascii_uppercase),
    st.text(alphabet=string.ascii_letters + string.digits + "_", max_size=4),
)
bad_start = st.builds(
    lambda first, rest: first + rest,
    st.sampled_from(string.digits + "_"),
    st.text(alphabet=string.ascii_lowercase + string.digits + "_", max_size=6),
)
raw_style = with_upper | bad_start
finite = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e15, max_value=1e15)


@given(st.lists(names, max_size=30), st.dictionaries(names, st.booleans(), max_size=30))
def test_classification_partitions_the_columns(columns, variables):
    result = classify_columns(columns, variables)
    assert set(result) == set(CLASSES)
    flat = [c for cols in result.values() for c in cols]
    assert sorted(flat) == sorted(set(columns))
    assert len(flat) == len(set(flat))


@given(model_style | raw_style, st.booleans(), st.dictionaries(names, st.booleans(), max_size=10))
def test_a_defined_name_takes_its_class_from_the_definition(column, computed, others):
    variables = {**others, column: computed}
    assert classify_column(column, variables) == ("computed_variable" if computed else "input_variable")


@given(model_style, st.dictionaries(raw_style, st.booleans(), max_size=10))
def test_an_undefined_model_style_name_is_a_missing_variable(column, variables):
    assert classify_column(column, variables) == "not_a_variable"


@given(raw_style, st.dictionaries(model_style, st.booleans(), max_size=10))
def test_an_undefined_name_outside_the_convention_is_a_raw_field(column, variables):
    assert classify_column(column, variables) == "raw_field"


def test_known_examples():
    variables = {"employment_income": False, "income_tax": True, "CA_credit": False}
    assert classify_column("A_AGE", variables) == "raw_field"
    assert classify_column("would_claim_wic", variables) == "not_a_variable"
    assert classify_column("income_tax", variables) == "computed_variable"
    assert classify_column("employment_income", variables) == "input_variable"
    assert classify_column("CA_credit", variables) == "input_variable"
    assert classify_column("_private", variables) == "raw_field"
    assert classify_column("2nd_job", variables) == "raw_field"


@given(finite, finite)
def test_comparison_is_consistent(baseline, tested):
    row = compare_values(baseline, tested)
    assert row["difference"] == tested - baseline
    swapped = compare_values(tested, baseline)
    assert swapped["difference"] == -row["difference"]
    ratio = row["relative_difference"]
    if baseline == 0:
        assert ratio is None
    else:
        assert ratio == (tested - baseline) / abs(baseline)
        assert (ratio > 0) == (tested > baseline) or ratio == 0


def test_undefined_ratios():
    assert relative_difference(0.0, 5.0) is None
    assert relative_difference(math.nan, 5.0) is None
    assert relative_difference(1.0, math.inf) is None
    assert compare_values(None, 3.0)["difference"] is None


def environment(label):
    return {
        "label": label,
        "packages": {"policyengine-us": label, "policyengine-core": "c", "spm-calculator": "s"},
        "dataset": {"file": "f.h5", "revision": "r", "sha256": "ab" * 32},
    }


def contract(unknown):
    return {
        "stored_columns": 4,
        "counts": {"input_variable": 1, "computed_variable": 0, "not_a_variable": len(unknown), "raw_field": 1},
        "not_a_variable": unknown,
        "computed_variable": [],
        "required_source_inputs_missing": None,
        "rejected_inputs_stored": None,
    }


def panel_row(value, **changes):
    row = {"period": 2024, "id": "x_total", "variable": "x", "kind": "sum", "unit": "usd", "value": value, "error": None}
    return {**row, **changes}


def write_run(directory, label, value, unknown, rows=None):
    directory.mkdir()
    (directory / "environment.json").write_text(json.dumps(environment(label)))
    (directory / "contract.json").write_text(json.dumps(contract(unknown)))
    (directory / "panel-2024.json").write_text(json.dumps({"rows": [panel_row(value)] if rows is None else rows}))
    (directory / "wic-loaded.json").write_text(
        json.dumps({"wic_as_loaded": value, "take_up_share_as_loaded": 1.0, "would_claim_wic_is_a_variable": False})
    )
    (directory / "wic-stored.json").write_text(
        json.dumps({"wic_with_stored_draw": value / 2, "take_up_share_with_stored_draw": 0.04})
    )


def run_compare(a, b, out):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compare.py"), str(a), str(b), "--out", str(out)],
        capture_output=True,
        text=True,
    )


def test_compare_end_to_end(tmp_path):
    write_run(tmp_path / "a", "1.0", 100.0, ["old_name"])
    write_run(tmp_path / "b", "2.0", 110.0, ["old_name", "removed_column"])
    out = tmp_path / "out"
    done = run_compare(tmp_path / "a", tmp_path / "b", out)
    assert done.returncode == 0, done.stderr
    result = json.loads((out / "comparison.json").read_text())
    row = result["panel"][0]
    assert row["difference"] == pytest.approx(10.0)
    assert row["relative_difference"] == pytest.approx(0.10)
    assert row["unit"] == "usd"
    assert result["contract"]["not_a_variable_only_in_tested"] == ["removed_column"]
    assert result["contract"]["not_a_variable_in_both"] == ["old_name"]
    assert result["wic"]["tested"]["wic_with_stored_draw"] == pytest.approx(55.0)
    text = (out / "comparison.md").read_text()
    assert "removed_column" in text and "| dollars |" in text


INCOMPLETE = {
    "a row in error": [panel_row(None, error="boom")],
    "a row that is not finite": [panel_row(math.inf)],
    "a row only one run measured": [panel_row(110.0), panel_row(1.0, id="y_total")],
    "a row counted in another unit": [panel_row(110.0, unit="people")],
    "a row from another variable": [panel_row(110.0, variable="z")],
    "a row measured twice": [panel_row(110.0), panel_row(110.0)],
}


@pytest.mark.parametrize("case", sorted(INCOMPLETE))
def test_compare_refuses_runs_that_are_not_alike(tmp_path, case):
    write_run(tmp_path / "a", "1.0", 100.0, [])
    write_run(tmp_path / "b", "2.0", 110.0, [], rows=INCOMPLETE[case])
    assert compare.problems(tmp_path / "a", tmp_path / "b")
    done = run_compare(tmp_path / "a", tmp_path / "b", tmp_path / "out")
    assert done.returncode != 0
    assert not (tmp_path / "out" / "comparison.json").exists()


@pytest.mark.parametrize("missing", compare.RUN_FILES + ("panel-2024.json",))
def test_compare_refuses_a_run_with_a_missing_file(tmp_path, missing):
    write_run(tmp_path / "a", "1.0", 100.0, [])
    write_run(tmp_path / "b", "2.0", 110.0, [])
    (tmp_path / "b" / missing).unlink()
    assert run_compare(tmp_path / "a", tmp_path / "b", tmp_path / "out").returncode != 0


def test_complete_runs_have_no_problems(tmp_path):
    write_run(tmp_path / "a", "1.0", 100.0, [])
    write_run(tmp_path / "b", "2.0", 110.0, [])
    assert compare.problems(tmp_path / "a", tmp_path / "b") == []


# No deadline: the first call imports numpy.
@settings(deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=10**12), min_size=1, max_size=40, unique=True), st.randoms())
def test_alignment_puts_each_value_on_the_row_with_its_id(ids, random):
    stored_ids = list(ids)
    random.shuffle(stored_ids)
    stored_values = [identifier % 7 for identifier in stored_ids]
    aligned = measure.align_by_id(ids, stored_ids, stored_values)
    assert [int(value) for value in aligned] == [identifier % 7 for identifier in ids]


def test_alignment_refuses_ambiguous_or_unmatched_ids():
    with pytest.raises(ValueError):
        measure.align_by_id([1, 2, 3], [1, 2, 2], [True, False, True])
    with pytest.raises(ValueError):
        measure.align_by_id([1, 1, 3], [1, 2, 3], [True, False, True])
    with pytest.raises(ValueError):
        measure.align_by_id([1, 2, 4], [1, 2, 3], [True, False, True])
    with pytest.raises(ValueError):
        measure.align_by_id([1, 2], [1, 2, 3], [True, False, True])
    with pytest.raises(ValueError):
        measure.align_by_id([1, 2, 3], [1, 2, 3], [True, False])


def test_the_panel_is_well_formed():
    ids = [row[0] for row in measure.PANEL]
    assert len(set(ids)) == len(ids)
    for _, _, kind, unit in measure.PANEL:
        assert kind in ("sum", "count_positive") and unit in measure.UNITS
    assert all(unit != measure.USD for _, _, kind, unit in measure.PANEL if kind == "count_positive")
    counts = [row[0] for row in measure.PANEL if row[3] != measure.USD]
    assert counts == ["snap_units", "medicaid_enrollment", "people_in_spm_poverty"]


def test_a_panel_row_without_a_value_fails_the_part():
    payload = {"rows": [panel_row(1.0), panel_row(None, id="y_total", error="boom")]}
    assert measure.panel_errors(payload) == ["y_total: boom"]
    assert measure.panel_errors({"rows": [panel_row(1.0)]}) == []


def test_a_result_file_is_never_replaced(tmp_path):
    measure.write(tmp_path / "x.json", {"a": 1})
    with pytest.raises(FileExistsError):
        measure.write(tmp_path / "x.json", {"a": 2})
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": 1}


def test_results_are_stale_exactly_when_the_code_differs(tmp_path):
    kind = provenance.KINDS["measure"]
    for path in kind["code"]:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(f"content of {path}\n")
    assert provenance.is_stale("measure", tmp_path), "no record yet"
    record = tmp_path / kind["record"]
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"code_sha256": provenance.code_hashes("measure", tmp_path)}))
    assert not provenance.is_stale("measure", tmp_path)
    for path in kind["code"]:
        original = (tmp_path / path).read_text()
        (tmp_path / path).write_text(original + "changed\n")
        assert provenance.is_stale("measure", tmp_path), path
        (tmp_path / path).write_text(original)
    assert not provenance.is_stale("measure", tmp_path)
