"""Record which workflow run and which code produced a set of results.

Record a run, after downloading its artifacts into the results folder::

    python scripts/provenance.py record measure --run 44141335692

The run's commit, event and times come from GitHub (through ``gh``), so
nobody types them.

Ask whether the committed results still match the code::

    python scripts/provenance.py check measure

It prints ``stale=true`` or ``stale=false``. The workflow reads that line to
decide whether to measure, and a test fails while results are stale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "PolicyEngine/us-model-version-drift"

# For each kind of result: the files that decide what a run produces, where
# its record lives, and the artifacts it comes from. ``compare.py`` is absent
# from ``measure`` on purpose: the comparison is a pure function of the two
# runs' files, and a test regenerates it.
KINDS = {
    "measure": {
        "code": (
            "scripts/measure.py",
            "scripts/rules.py",
            "envs/pinned.txt",
            "envs/pinned.lock.txt",
            "envs/head.txt",
            "envs/head.lock.txt",
            ".github/workflows/measure.yml",
        ),
        "record": "results/provenance.json",
        "artifacts": ["results-pinned", "results-head"],
    },
}


def code_hashes(kind: str = "measure", root: Path = ROOT) -> dict[str, str]:
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in KINDS[kind]["code"]}


def recorded(kind: str = "measure", root: Path = ROOT) -> dict | None:
    path = root / KINDS[kind]["record"]
    return json.loads(path.read_text()) if path.exists() else None


def is_stale(kind: str = "measure", root: Path = ROOT) -> bool:
    """Whether the committed results predate the code in this tree."""
    record = recorded(kind, root)
    return record is None or record.get("code_sha256") != code_hashes(kind, root)


def run_facts(run: int) -> dict:
    """What GitHub records about one workflow run."""
    done = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/actions/runs/{run}"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(done.stdout)
    if payload["conclusion"] != "success":
        raise SystemExit(f"run {run} concluded {payload['conclusion']}, not success")
    return {
        "workflow_run": run,
        "workflow": payload["name"],
        "url": payload["html_url"],
        "event": payload["event"],
        "head_sha": payload["head_sha"],
        "started": payload["run_started_at"],
        "completed": payload["updated_at"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "check"))
    parser.add_argument("kind", choices=sorted(KINDS))
    parser.add_argument("--run", type=int, help="the workflow run id, for record")
    args = parser.parse_args()
    if args.action == "check":
        print(f"stale={'true' if is_stale(args.kind) else 'false'}")
        return 0
    if args.run is None:
        parser.error("record needs --run")
    record = {
        **run_facts(args.run),
        "artifacts": KINDS[args.kind]["artifacts"],
        "code_sha256": code_hashes(args.kind),
    }
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    (ROOT / KINDS[args.kind]["record"]).write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
