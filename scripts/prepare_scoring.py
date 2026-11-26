"""Lay out the files Microcosm's scorer reads for the default US dataset.

``tools/build_us_compatibility_recertification.py score`` in
PolicyEngine/microcosm scores an H5 under the installed engine against the
targets in a release's ``calibration_diagnostics.json``. It reads three things:

- ``<release>/compatibility_recertification.json``, for the H5's file name and
  hash;
- ``<release>/calibration_diagnostics.json``, for the target rows and the SPM
  selection to score under;
- ``<artifacts>/<the H5>``.

The diagnostics hold the target rows and the estimates the build calibrated
to them. The default dataset carries that file unchanged from its parent
build, which the release's ``parent_release_manifest.json`` names; this
script checks that the manifest lists the same file and records which build
and engine made those estimates.

The default dataset is a published release with no recertification report, and
its diagnostics record no SPM selection (``build.post_export_scoring`` is
null). This script writes a report that holds only the dataset's identity, and
a copy of the published diagnostics with one value added: the SPM selection
Microcosm's own scoring of its October 2026 build used, which the
``policyengine`` bundle also uses. Nothing else in the diagnostics changes,
and :func:`restore` proves it.

The release folder is pinned here, with the hashes of the files read from it.
Before any download, ``--check-measured`` checks that the committed
measurement (``results/pinned`` and ``results/head``) read the same dataset
(:func:`measured_dataset_failures`) and prints the folder's URL, which the
Score workflow downloads from. A measurement on another dataset stops the run
there, before it scores this folder's file.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import file_hashes, run_identity  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The files that decide what a scoring run produces. Each job writes their
# hashes into its output, and a test fails while the committed scores carry
# other hashes than the tree.
SCORING_CODE = (
    "scripts/fetch_wheels.py",
    "scripts/prepare_scoring.py",
    "scripts/critical_targets.py",
    "scripts/rules.py",
    "envs/score.constraints.txt",
    ".github/workflows/score.yml",
)
# The scoring jobs of the Score workflow, by the name each uploads under.
SCORING_JOBS = ("pinned", "head", "head-without-newly-read")

DATASET_FILE = "populace_us_2024.h5"
DATASET_SHA256 = "6496cc4393d4d3c6574f76eca231de5898c803b9067645591fd5c4d3e65aee84"
REPOSITORY = "policyengine/populace-us"
REVISION = "0ff35303e4e5c10bf1cfb2da8f65c83d7dfa9ab3"
RELEASE_FOLDER = "releases/microcosm-us-2024-national/populace-us-2024-spm-20260915"
PUBLISHED_DIAGNOSTICS_SHA256 = "870449b44e86b13b25bcea1a57f0e7af37f4d4db18be815eea3acdf9fe6eb40e"
PARENT_MANIFEST_SHA256 = "dd949ba3c4c7a56aff8442c6db5a031d2c84c3da59f5d14832f468c358604506"

# The selection in ``scores.*.scoring.spm`` of the compatibility_drift.json
# Microcosm published with populace-us-2024-b5db384-recert-pe-us-2.90.4, and
# the ``geography_kind`` of the policyengine 6.20.2 bundle's SPM measurement.
SPM_SELECTION = {"geography_kind": "county"}


def folder_url() -> str:
    """The release folder the scoring jobs download from."""
    return f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{RELEASE_FOLDER}"


def url(filename: str) -> str:
    return f"{folder_url()}/{filename}"


def measured_dataset_failures(environments: dict[str, dict]) -> list[str]:
    """How the datasets the measured runs read differ from the one scored here.

    ``environments`` maps each run's name to its ``environment.json``. Each
    run must have read this script's file, by hash, from this repository, at
    the revision tag that names this script's release folder. The tag is the
    folder's last part, so a measurement on another release refuses scoring
    here rather than letting the jobs score this folder's file. Empty when
    every run matches.
    """
    found = []
    for run, environment in sorted(environments.items()):
        dataset = environment.get("dataset") or {}
        if dataset.get("sha256") != DATASET_SHA256:
            found.append(f"the {run} measurement read sha256 {dataset.get('sha256')}, not {DATASET_SHA256}")
        if dataset.get("file") != DATASET_FILE:
            found.append(f"the {run} measurement read the file {dataset.get('file')}, not {DATASET_FILE}")
        if dataset.get("repo") != REPOSITORY:
            found.append(f"the {run} measurement read the repository {dataset.get('repo')}, not {REPOSITORY}")
        revision = dataset.get("revision")
        if not isinstance(revision, str) or not revision or not RELEASE_FOLDER.endswith(f"/{revision}"):
            found.append(f"the {run} measurement read the revision {revision}, not the release folder {RELEASE_FOLDER}")
    return found


def check_measured(root: Path = ROOT) -> str:
    """The release folder's URL, once the committed measurement is shown to
    have read this script's dataset; otherwise ``ValueError``."""
    environments = {
        run: json.loads((root / "results" / run / "environment.json").read_text()) for run in ("pinned", "head")
    }
    found = measured_dataset_failures(environments)
    if found:
        raise ValueError("; ".join(found))
    return folder_url()


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


