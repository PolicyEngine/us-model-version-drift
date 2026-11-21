"""Record which workflow run and which code produced a set of results.

Each run stamps its own result files with its run id and with the hashes of
the code it ran. After copying a run's artifacts into the results folder,
record the run::

    python scripts/provenance.py record measure --run 44904663719
    python scripts/provenance.py record score --run 44345993218

``record`` refuses files that another run made, or that different code made.
It takes the code hashes from the files, and the run's commit, event and
times from GitHub (through ``gh``), so nobody types them.

Ask whether the committed results still match the code::

    python scripts/provenance.py check measure

It prints ``stale=true`` or ``stale=false``. The workflow reads that line to
decide whether to measure, and a test fails while results are stale.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure  # noqa: E402
import prepare_scoring  # noqa: E402
from rules import file_hashes, stamped_by_one_run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "PolicyEngine/us-model-version-drift"

# For each kind of result: the files that decide what a run produces, where
# its record lives, the artifacts it comes from, and the result files that
# carry the run's stamp.
KINDS = {
    "measure": {
        "code": measure.MEASUREMENT_CODE,
        "record": "results/provenance.json",
        "artifacts": ["results-pinned", "results-head"],
        "stamped": ("results/pinned/environment.json", "results/head/environment.json"),
    },
    "score": {
        "code": prepare_scoring.SCORING_CODE,
        "record": "results/critical-targets/provenance.json",
        "artifacts": ["results-critical-targets"],
        "stamped": (
            *(f"results/critical-targets/scoring_inputs-{name}.json" for name in prepare_scoring.SCORING_JOBS),
            "results/critical-targets/combine.json",
        ),
    },
}


def code_hashes(kind: str = "measure", root: Path = ROOT) -> dict[str, str]:
    return file_hashes(root, KINDS[kind]["code"])


def recorded(kind: str = "measure", root: Path = ROOT) -> dict | None:
    path = root / KINDS[kind]["record"]
    return json.loads(path.read_text()) if path.exists() else None


def is_stale(kind: str = "measure", root: Path = ROOT) -> bool:
    """Whether the committed results predate the code in this tree."""
    record = recorded(kind, root)
    return record is None or record.get("code_sha256") != code_hashes(kind, root)


def stamps(kind: str = "measure", root: Path = ROOT) -> list[dict]:
    return [json.loads((root / path).read_text()) for path in KINDS[kind]["stamped"]]


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
    found = stamps(args.kind)
    try:
        hashes = stamped_by_one_run(found, REPOSITORY, args.run)
    except ValueError as exc:
        raise SystemExit(f"cannot record run {args.run}: {exc}")
    record = {
        **run_facts(args.run),
        # On a pull request the job checks out a merge commit, not head_sha.
        "checked_out": sorted({item["run"]["github_sha"] for item in found}),
        "artifacts": KINDS[args.kind]["artifacts"],
        "code_sha256": hashes,
    }
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    (ROOT / KINDS[args.kind]["record"]).write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
