"""Measure one installed policyengine-us release on the default US dataset.

Run it inside an environment that holds exactly one policyengine-us release.
Each call measures one part, so memory stays bounded (a first run that held
two periods in one process exhausted a 16 GB runner). The parts write into
``--out``, and a part refuses to replace a file that is already there, so a
folder never mixes two runs:

- ``contract``: ``environment.json`` (package versions, interpreter, the
  dataset's identity, the workflow run and the hashes of the measurement
  code) and ``contract.json`` (every column the dataset stores,
  classified by how this release defines its name).
- ``panel``: ``panel-<period>.json``, weighted totals and counts for a fixed
  panel of programmes in one year.
- ``wic_loaded``: ``wic-loaded.json``, WIC as the release loads the dataset.
- ``wic_stored``: ``wic-stored.json``, WIC with the dataset's stored take-up
  draw applied to the release's take-up input.

Every figure comes from ``policyengine_us.Microsimulation()`` on the release's
own default dataset. Nothing is imputed or approximated here.

A part exits with an error when it cannot measure everything it should: a
panel row that fails, a stored draw that does not line up with the
simulation's people, or a release whose default dataset is not the measured
file.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import logging
import math
import os
import platform
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import classify_columns, file_hashes, run_identity  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The files that decide what a run measures. Each run writes their hashes into
# ``environment.json``, and a test fails while the committed results carry
# other hashes than the tree. ``compare.py`` is absent on purpose: the
# comparison is a pure function of the two runs' files, and a test
# regenerates it.
MEASUREMENT_CODE = (
    "scripts/measure.py",
    "scripts/rules.py",
    "envs/pinned.txt",
    "envs/pinned.lock.txt",
    "envs/head.txt",
    "envs/head.lock.txt",
    ".github/workflows/measure.yml",
)

DATASET_REPO = "policyengine/populace-us"
DATASET_FILE = "populace_us_2024.h5"
DATASET_REVISION = "populace-us-2024-spm-20260915"
DATASET_SHA256 = "6496cc4393d4d3c6574f76eca231de5898c803b9067645591fd5c4d3e65aee84"
ENTITY_TABLES = ("person", "household", "tax_unit", "spm_unit", "family", "marital_unit")
PERIODS = (2024, 2026)

# (id, variable, kind, unit). ``sum`` is a weighted total; ``count_positive``
# is the weighted number of units with a positive value. The unit says what a
# row counts: dollars, or one of three counts. ``medicaid_enrollment`` and
# ``people_in_spm_poverty`` sum a true/false variable over people, so they
# count people. The first block follows the headline rows of Microcosm's
# compatibility scorer
# (microcosm.data.compatibility_recertification.HEADLINE_METRICS); the second
# adds programmes it does not list.
USD, SPM_UNITS, PEOPLE = "usd", "spm_units", "people"
UNITS = (USD, SPM_UNITS, PEOPLE)
PANEL = (
    ("income_tax_net", "income_tax", "sum", USD),
    ("ctc_total", "ctc", "sum", USD),
    ("eitc_total", "eitc", "sum", USD),
    ("social_security_total", "social_security", "sum", USD),
    ("snap_total", "snap", "sum", USD),
    ("snap_units", "snap", "count_positive", SPM_UNITS),
    ("ssi_total", "ssi", "sum", USD),
    ("medicaid_enrollment", "medicaid_enrolled", "sum", PEOPLE),
    ("medicaid_total", "medicaid", "sum", USD),
    ("state_income_tax_total", "state_income_tax", "sum", USD),
    ("medicare_part_d_irmaa_total", "income_adjusted_part_d_premium_surcharge", "sum", USD),
    ("medicare_cost_total", "medicare_cost", "sum", USD),
    ("adjusted_gross_income_total", "adjusted_gross_income", "sum", USD),
    ("wic_total", "wic", "sum", USD),
    ("tanf_total", "tanf", "sum", USD),
    ("refundable_ctc_total", "refundable_ctc", "sum", USD),
    ("employee_payroll_tax_total", "employee_payroll_tax", "sum", USD),
    ("premium_tax_credit_total", "premium_tax_credit", "sum", USD),
    ("household_net_income_total", "household_net_income", "sum", USD),
    ("people_in_spm_poverty", "person_in_poverty", "sum", PEOPLE),
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str | None]:
    names = (
        "policyengine-us",
        "policyengine-core",
        "spm-calculator",
        "microdf-python",
        "numpy",
        "pandas",
        "tables",
        "h5py",
        "huggingface-hub",
    )
    out: dict[str, str | None] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def fetch_dataset() -> Path:
    from huggingface_hub import hf_hub_download

    path = Path(
        hf_hub_download(
            repo_id=DATASET_REPO,
            filename=DATASET_FILE,
            repo_type="dataset",
            revision=DATASET_REVISION,
        )
    )
    actual = sha256_of(path)
    if actual != DATASET_SHA256:
        raise SystemExit(
            f"{DATASET_FILE}@{DATASET_REVISION} has sha256 {actual}, expected {DATASET_SHA256}"
        )
    return path


def release_default_dataset() -> dict[str, str | None]:
    """The default dataset this release names, and the hash it certifies.

    Both measured releases check the file ``Microsimulation()`` loads against
    ``DEFAULT_DATASET_SHA256`` and raise on a mismatch. When that hash equals
    the measured file's, the simulation read the bytes this script hashed.
    """
    import policyengine_us.system as system

    return {
        "name": getattr(system, "DEFAULT_DATASET", None),
        "sha256": getattr(system, "DEFAULT_DATASET_SHA256", None),
    }


def require_measured_default() -> dict[str, str | None]:
    default = release_default_dataset()
    if default["sha256"] != DATASET_SHA256:
        raise SystemExit(
            f"this release's default dataset {default['name']} is certified as sha256 "
            f"{default['sha256']}, not the measured file's {DATASET_SHA256}"
        )
    return default


def stored_columns(path: Path) -> dict[str, list[str]]:
    import pandas as pd

    out: dict[str, list[str]] = {}
    with pd.HDFStore(str(path), "r") as store:
        for table in ENTITY_TABLES:
            out[table] = [str(c) for c in store.select(table, stop=1).columns]
    return out


class Captured(logging.Handler):
    """Collect what the loader says while it builds the simulation."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(f"{record.name}: {record.getMessage()}")
        except Exception:  # pragma: no cover - never fail a run on a log line
            pass


