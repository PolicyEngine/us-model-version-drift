"""Measure one installed policyengine-us release on the default US dataset.

Run it inside an environment that holds exactly one policyengine-us release.
It writes four JSON files into ``--out``:

- ``environment.json``: package versions, interpreter, and the dataset's
  identity (the file's SHA-256 as downloaded here).
- ``contract.json``: every column the dataset stores, classified against the
  variables this release defines.
- ``panel.json``: weighted totals for a fixed panel of programmes.
- ``wic.json``: WIC as the release loads the dataset, and again with the
  dataset's stored take-up draw applied to the release's take-up input.

Every figure comes from ``policyengine_us.Microsimulation()`` on the release's
own default dataset. Nothing is imputed or approximated here.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata as metadata
import json
import logging
import platform
import sys
import time
import traceback
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import classify_columns  # noqa: E402

DATASET_REPO = "policyengine/populace-us"
DATASET_FILE = "populace_us_2024.h5"
DATASET_REVISION = "populace-us-2024-spm-20260915"
DATASET_SHA256 = "6496cc4393d4d3c6574f76eca231de5898c803b9067645591fd5c4d3e65aee84"
ENTITY_TABLES = ("person", "household", "tax_unit", "spm_unit", "family", "marital_unit")
PERIODS = (2024, 2026)

# (id, variable, kind). ``sum`` is a weighted total; ``count_positive`` is the
# weighted number of units with a positive value. The first block follows the
# headline rows of Microcosm's compatibility scorer
# (microcosm.data.compatibility_recertification.HEADLINE_METRICS); the second
# adds programmes it does not list.
PANEL = (
    ("income_tax_net", "income_tax", "sum"),
    ("ctc_total", "ctc", "sum"),
    ("eitc_total", "eitc", "sum"),
    ("social_security_total", "social_security", "sum"),
    ("snap_total", "snap", "sum"),
    ("snap_units", "snap", "count_positive"),
    ("ssi_total", "ssi", "sum"),
    ("medicaid_enrollment", "medicaid_enrolled", "sum"),
    ("medicaid_total", "medicaid", "sum"),
    ("state_income_tax_total", "state_income_tax", "sum"),
    ("medicare_part_d_irmaa_total", "income_adjusted_part_d_premium_surcharge", "sum"),
    ("medicare_cost_total", "medicare_cost", "sum"),
    ("adjusted_gross_income_total", "adjusted_gross_income", "sum"),
    ("wic_total", "wic", "sum"),
    ("tanf_total", "tanf", "sum"),
    ("refundable_ctc_total", "refundable_ctc", "sum"),
    ("employee_payroll_tax_total", "employee_payroll_tax", "sum"),
    ("premium_tax_credit_total", "premium_tax_credit", "sum"),
    ("household_net_income_total", "household_net_income", "sum"),
    ("people_in_spm_poverty", "person_in_poverty", "sum"),
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
    """Each variable the release defines, mapped to whether it is computed."""
    out: dict[str, bool] = {}
    for name, variable in sim.tax_benefit_system.variables.items():
        has_formula = len(getattr(variable, "formulas", {}) or {}) > 0
        has_adds = bool(getattr(variable, "adds", None)) or bool(getattr(variable, "subtracts", None))
        out[name] = has_formula or has_adds
    return out


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


def measure_panel(sim) -> dict:
    defined = set(sim.tax_benefit_system.variables)
    rows = []
    for period in PERIODS:
        for metric_id, variable, kind in PANEL:
            row = {"period": period, "id": metric_id, "variable": variable, "kind": kind}
            started = time.time()
            if variable not in defined:
                row.update(value=None, error="variable not defined in this release")
            else:
                try:
                    row.update(value=weighted(sim, variable, period, kind), error=None)
                except Exception as exc:  # record, keep measuring
                    row.update(value=None, error=f"{type(exc).__name__}: {str(exc)[:400]}")
            row["seconds"] = round(time.time() - started, 1)
            print(json.dumps(row), flush=True)
            rows.append(row)
    return {"periods": list(PERIODS), "rows": rows}


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
        out["take_up_share_as_loaded"] = weighted(sim, "takes_up_wic_if_eligible", f"{period}-01", "mean")
    with pd.HDFStore(str(dataset), "r") as store:
        person = store.select("person", columns=["person_id", "would_claim_wic"])
    out["stored_draw_rows"] = int(len(person))
    out["stored_draw_share_true_unweighted"] = float(person["would_claim_wic"].mean())
    return out


def measure_wic_with_stored_draw(dataset: Path) -> dict:
    """WIC with the dataset's stored take-up draw applied.

    The dataset stores each person's WIC take-up draw as ``would_claim_wic``.
    A release that does not define that variable cannot read it. This applies
    the stored draw to ``takes_up_wic_if_eligible`` for each month of 2024 on
    a fresh simulation, matching rows by ``person_id``.
    """
    import numpy as np
    import pandas as pd

    period = 2024
    months = [f"{period}-{m:02d}" for m in range(1, 13)]
    out: dict = {}
    fresh = build_simulation()
    if "takes_up_wic_if_eligible" not in fresh.tax_benefit_system.variables:
        out["wic_with_stored_draw"] = None
        out["note"] = "this release has no takes_up_wic_if_eligible input"
        return out
    with pd.HDFStore(str(dataset), "r") as store:
        person = store.select("person", columns=["person_id", "would_claim_wic"])
    ids = np.asarray(fresh.calculate("person_id", period).values).astype("int64")
    stored = person.drop_duplicates("person_id").set_index("person_id")["would_claim_wic"]
    aligned = stored.reindex(ids)
    out["person_ids_matched"] = int(aligned.notna().sum())
    out["person_ids_in_simulation"] = int(len(ids))
    if aligned.isna().any():
        out["wic_with_stored_draw"] = None
        out["note"] = "stored person_id values do not cover the simulation's people"
        return out
    values = aligned.to_numpy(dtype=bool)
    for month in months:
        fresh.set_input("takes_up_wic_if_eligible", month, values)
    out["take_up_share_with_stored_draw"] = weighted(fresh, "takes_up_wic_if_eligible", months[0], "mean")
    out["wic_with_stored_draw"] = weighted(fresh, "wic", period, "sum")
    return out


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name of this environment, for example pinned or head")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    started = time.time()
    dataset = fetch_dataset()
    columns = stored_columns(dataset)

    import policyengine_us.system as system

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
        "release_default_dataset": getattr(system, "DEFAULT_DATASET", None),
        "release_default_dataset_sha256": getattr(system, "DEFAULT_DATASET_SHA256", None),
    }
    write(args.out / "environment.json", environment)
    print(json.dumps(environment, indent=2), flush=True)

    captured = Captured()
    sim = build_simulation(captured)
    write(args.out / "contract.json", measure_contract(sim, columns, captured.messages))
    print("contract written", flush=True)

    write(args.out / "panel.json", measure_panel(sim))
    print("panel written", flush=True)

    try:
        wic = measure_wic_as_loaded(sim, dataset)
    except Exception as exc:
        wic = {"error": f"{type(exc).__name__}: {str(exc)[:600]}", "traceback": traceback.format_exc()[-2000:]}
    del sim
    gc.collect()
    try:
        wic.update(measure_wic_with_stored_draw(dataset))
    except Exception as exc:
        wic["stored_draw_error"] = f"{type(exc).__name__}: {str(exc)[:600]}"
        wic["stored_draw_traceback"] = traceback.format_exc()[-2000:]
    write(args.out / "wic.json", wic)
    print(json.dumps(wic, indent=2), flush=True)

    environment["seconds"] = round(time.time() - started, 1)
    write(args.out / "environment.json", environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
