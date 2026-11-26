"""Invariants of the committed results.

- The comparison is a pure function of the two runs' files: regenerating it
  gives the committed files byte for byte.
- The results were measured by the measurement code in this tree: the hashes
  each run stamped into its files equal the files' hashes. A change to that
  code fails here until someone measures again. Both environments' files
  name the one recorded run.
- Every committed result file is, byte for byte, the file the recorded run
  uploaded: recording took each file's hash from the run's artifacts, and
  the committed files still have those hashes, with none missing or extra.
- Each run installed exactly its lock file, and the lock agrees with the
  releases its environment file pins. The two locks differ in the engine
  packages only.
- Both runs read the same dataset bytes, the bytes each release certifies as
  its default.
- Each run measured exactly the panel the code defines, every row with a
  finite value.
- The contract's classes follow from the recorded definitions under the
  classification rule, table by table.
- The stored WIC draw was applied to every person, matched on a unique id,
  with no missing draw, and the matched people's stored age equals the
  simulation's.
- Two separate processes agree on WIC as loaded, and three earlier runs
  gave exactly this run's value for every row they measured.
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
from rules import CLASSES, classify_columns, stamped_by_one_run  # noqa: E402

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


def test_both_environments_name_the_recorded_run_and_code():
    """The run stamped its environment files itself. Both name the recorded
    run and carry the hashes of the measurement code in this tree."""
    record = load("provenance.json")
    stamps = provenance.stamps("measure")
    assert len(stamps) == len(RUNS)
    assert stamped_by_one_run(stamps, provenance.REPOSITORY, record["workflow_run"]) == record["code_sha256"]
    assert record["code_sha256"] == provenance.code_hashes("measure")
    assert record["checked_out"] == sorted({stamp["run"]["github_sha"] for stamp in stamps})
    for stamp in stamps:
        assert stamp["run"]["github_event_name"] == record["event"]


def test_every_result_file_is_the_recorded_runs_artifact():
    record = load("provenance.json")
    assert provenance.files_differ_from_record("measure") == []
    assert set(record["files"]) == set(provenance.committed("measure"))
    assert {name.split("/")[1] for name in record["files"]} == set(RUNS)
    for run in RUNS:
        assert f"results/{run}/environment.json" in record["files"]


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
    join = values["join"]
    assert join["stored_ids_unique"] and join["simulation_ids_unique"] and join["same_id_sets"]
    assert join["check_column"] == measure.CHECK_COLUMN
    assert join["check_column_rows_that_differ"] == 0
    assert values["stored_draw_missing"] == 0
    assert values["person_ids_in_simulation"] == values["person_ids_stored"] == values["stored_draw_rows"]
    true_rows = values["stored_draw_true_rows_applied"]
    assert true_rows / values["stored_draw_rows"] == pytest.approx(values["stored_draw_share_true_unweighted"], abs=1e-12)
    assert 0 < values["take_up_share_with_stored_draw"] < values["take_up_share_as_loaded"] <= 1
    assert 0 < values["wic_with_stored_draw"] < values["wic_as_loaded"]


@pytest.mark.parametrize("run", RUNS)
def test_two_processes_agree_on_wic_as_loaded(run):
    in_panel = [row["value"] for row in panel(run) if row["id"] == "wic_total" and row["period"] == 2024]
    assert len(in_panel) == 1
    assert math.isclose(in_panel[0], wic(run)["wic_as_loaded"], rel_tol=1e-12, abs_tol=0.0)


EARLIER = {
    # The first run printed these rows before its runners shut down.
    "run-44133383190-panel-rows.json": 2 * len(measure.PANEL) + 4,
    # The first complete run.
    "run-44141335692-panel-rows.json": 2 * len(measure.PANEL) * len(measure.PERIODS),
    # A complete run four days later, under the lock files.
    "run-44904663719-panel-rows.json": 2 * len(measure.PANEL) * len(measure.PERIODS),
}


@pytest.mark.parametrize("name", sorted(EARLIER))
def test_an_earlier_run_gave_the_same_rows(name):
    """Every row an earlier run measured equals this run's exactly, under
    code that has changed since. If a later run differs in a last digit, this
    fails, and the README's claim of equal digits has to change with it."""
    earlier = load("earlier", name)
    assert earlier["workflow_run"] != load("provenance.json")["workflow_run"]
    definitions = {metric_id: (variable, kind) for metric_id, variable, kind, _ in measure.PANEL}
    compared = 0
    for run in RUNS:
        now = {(row["period"], row["id"]): row["value"] for row in panel(run)}
        for row in earlier["rows"][run]:
            assert (row["variable"], row["kind"]) == definitions[row["id"]], row
            assert now[(row["period"], row["id"])] == row["value"], row
            compared += 1
    assert compared == EARLIER[name]
