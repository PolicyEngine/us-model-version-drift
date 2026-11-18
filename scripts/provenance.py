"""Record which workflow run and which measurement code produced ``results/``.

Usage, after downloading a ``Measure`` run's artifacts into ``results/``::

    python scripts/provenance.py --run 44141335692 --event pull_request \
        --head-sha <commit> --completed 2026-11-17T18:37:38Z

A test compares the recorded hashes with the files in the tree, so results
that predate a change to the measurement code fail until someone measures
again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "PolicyEngine/us-model-version-drift"

# The files that decide what a run measures. ``compare.py`` is absent on
# purpose: the comparison is a pure function of the two runs' files, and a
# separate test regenerates it.
MEASUREMENT_CODE = (
    "scripts/measure.py",
    "scripts/rules.py",
    "envs/pinned.txt",
    "envs/head.txt",
)


def code_hashes(root: Path = ROOT) -> dict[str, str]:
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in MEASUREMENT_CODE}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=int, required=True, help="the Measure workflow run id")
    parser.add_argument("--event", required=True, help="the event that started the run")
    parser.add_argument("--head-sha", required=True, help="the commit the run measured")
    parser.add_argument("--completed", required=True, help="when the run finished, UTC")
    args = parser.parse_args()
    record = {
        "workflow_run": args.run,
        "url": f"https://github.com/{REPOSITORY}/actions/runs/{args.run}",
        "event": args.event,
        "head_sha": args.head_sha,
        "completed": args.completed,
        "artifacts": ["results-pinned", "results-head"],
        "measurement_code_sha256": code_hashes(),
    }
    (ROOT / "results" / "provenance.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
