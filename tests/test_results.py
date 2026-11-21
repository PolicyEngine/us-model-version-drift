"""Invariants of the committed results.

- The comparison is a pure function of the two runs' files: regenerating it
  gives the committed files byte for byte.
- The results were measured by the measurement code in this tree: the hashes
  recorded with them equal the files' hashes. A change to that code fails
  here until someone measures again.
- Each run installed exactly its lock file, and the lock agrees with the
  releases its environment file pins. The two locks differ in the engine
  packages only.
- Both runs read the same dataset bytes, the bytes each release certifies as
  its default.
- Each run measured exactly the panel the code defines, every row with a
  finite value.
- The contract's classes follow from the recorded definitions under the
  classification rule, table by table.
- The stored WIC draw was applied to every person, matched on a unique id.
- Two separate processes agree on WIC as loaded, and an earlier run agrees
  with this one on every row it measured.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
sys.path.insert(0, str(ROOT / "scripts"))

import measure  # noqa: E402
import provenance  # noqa: E402
from rules import CLASSES, classify_columns  # noqa: E402

RUNS = ("pinned", "head")
ENGINE_PACKAGES = {"policyengine-us", "policyengine-core"}


def load(*parts: str) -> dict:
    return json.loads(RESULTS.joinpath(*parts).read_text())


def test_comparison_regenerates_byte_for_byte(tmp_path):
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "compare.py"),
            str(RESULTS / "pinned"),
            str(RESULTS / "head"),
            "--out",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    for name in ("comparison.json", "comparison.csv", "comparison.md"):
        assert (tmp_path / name).read_bytes() == (RESULTS / name).read_bytes(), name


def test_results_come_from_this_measurement_code():
    assert not provenance.is_stale("measure"), "measurement code changed since these results: run Measure again"
    record = load("provenance.json")
    assert record["workflow"] == "Measure"
    assert record["artifacts"] == ["results-pinned", "results-head"]
    assert record["started"] < record["completed"]


def pins(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.strip().split("==")
            out[name] = version
    return out


@pytest.mark.parametrize("run", RUNS)
def test_each_run_installed_its_lock(run):
    wanted = pins(ROOT / "envs" / f"{run}.txt")
    assert ENGINE_PACKAGES <= set(wanted), "an environment must pin both engine packages"
    lock = ROOT / "envs" / f"{run}.lock.txt"
    locked = pins(lock)
    assert len(locked) == len(lock.read_text().splitlines()), "every lock line pins one exact version"
    for name, version in wanted.items():
        assert locked[name] == version, name
    assert (RESULTS / run / "freeze.txt").read_bytes() == lock.read_bytes()
    installed = load(run, "environment.json")["packages"]
    for name, version in installed.items():
        assert locked[name] == version, name
    assert ENGINE_PACKAGES <= set(installed)


def test_the_two_locks_differ_in_the_engine_only():
    locks = [pins(ROOT / "envs" / f"{run}.lock.txt") for run in RUNS]
    assert set(locks[0]) == set(locks[1])
    assert {name for name in locks[0] if locks[0][name] != locks[1][name]} == ENGINE_PACKAGES


def test_both_runs_read_the_same_dataset_bytes():
    datasets = [load(run, "environment.json")["dataset"] for run in RUNS]
    assert datasets[0] == datasets[1]
    assert datasets[0]["sha256"] == measure.DATASET_SHA256
    for run in RUNS:
        environment = load(run, "environment.json")
        assert environment["release_default_dataset_sha256"] == measure.DATASET_SHA256


def panel(run: str) -> list[dict]:
    return [row for path in sorted((RESULTS / run).glob("panel-*.json")) for row in json.loads(path.read_text())["rows"]]


@pytest.mark.parametrize("run", RUNS)
def test_each_run_measured_exactly_the_panel(run):
    expected = {
        (period, metric_id): (variable, kind, unit)
        for period in measure.PERIODS
        for metric_id, variable, kind, unit in measure.PANEL
    }
    rows = panel(run)
    measured = {(row["period"], row["id"]): (row["variable"], row["kind"], row["unit"]) for row in rows}
    assert len(rows) == len(measured), "a row appears twice"
    assert measured == expected
    for row in rows:
        assert row["error"] is None, row
        assert isinstance(row["value"], float) and math.isfinite(row["value"]), row


@pytest.mark.parametrize("run", RUNS)
def test_contract_classes_follow_from_the_definitions(run):
    contract = load(run, "contract.json")
    definitions = contract["definitions"]
    assert set(definitions.values()) <= {None, "input", "computed"}
    variables = {column: kind == "computed" for column, kind in definitions.items() if kind is not None}
    classes = classify_columns(definitions, variables)
    assert contract["classes"] == classes
    assert contract["counts"] == {name: len(classes[name]) for name in CLASSES}
    assert contract["stored_columns"] == len(definitions) == sum(contract["counts"].values())
    assert contract["not_a_variable"] == classes["not_a_variable"]
    assert contract["computed_variable"] == classes["computed_variable"]
    stored = set()
    for table, columns in contract["tables"].items():
        assert contract["by_table"][table] == classify_columns(columns, variables), table
        stored |= set(columns)
    assert stored == set(definitions)
    assert set(contract["tables"]) == set(measure.ENTITY_TABLES)


def wic(run: str) -> dict:
    return {**load(run, "wic-loaded.json"), **load(run, "wic-stored.json")}


@pytest.mark.parametrize("run", RUNS)
def test_stored_draw_was_applied_to_every_person(run):
    values = wic(run)
    assert values["person_ids_unique_and_identical_sets"] is True
    assert values["person_ids_in_simulation"] == values["person_ids_stored"] == values["stored_draw_rows"]
    true_rows = values["stored_draw_true_rows_applied"]
    assert true_rows / values["stored_draw_rows"] == pytest.approx(values["stored_draw_share_true_unweighted"], abs=1e-12)
    assert 0 < values["take_up_share_with_stored_draw"] < values["take_up_share_as_loaded"] <= 1
    assert 0 < values["wic_with_stored_draw"] < values["wic_as_loaded"]


@pytest.mark.parametrize("run", RUNS)
def test_two_processes_agree_on_wic_as_loaded(run):
    in_panel = [row["value"] for row in panel(run) if row["id"] == "wic_total" and row["period"] == 2024]
    assert in_panel == [wic(run)["wic_as_loaded"]]


def test_an_earlier_run_gave_the_same_rows():
    earlier = load("earlier", "run-44133383190-panel-rows.json")
    assert earlier["workflow_run"] != load("provenance.json")["workflow_run"]
    compared = 0
    for run in RUNS:
        now = {(row["period"], row["id"]): row["value"] for row in panel(run)}
        then = earlier["rows"][run]
        assert sum(1 for row in then if row["period"] == 2024) == len(measure.PANEL)
        for row in then:
            assert math.isclose(now[(row["period"], row["id"])], row["value"], rel_tol=1e-9, abs_tol=0.0), row
            compared += 1
    assert compared >= 2 * len(measure.PANEL)