def build_simulation(captured: Captured | None = None):
    from policyengine_us import Microsimulation

    handler = captured
    if handler is not None:
        logging.getLogger().addHandler(handler)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sim = Microsimulation()
        if handler is not None:
            handler.messages.extend(f"warning: {w.category.__name__}: {w.message}" for w in caught)
    finally:
        if handler is not None:
            logging.getLogger().removeHandler(handler)
    return sim


def variable_table(sim) -> dict[str, bool]:
    """Each variable the release defines, mapped to whether it is computed.

    policyengine-core decides: a variable is computed when its own
    ``is_input_variable()`` is false.
    """
    return {
        name: not variable.is_input_variable()
        for name, variable in sim.tax_benefit_system.variables.items()
    }


def declared_sets() -> dict[str, list[str] | None]:
    """The release's own declarations about dataset columns, where it has them."""
    out: dict[str, list[str] | None] = {
        "DATASET_SOURCE_INPUTS": None,
        "REJECTED_DATASET_INPUTS": None,
    }
    try:
        import policyengine_us.spm as spm
    except Exception:
        return out
    for name in out:
        value = getattr(spm, name, None)
        if value is not None:
            out[name] = sorted(str(v) for v in value)
    return out


def measure_contract(sim, columns: dict[str, list[str]], messages: list[str]) -> dict:
    variables = variable_table(sim)
    by_table = {table: classify_columns(cols, variables) for table, cols in columns.items()}
    every = sorted({c for cols in columns.values() for c in cols})
    overall = classify_columns(every, variables)
    declared = declared_sets()
    required = declared["DATASET_SOURCE_INPUTS"]
    rejected = declared["REJECTED_DATASET_INPUTS"]
    unknown = set(overall["not_a_variable"])
    return {
        "stored_columns": len(every),
        "variables_defined": len(variables),
        "counts": {name: len(cols) for name, cols in overall.items()},
        "not_a_variable": overall["not_a_variable"],
        "computed_variable": overall["computed_variable"],
        "classes": overall,
        # How the release defines each stored column's name: "input",
        # "computed", or null when it defines no such variable.
        "definitions": {
            column: (None if column not in variables else "computed" if variables[column] else "input")
            for column in every
        },
        "tables": {table: sorted(cols) for table, cols in columns.items()},
        "by_table": by_table,
        "declared": declared,
        "required_source_inputs_missing": (
            None if required is None else sorted(set(required) - set(every))
        ),
        "rejected_inputs_stored": (
            None if rejected is None else sorted(set(rejected) & set(every))
        ),
        "loader_messages_total": len(messages),
        "loader_messages_naming_unknown_columns": [
            m[:600] for m in messages if any(name in m for name in unknown)
        ][:40],
        "loader_messages_sample": [m[:300] for m in messages[:20]],
    }


