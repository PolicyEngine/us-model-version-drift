"""Record which workflow run and which code produced a set of results.

Each run stamps its environment files with its run id and with the hashes of
the code it ran. After copying a run's artifacts into the results folder,
record the run::

    python scripts/provenance.py record measure --run 44904663719
    python scripts/provenance.py record score --run 44345993218

``record`` downloads the run's artifacts from GitHub (through ``gh``) and
refuses the committed results unless they are exactly those artifacts' files,
byte for byte, with none missing and none extra, at any depth of each result
folder. Only a folder a kind names as kept outside the record, such as the
earlier scoring runs, is not compared. It also refuses stamps that name another
repository or run, or that disagree on the code; ``check`` and the tests
compare that code with the tree. It writes each file's hash, the code hashes
from the stamps, and the run's commit, event and times from GitHub, so nobody
types them. Afterwards a test checks the committed files against the recorded
hashes; it does not download the artifacts again.

Ask whether the committed results still match the code::

    python scripts/provenance.py check measure

It prints ``stale=true`` or ``stale=false``. The workflow reads that line to
decide whether to measure, and a test fails while results are stale. Scores
are also stale when the releases or dataset they scored differ from the ones
the committed measurement ran.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_wheels  # noqa: E402
import measure  # noqa: E402
import prepare_scoring  # noqa: E402
from rules import file_hashes, stamped_by_one_run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "PolicyEngine/us-model-version-drift"

# For each kind of result: the files that decide what a run produces, where
# its record lives, the artifacts it comes from, and the result files that
# carry the run's stamp. Each artifact maps to the folder that holds its
# committed copy and the pattern its files match there, at any depth. A kind's
# "outside" folders hold files kept beside the results but outside the record,
# with tests of their own. The comparison is not
# among them: it is a pure function of the two environments' files, and a test
# rebuilds it byte for byte with the compare.py in the tree.
KINDS = {
    "measure": {
        "code": measure.MEASUREMENT_CODE,
        "record": "results/provenance.json",
        "artifacts": {
            "results-pinned": ("results/pinned", "**/*"),
            "results-head": ("results/head", "**/*"),
        },
        "stamped": ("results/pinned/environment.json", "results/head/environment.json"),
    },
    "score": {
        "code": prepare_scoring.SCORING_CODE,
        "record": "results/critical-targets/provenance.json",
        "artifacts": {"results-critical-targets": ("results/critical-targets", "**/*")},
        "outside": ("results/critical-targets/earlier",),
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


def scores_differ_from_measured(root: Path = ROOT) -> list[str]:
    """How the scored releases and dataset differ from the measured ones."""
    path = root / "results" / "critical-targets" / "critical_targets.json"
    if not path.exists():
        return ["no committed scores"]
    result = json.loads(path.read_text())
    found = []
    for side, run in (("baseline", "pinned"), ("tested", "head")):
        environment = json.loads((root / "results" / run / "environment.json").read_text())
        if result[side]["versions"] != fetch_wheels.pins(environment):
            found.append(f"the {side} scores ran other releases than the {run} measurement")
        if result["dataset_sha256"] != environment["dataset"]["sha256"]:
            found.append(f"the scores read another dataset than the {run} measurement")
    return found


def is_stale(kind: str = "measure", root: Path = ROOT) -> bool:
    """Whether the committed results predate the code in this tree, or, for
    scores, the committed measurement."""
    record = recorded(kind, root)
    if record is None or record.get("code_sha256") != code_hashes(kind, root):
        return True
    return kind == "score" and bool(scores_differ_from_measured(root))


def stamps(kind: str = "measure", root: Path = ROOT) -> list[dict]:
    return [json.loads((root / path).read_text()) for path in KINDS[kind]["stamped"]]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def committed(kind: str = "measure", root: Path = ROOT) -> dict[str, str]:
    """The committed result files that copy the kind's artifacts, each with the
    artifact it belongs to: every file under the artifact's folder, at any
    depth, except the record and the kind's "outside" folders. A symbolic link
    counts as an entry, even a dangling one, so the checks can refuse it."""
    outside = [root / folder for folder in KINDS[kind].get("outside", ())]
    out = {}
    for artifact, (folder, pattern) in KINDS[kind]["artifacts"].items():
        for path in sorted((root / folder).glob(pattern)):
            name = path.relative_to(root).as_posix()
            if name == KINDS[kind]["record"] or (path.is_dir() and not path.is_symlink()):
                continue
            if any(path.is_relative_to(folder_) for folder_ in outside):
                continue
            out[name] = artifact
    return out


def links_among(names, root: Path = ROOT) -> list[str]:
    """The names that are symbolic links. A result is a regular file; a link,
    even to identical bytes, is refused."""
    return sorted(name for name in names if (root / name).is_symlink())


def match_artifacts(kind: str, downloaded: dict[str, Path], root: Path = ROOT) -> dict[str, str]:
    """Each result file's hash, taken from the artifacts' bytes.

    Raises ``ValueError`` unless the committed files (``committed``: at any
    depth, outside the kind's "outside" folders) are exactly the artifacts'
    files: none missing, none extra, every byte the same.
    """
    expected = {}
    for artifact, (folder, _) in KINDS[kind]["artifacts"].items():
        base = downloaded[artifact]
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            expected[f"{folder}/{path.relative_to(base).as_posix()}"] = sha256_of(path)
    have = committed(kind, root)
    links = links_among(have, root)
    found = [f"a symbolic link, not a file: {name}" for name in links]
    found += [f"missing from results: {name}" for name in sorted(set(expected) - set(have))]
    found += [f"not in the run's artifacts: {name}" for name in sorted(set(have) - set(expected) - set(links))]
    found += [
        f"differs from the run's artifact: {name}"
        for name in sorted(set(expected) & set(have) - set(links))
        if sha256_of(root / name) != expected[name]
    ]
    if found:
        raise ValueError("; ".join(found))
    return dict(sorted(expected.items()))


def files_differ_from_record(kind: str = "measure", root: Path = ROOT) -> list[str]:
    """How the committed result files differ from the recorded ones."""
    files = (recorded(kind, root) or {}).get("files", {})
    have = committed(kind, root)
    links = links_among(have, root)
    found = [f"a symbolic link, not a file: {name}" for name in links]
    found += [f"recorded but not committed: {name}" for name in sorted(set(files) - set(have))]
    found += [f"committed but not recorded: {name}" for name in sorted(set(have) - set(files) - set(links))]
    found += [
        f"changed since recording: {name}"
        for name in sorted(set(files) & set(have) - set(links))
        if sha256_of(root / name) != files[name]
    ]
    return found


def download(run: int, artifacts, dest: Path) -> dict[str, Path]:
    """Download each named artifact of the run into its own folder."""
    out = {}
    for name in artifacts:
        out[name] = dest / name
        subprocess.run(
            ["gh", "run", "download", str(run), "-R", REPOSITORY, "-n", name, "-D", str(out[name])],
            check=True,
        )
    return out


def gh_api(path: str) -> dict:
    done = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def run_facts(run: int) -> dict:
    """What GitHub records about one workflow run. The run finished when its
    last job did; the run's own ``updated_at`` can change later."""
    payload = gh_api(f"repos/{REPOSITORY}/actions/runs/{run}")
    if payload["conclusion"] != "success":
        raise SystemExit(f"run {run} concluded {payload['conclusion']}, not success")
    jobs = gh_api(f"repos/{REPOSITORY}/actions/runs/{run}/jobs?per_page=100")["jobs"]
    return {
        "workflow_run": run,
        "workflow": payload["name"],
        "url": payload["html_url"],
        "event": payload["event"],
        "head_sha": payload["head_sha"],
        "started": payload["run_started_at"],
        "completed": max(job["completed_at"] for job in jobs),
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
    artifacts = list(KINDS[args.kind]["artifacts"])
    try:
        hashes = stamped_by_one_run(found, REPOSITORY, args.run)
        with tempfile.TemporaryDirectory() as tmp:
            files = match_artifacts(args.kind, download(args.run, artifacts, Path(tmp)))
    except ValueError as exc:
        raise SystemExit(f"cannot record run {args.run}: {exc}")
    record = {
        **run_facts(args.run),
        # On a pull request the job checks out a merge commit, not head_sha.
        "checked_out": sorted({item["run"]["github_sha"] for item in found}),
        "artifacts": artifacts,
        "files": files,
        "code_sha256": hashes,
    }
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    (ROOT / KINDS[args.kind]["record"]).write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
