"""Download the three engine wheels one measured environment ran.

Microcosm's scorer proves its runtime against the wheels the environment was
installed from, so scoring installs from these files. The versions come from
the measured run's ``environment.json``, which ties the scores to the releases
the panel measured.

Standard library only: it runs before any environment exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

# The runtime Microcosm's scorer authenticates, by distribution name.
PACKAGES = ("policyengine-us", "policyengine-core", "spm-calculator")


def pins(environment: dict) -> dict[str, str]:
    """The exact version of each engine package a measured run installed."""
    installed = environment["packages"]
    missing = [name for name in PACKAGES if not installed.get(name)]
    if missing:
        raise ValueError(f"the measured environment records no version for {missing}")
    return {name: installed[name] for name in PACKAGES}


def wheel_file(name: str, version: str) -> dict:
    """PyPI's record of the one wheel a release publishes."""
    with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
        payload = json.load(response)
    wheels = [item for item in payload["urls"] if item["packagetype"] == "bdist_wheel"]
    if len(wheels) != 1:
        raise ValueError(f"{name} {version} publishes {len(wheels)} wheels; expected one")
    item = wheels[0]
    return {"filename": item["filename"], "url": item["url"], "sha256": item["digests"]["sha256"]}


def download(item: dict, destination: Path) -> Path:
    path = destination / item["filename"]
    digest = hashlib.sha256()
    with urlopen(item["url"], timeout=300) as response, path.open("wb") as handle:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            digest.update(chunk)
            handle.write(chunk)
    if digest.hexdigest() != item["sha256"]:
        path.unlink()
        raise ValueError(f"{item['filename']} does not match the digest PyPI publishes")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, choices=("pinned", "head"))
    parser.add_argument("--dest", required=True, type=Path)
    args = parser.parse_args()
    environment = json.loads((ROOT / "results" / args.run / "environment.json").read_text())
    args.dest.mkdir(parents=True, exist_ok=True)
    record = {}
    for name, version in pins(environment).items():
        item = wheel_file(name, version)
        download(item, args.dest)
        record[name] = {"version": version, "filename": item["filename"], "sha256": item["sha256"]}
    (args.dest / "wheels.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
