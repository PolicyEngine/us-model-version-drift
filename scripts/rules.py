"""Pure rules shared by the measurement and the comparison.

Nothing here imports a tax-benefit model, so the tests run anywhere.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Mapping

# The policyengine-us variable naming convention. A stored column outside it
# (a raw Census field such as ``A_AGE``) cannot name a model variable.
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
    """Classify one stored column against one model release.

    ``variables`` maps each variable the release defines to whether the
    release computes it (it has a formula, or it adds or subtracts others).

    - ``raw_field``: the name is outside the model's naming convention.
    - ``not_a_variable``: a model-style name the release does not define. The
      loader cannot read it as an input.
    - ``computed_variable``: the release defines it and computes it.
    - ``input_variable``: the release defines it and reads it from data.
    """
    if not MODEL_NAMED.fullmatch(column):
        return RAW_FIELD
    if column not in variables:
        return NOT_A_VARIABLE
    return COMPUTED_VARIABLE if variables[column] else INPUT_VARIABLE


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
