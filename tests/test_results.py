"""Invariants of the committed results.

- The comparison is a pure function of the two runs' files: regenerating it
  gives the committed files byte for byte.
- The results were measured by the measurement code in this tree: the hashes
  recorded with them equal the files' hashes. A change to that code fails
  here until someone measures again.
- Both runs read the same dataset bytes, and each ran the releases its
  environment file pins.
- Both runs measured the same rows, with no row in error.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
sys.path.insert(0, str(ROOT / "scripts"))

from provenance import code_hashes  # noqa: E402

RUNS = ("pinned", "head")


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
    recorded = load("provenance.json")["measurement_code_sha256"]
    assert recorded == code_hashes(), "measurement code changed since these results: run Measure again"


def pins(run: str) -> dict[str, str]:
    out = {}
    for line in (ROOT / "envs" / f"{run}.txt").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.strip().split("==")
            out[name] = version
    return out


@pytest.mark.parametrize("run", RUNS)
def test_each_run_used_its_pinned_releases(run):
    installed = load(run, "environment.json")["packages"]
    for name, version in pins(run).items():
        assert installed[name] == version, name


def test_both_runs_read_the_same_dataset_bytes():
    datasets = [load(run, "environment.json")["dataset"] for run in RUNS]
    assert datasets[0]["sha256"] == datasets[1]["sha256"]
    assert datasets[0]["bytes"] == datasets[1]["bytes"]
    for run in RUNS:
        environment = load(run, "environment.json")
        assert environment["release_default_dataset_sha256"] == environment["dataset"]["sha256"]


def test_both_runs_measured_the_same_rows_without_error():
    keys = []
    for run in RUNS:
        rows = [row for path in sorted((RESULTS / run).glob("panel-*.json")) for row in json.loads(path.read_text())["rows"]]
        assert rows
        assert all(row["error"] is None and row["value"] is not None for row in rows)
        keys.append(sorted((row["period"], row["id"]) for row in rows))
    assert keys[0] == keys[1]
    assert len(set(keys[0])) == len(keys[0])


@pytest.mark.parametrize("run", RUNS)
def test_contract_classes_partition_the_stored_columns(run):
    contract = load(run, "contract.json")
    assert sum(contract["counts"].values()) == contract["stored_columns"]


@pytest.mark.parametrize("run", RUNS)
def test_stored_draw_covers_every_person(run):
    wic = {**load(run, "wic-loaded.json"), **load(run, "wic-stored.json")}
    assert wic["person_ids_matched"] == wic["person_ids_in_simulation"] == wic["stored_draw_rows"]
    assert 0 <= wic["take_up_share_with_stored_draw"] <= wic["take_up_share_as_loaded"] <= 1
    assert wic["wic_with_stored_draw"] <= wic["wic_as_loaded"]
