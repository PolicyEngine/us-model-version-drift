"""Pure rules shared by the measurement and the comparison.

Nothing here imports a tax-benefit model, so the tests run anywhere.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Iterable, Mapping

# The policyengine-us variable naming convention. A stored column the release
# does not define, named outside it (a raw Census field such as ``A_AGE``), is
# a raw field rather than a missing variable.
MODEL_NAMED = re.compile(r"[a-z][a-z0-9_]*")

RAW_FIELD = "raw_field"
NOT_A_VARIABLE = "not_a_variable"
COMPUTED_VARIABLE = "computed_variable"
INPUT_VARIABLE = "input_variable"
CLASSES = (RAW_FIELD, NOT_A_VARIABLE, COMPUTED_VARIABLE, INPUT_VARIABLE)


def classify_column(
    column: str,
    variables: Mapping[str, bool],
) -> str:
    """Classify one stored column by how one release defines its name.

    ``variables`` maps each variable the release defines to whether the
    release declares a way to compute it: policyengine-core's
    ``Variable.is_input_variable()`` is false (the variable has a formula, or
    declares ``adds`` or ``subtracts``).

    - ``input_variable``: the release defines the name as an input.
    - ``computed_variable``: the release defines the name and declares a way
      to compute it. Core can still load stored values for such a variable, so
      this class describes the definition, not what the loader does.
    - ``not_a_variable``: the release does not define the name, and the name
      follows the model's convention. The loader cannot read it.
    - ``raw_field``: the release does not define the name, and the name is
      outside the convention.

    A defined name is classified by its definition whatever its spelling.
    """
    if column in variables:
        return COMPUTED_VARIABLE if variables[column] else INPUT_VARIABLE
    if MODEL_NAMED.fullmatch(column):
        return NOT_A_VARIABLE
    return RAW_FIELD


def classify_columns(
    columns: Iterable[str],
    variables: Mapping[str, bool],
) -> dict[str, list[str]]:
    """Partition stored columns into the four classes, each list sorted."""
    out: dict[str, list[str]] = {name: [] for name in CLASSES}
    for column in sorted(set(columns)):
        out[classify_column(column, variables)].append(column)
    return out


def relative_difference(baseline: float, tested: float) -> float | None:
    """``(tested - baseline) / |baseline|``, or ``None`` when undefined."""
    if baseline is None or tested is None:
        return None
    if not (math.isfinite(baseline) and math.isfinite(tested)):
        return None
    if baseline == 0:
        return None
    return (tested - baseline) / abs(baseline)


def compare_values(baseline: float | None, tested: float | None) -> dict:
    """One comparison row: both values, the difference and its ratio."""
    if baseline is None or tested is None:
        return {
            "baseline": baseline,
            "tested": tested,
            "difference": None,
            "relative_difference": None,
        }
    return {
        "baseline": baseline,
        "tested": tested,
        "difference": tested - baseline,
        "relative_difference": relative_difference(baseline, tested),
    }


RUN_KEYS = (
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_SHA",
    "GITHUB_REF",
    "GITHUB_EVENT_NAME",
)


def file_hashes(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """The sha256 of each file, keyed by its path under ``root``."""
    return {path: hashlib.sha256((Path(root) / path).read_bytes()).hexdigest() for path in paths}


def run_identity(environ: Mapping[str, str]) -> dict[str, str | None]:
    """Which workflow run this process belongs to, from GitHub's variables.

    Every value is ``None`` outside GitHub Actions. On a pull request,
    ``github_sha`` is the merge commit the job checked out, not the branch's
    head commit.
    """
    return {key.lower(): environ.get(key) for key in RUN_KEYS}


def stamped_by_one_run(stamps: Iterable[Mapping], repository: str, run: int) -> dict[str, str]:
    """The code hashes that several result files of one run agree on.

    Each stamp is a result file's ``{"run": ..., "code_sha256": ...}``. Raises
    ``ValueError`` unless every file names this repository and this run, and
    all carry the same hashes.
    """
    stamps = list(stamps)
    if not stamps:
        raise ValueError("no result file to check")
    hashes = None
    for stamp in stamps:
        identity = stamp.get("run") or {}
        if identity.get("github_repository") != repository:
            raise ValueError(f"a result file comes from {identity.get('github_repository')}, not {repository}")
        if str(identity.get("github_run_id")) != str(run):
            raise ValueError(f"a result file comes from run {identity.get('github_run_id')}, not {run}")
        code = stamp.get("code_sha256")
        if not code:
            raise ValueError("a result file records no code hashes")
        if hashes is not None and code != hashes:
            raise ValueError("the result files were made by different code")
        hashes = dict(code)
    return hashes
