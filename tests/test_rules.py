"""Invariants of the pure rules.

- Classification partitions the stored columns: every distinct column lands in
  exactly one class.
- A raw field is never classified against the model, whatever the model
  defines.
- A comparison's difference and ratio follow from its two values, and
  swapping the sides flips the sign of the difference.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rules import (  # noqa: E402
    CLASSES,
    MODEL_NAMED,
    classify_column,
    classify_columns,
    compare_values,
    relative_difference,
)

names = st.text(alphabet="abcXYZ_019", min_size=1, max_size=6)
finite = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e15, max_value=1e15)


@given(st.lists(names, max_size=30), st.dictionaries(names, st.booleans(), max_size=30))
def test_classification_partitions_the_columns(columns, variables):
    result = classify_columns(columns, variables)
    assert set(result) == set(CLASSES)
    flat = [c for cols in result.values() for c in cols]
    assert sorted(flat) == sorted(set(columns))
    assert len(flat) == len(set(flat))


@given(names, st.dictionaries(names, st.booleans(), max_size=30))
def test_each_class_means_what_it_says(column, variables):
    result = classify_column(column, variables)
    if not MODEL_NAMED.fullmatch(column):
        assert result == "raw_field"
    elif column not in variables:
        assert result == "not_a_variable"
    elif variables[column]:
        assert result == "computed_variable"
    else:
        assert result == "input_variable"


def test_known_examples():
    variables = {"employment_income": False, "income_tax": True}
    assert classify_column("A_AGE", variables) == "raw_field"
    assert classify_column("would_claim_wic", variables) == "not_a_variable"
    assert classify_column("income_tax", variables) == "computed_variable"
    assert classify_column("employment_income", variables) == "input_variable"


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


def write_run(directory, label, value, unknown):
    directory.mkdir()
    (directory / "environment.json").write_text(json.dumps(environment(label)))
    (directory / "contract.json").write_text(json.dumps(contract(unknown)))
    (directory / "panel.json").write_text(
        json.dumps({"rows": [{"period": 2024, "id": "x_total", "variable": "x", "kind": "sum", "value": value, "error": None}]})
    )
    (directory / "wic.json").write_text(json.dumps({"wic_as_loaded": value, "would_claim_wic_is_a_variable": False}))


def test_compare_end_to_end(tmp_path):
    write_run(tmp_path / "a", "1.0", 100.0, ["old_name"])
    write_run(tmp_path / "b", "2.0", 110.0, ["old_name", "removed_column"])
    out = tmp_path / "out"
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compare.py"), str(tmp_path / "a"), str(tmp_path / "b"), "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    result = json.loads((out / "comparison.json").read_text())
    row = result["panel"][0]
    assert row["difference"] == pytest.approx(10.0)
    assert row["relative_difference"] == pytest.approx(0.10)
    assert result["contract"]["not_a_variable_only_in_tested"] == ["removed_column"]
    assert result["contract"]["not_a_variable_in_both"] == ["old_name"]
    assert "removed_column" in (out / "comparison.md").read_text()