def weighted(sim, variable: str, period, kind: str) -> float:
    series = sim.calculate(variable, period)
    if kind == "sum":
        return float(series.sum())
    if kind == "count_positive":
        return float((series > 0).sum())
    if kind == "mean":
        return float(series.mean())
    raise ValueError(kind)


def measure_panel(sim, period: int) -> dict:
    defined = set(sim.tax_benefit_system.variables)
    rows = []
    for metric_id, variable, kind, unit in PANEL:
        row = {"period": period, "id": metric_id, "variable": variable, "kind": kind, "unit": unit}
        started = time.time()
        if variable not in defined:
            row.update(value=None, error="variable not defined in this release")
        else:
            try:
                value = weighted(sim, variable, period, kind)
                if math.isfinite(value):
                    row.update(value=value, error=None)
                else:
                    row.update(value=None, error=f"not a finite number: {value}")
            except Exception as exc:  # record every row, then fail the part
                row.update(value=None, error=f"{type(exc).__name__}: {str(exc)[:400]}")
        row["seconds"] = round(time.time() - started, 1)
        print(json.dumps(row), flush=True)
        rows.append(row)
    return {"period": period, "rows": rows}


def panel_errors(payload: dict) -> list[str]:
    """The rows of one measured panel year that hold no value."""
    return [f"{row['id']}: {row['error']}" for row in payload["rows"] if row["error"] is not None]


def measure_wic_as_loaded(sim, dataset: Path) -> dict:
    """WIC exactly as this release loads the dataset."""
    import pandas as pd

    period = 2024
    defined = set(sim.tax_benefit_system.variables)
    out: dict = {
        "period": period,
        "would_claim_wic_is_a_variable": "would_claim_wic" in defined,
        "takes_up_wic_if_eligible_is_a_variable": "takes_up_wic_if_eligible" in defined,
    }
    out["wic_as_loaded"] = weighted(sim, "wic", period, "sum")
    if "takes_up_wic_if_eligible" in defined:
        # The input is monthly. This is its January value, averaged over
        # every person with person weights.
        out["take_up_share_as_loaded"] = weighted(sim, "takes_up_wic_if_eligible", f"{period}-01", "mean")
    with pd.HDFStore(str(dataset), "r") as store:
        person = store.select("person", columns=["person_id", "would_claim_wic"])
    out["stored_draw_rows"] = int(len(person))
    out["stored_draw_share_true_unweighted"] = float(person["would_claim_wic"].mean())
    return out


def align_by_id(simulation_ids, stored_ids, stored_values):
    """Stored values in the simulation's row order, matched on a unique id.

    Raises ``ValueError`` unless each side's ids are unique and the two sides
    hold the same ids: a repeated or missing id would make the match
    ambiguous.
    """
    import numpy as np

    simulation_ids = np.asarray(simulation_ids).astype("int64")
    stored_ids = np.asarray(stored_ids).astype("int64")
    stored_values = np.asarray(stored_values)
    if len(stored_ids) != len(stored_values):
        raise ValueError("stored ids and stored values differ in length")
    if len(np.unique(stored_ids)) != len(stored_ids):
        raise ValueError("stored ids repeat")
    if len(np.unique(simulation_ids)) != len(simulation_ids):
        raise ValueError("the simulation's ids repeat")
    order = np.argsort(stored_ids, kind="stable")
    position = np.searchsorted(stored_ids[order], simulation_ids)
    position = np.clip(position, 0, max(len(stored_ids) - 1, 0))
    if len(stored_ids) != len(simulation_ids) or not np.array_equal(stored_ids[order][position], simulation_ids):
        raise ValueError("the stored ids and the simulation's ids are not the same set")
    return stored_values[order][position]