def estimates_from(parent: dict, diagnostics_sha256: str) -> dict:
    """The build whose estimates the diagnostics hold, from the parent's
    release manifest, which must list the same diagnostics file."""
    listed = parent["artifacts"]["calibration_diagnostics"]["sha256"]
    if listed != diagnostics_sha256:
        raise ValueError(f"the parent build lists diagnostics {listed}, not {diagnostics_sha256}")
    build = parent["build"]
    return {
        "build_id": build["build_id"],
        "built_at": build["built_at"],
        "policyengine-us": build["built_with_model_package"]["version"],
        "policyengine-core": build["built_with_core_package"]["version"],
        "manifest": {"sha256": PARENT_MANIFEST_SHA256, "url": url("parent_release_manifest.json")},
    }


def stamp() -> dict:
    """Which workflow run this process belongs to, and the code it ran."""
    return {"run": run_identity(os.environ), "code_sha256": file_hashes(ROOT, SCORING_CODE)}


def household_count(h5: Path) -> int:
    import h5py

    with h5py.File(h5, "r") as handle:
        return int(handle["household"]["table"].shape[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-measured",
        action="store_true",
        help=(
            "check that results/pinned and results/head read this script's dataset, and print the release "
            "folder's URL as folder_url=<url>"
        ),
    )
    parser.add_argument("--diagnostics", type=Path, help="the published calibration_diagnostics.json")
    parser.add_argument("--parent-manifest", type=Path, help="the published parent_release_manifest.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--h5", type=Path, help="the downloaded dataset; checked and counted when given")
    args = parser.parse_args(argv)
    if args.check_measured:
        try:
            print(f"folder_url={check_measured()}")
        except ValueError as exc:
            raise SystemExit(f"the committed measurement read another dataset than scoring would: {exc}")
        return 0
    given = {"--diagnostics": args.diagnostics, "--parent-manifest": args.parent_manifest, "--out": args.out}
    missing = [flag for flag, value in given.items() if value is None]
    if missing:
        parser.error(f"laying out the scorer's inputs needs {', '.join(missing)}")

    published_sha256 = sha256_of(args.diagnostics)
    if published_sha256 != PUBLISHED_DIAGNOSTICS_SHA256:
        raise SystemExit(f"calibration_diagnostics.json has sha256 {published_sha256}")
    published = json.loads(args.diagnostics.read_text())
    parent_sha256 = sha256_of(args.parent_manifest)
    if parent_sha256 != PARENT_MANIFEST_SHA256:
        raise SystemExit(f"parent_release_manifest.json has sha256 {parent_sha256}")
    try:
        estimates = estimates_from(json.loads(args.parent_manifest.read_text()), published_sha256)
    except ValueError as exc:
        raise SystemExit(str(exc))
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
        "estimates_from": estimates,
        "derived_diagnostics": {
            "sha256": sha256_of(derived_path),
            "added": {"build.post_export_scoring": {"spm": SPM_SELECTION}},
            "targets": len(published.get("targets") or ()),
        },
        **stamp(),
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
