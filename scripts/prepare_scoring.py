"""Lay out the files Microcosm's scorer reads for the default US dataset.

``tools/build_us_compatibility_recertification.py score`` in
PolicyEngine/microcosm scores an H5 under the installed engine against the
targets in a release's ``calibration_diagnostics.json``. It reads three things:

- ``<release>/compatibility_recertification.json``, for the H5's file name and
  hash;
- ``<release>/calibration_diagnostics.json``, for the target rows and the SPM
  selection to score under;
- ``<artifacts>/<the H5>``.

The default dataset is a published release with no recertification report, and
its diagnostics record no SPM selection (``build.post_export_scoring`` is
null). This script writes a report that holds only the dataset's identity, and
a copy of the published diagnostics with one value added: the SPM selection
Microcosm's own scoring of its October 2026 build used, which the
``policyengine`` bundle also uses. Nothing else in the diagnostics changes,
and :func:`restore` proves it.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

DATASET_FILE = "populace_us_2024.h5"
DATASET_SHA256 = "6496cc4393d4d3c6574f76eca231de5898c803b9067645591fd5c4d3e65aee84"
REPOSITORY = "policyengine/populace-us"
REVISION = "0ff35303e4e5c10bf1cfb2da8f65c83d7dfa9ab3"
RELEASE_FOLDER = "releases/microcosm-us-2024-national/populace-us-2024-spm-20260915"
PUBLISHED_DIAGNOSTICS_SHA256 = "870449b44e86b13b25bcea1a57f0e7af37f4d4db18be815eea3acdf9fe6eb40e"

# The selection in ``scores.*.scoring.spm`` of the compatibility_drift.json
# Microcosm published with populace-us-2024-b5db384-recert-pe-us-2.90.4, and
# the ``geography_kind`` of the policyengine 6.20.2 bundle's SPM measurement.
SPM_SELECTION = {"geography_kind": "county"}


def url(filename: str) -> str:
    return f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{RELEASE_FOLDER}/{filename}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive(diagnostics: dict) -> dict:
    """The published diagnostics with the SPM selection added, and nothing else."""
    build = diagnostics.get("build")
    if not isinstance(build, dict):
        raise ValueError("the diagnostics have no build record")
    if build.get("post_export_scoring") is not None:
        raise ValueError("the diagnostics already record a post-export scoring selection")
    derived = copy.deepcopy(diagnostics)
    derived["build"]["post_export_scoring"] = {"spm": dict(SPM_SELECTION)}
    return derived


def restore(derived: dict) -> dict:
    """Undo :func:`derive`: what the published file held."""
    restored = copy.deepcopy(derived)
    restored["build"]["post_export_scoring"] = None
    return restored


def report() -> dict:
    """The dataset's identity, in the one place the scorer reads it from."""
    return {
        "dataset": {"artifact": "populace_us_2024", "filename": DATASET_FILE, "sha256": DATASET_SHA256},
        "purpose": (
            "Written by PolicyEngine/us-model-version-drift so Microcosm's scorer can find the "
            "default dataset. It certifies nothing."
        ),
    }


def household_count(h5: Path) -> int:
    import h5py

    with h5py.File(h5, "r") as handle:
        return int(handle["household"]["table"].shape[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", required=True, type=Path, help="the published calibration_diagnostics.json")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--h5", type=Path, help="the downloaded dataset; checked and counted when given")
    args = parser.parse_args()

    published_sha256 = sha256_of(args.diagnostics)
    if published_sha256 != PUBLISHED_DIAGNOSTICS_SHA256:
        raise SystemExit(f"calibration_diagnostics.json has sha256 {published_sha256}")
    published = json.loads(args.diagnostics.read_text())
    if "post_export_scoring" in published["build"] and published["build"]["post_export_scoring"] is not None:
        raise SystemExit("the published diagnostics already record a selection")
    derived = derive(published)
    comparable = dict(published, build=dict(published["build"], post_export_scoring=None))
    if restore(derived) != comparable:
        raise SystemExit("the derived diagnostics differ from the published ones beyond the added selection")

    release = args.out / "release"
    release.mkdir(parents=True, exist_ok=True)
    (release / "compatibility_recertification.json").write_text(json.dumps(report(), indent=2, sort_keys=True) + "\n")
    derived_path = release / "calibration_diagnostics.json"
    derived_path.write_text(json.dumps(derived))

    inputs = {
        "dataset": {"file": DATASET_FILE, "sha256": DATASET_SHA256, "url": url(DATASET_FILE)},
        "published_diagnostics": {"sha256": published_sha256, "url": url("calibration_diagnostics.json")},
        "derived_diagnostics": {
            "sha256": sha256_of(derived_path),
            "added": {"build.post_export_scoring": {"spm": SPM_SELECTION}},
            "targets": len(published.get("targets") or ()),
        },
    }
    if args.h5 is not None:
        actual = sha256_of(args.h5)
        if actual != DATASET_SHA256:
            raise SystemExit(f"{args.h5} has sha256 {actual}")
        inputs["dataset"]["households"] = household_count(args.h5)
    (args.out / "scoring_inputs.json").write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n")
    print(json.dumps(inputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