def measure_wic_with_stored_draw(dataset: Path) -> dict:
    """WIC with the dataset's stored take-up draw applied.

    The dataset stores each person's WIC take-up draw as ``would_claim_wic``.
    A release that does not define that variable cannot read it. This applies
    the stored draw to ``takes_up_wic_if_eligible`` for each month of 2024 on
    a fresh simulation, before any benefit is calculated. It matches people on
    ``person_id``, which must be unique on both sides and cover the same
    people.
    """
    import pandas as pd

    period = 2024
    months = [f"{period}-{m:02d}" for m in range(1, 13)]
    fresh = build_simulation()
    if "takes_up_wic_if_eligible" not in fresh.tax_benefit_system.variables:
        raise SystemExit("this release has no takes_up_wic_if_eligible input")
    with pd.HDFStore(str(dataset), "r") as store:
        person = store.select("person", columns=["person_id", "would_claim_wic"])
    ids = fresh.calculate("person_id", period).values
    try:
        values = align_by_id(ids, person["person_id"].to_numpy(), person["would_claim_wic"].to_numpy()).astype(bool)
    except ValueError as exc:
        raise SystemExit(f"cannot apply the stored draw: {exc}")
    out: dict = {
        "person_ids_in_simulation": int(len(ids)),
        "person_ids_stored": int(len(person)),
        "person_ids_unique_and_identical_sets": True,
        "stored_draw_true_rows_applied": int(values.sum()),
    }
    for month in months:
        fresh.set_input("takes_up_wic_if_eligible", month, values)
    # The same measure as ``take_up_share_as_loaded``: the January input,
    # averaged over every person with person weights.
    out["take_up_share_with_stored_draw"] = weighted(fresh, "takes_up_wic_if_eligible", months[0], "mean")
    out["wic_with_stored_draw"] = weighted(fresh, "wic", period, "sum")
    return out


def write(path: Path, payload: dict) -> None:
    """Write one result file. Fails if it exists: no run reuses another's file."""
    with path.open("x") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


PARTS = ("contract", "panel", "wic_loaded", "wic_stored")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name of this environment, for example pinned or head")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--part",
        required=True,
        choices=PARTS,
        help="what to measure in this process; one part per process keeps memory bounded",
    )
    parser.add_argument("--period", type=int, choices=PERIODS, help="the year, for --part panel")
    args = parser.parse_args()
    if args.part == "panel" and args.period is None:
        parser.error("--part panel needs --period")
    args.out.mkdir(parents=True, exist_ok=True)

    started = time.time()
    dataset = fetch_dataset()
    default = require_measured_default()
    failures: list[str] = []

    if args.part == "contract":
        environment = {
            "label": args.label,
            "packages": package_versions(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dataset": {
                "repo": DATASET_REPO,
                "file": DATASET_FILE,
                "revision": DATASET_REVISION,
                "sha256": DATASET_SHA256,
                "bytes": dataset.stat().st_size,
            },
            "release_default_dataset": default["name"],
            "release_default_dataset_sha256": default["sha256"],
            # Which run made these files, and with what code: the files
            # themselves say so, so nobody has to remember where they came from.
            "run": run_identity(os.environ),
            "code_sha256": file_hashes(ROOT, MEASUREMENT_CODE),
        }
        write(args.out / "environment.json", environment)
        print(json.dumps(environment, indent=2), flush=True)
        captured = Captured()
        sim = build_simulation(captured)
        write(args.out / "contract.json", measure_contract(sim, stored_columns(dataset), captured.messages))
    elif args.part == "panel":
        payload = measure_panel(build_simulation(), args.period)
        payload["seconds"] = round(time.time() - started, 1)
        write(args.out / f"panel-{args.period}.json", payload)
        failures = panel_errors(payload)
    elif args.part == "wic_loaded":
        payload = measure_wic_as_loaded(build_simulation(), dataset)
        write(args.out / "wic-loaded.json", payload)
        print(json.dumps(payload, indent=2), flush=True)
    else:
        payload = measure_wic_with_stored_draw(dataset)
        write(args.out / "wic-stored.json", payload)
        print(json.dumps(payload, indent=2), flush=True)
    print(f"{args.part} done in {round(time.time() - started, 1)} s", flush=True)
    if failures:
        print("rows without a value:\n  " + "\n  ".join(failures), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
