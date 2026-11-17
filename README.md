# US model version drift

How far PolicyEngine US results on the default dataset move between two releases of the model, with the data held fixed.

## Why

The `policyengine` package pins one policyengine-us release for the United States, and policyengine-us publishes many releases after that pin. Both use the same default dataset. This repository measures what changes when only the model release changes:

1. **Column contract.** Which columns the dataset stores that a release does not define as variables, and which it computes itself.
2. **Aggregate panel.** Weighted totals for a fixed list of programmes in 2024 and 2026.
3. **WIC take-up.** The dataset stores each person's WIC take-up draw as `would_claim_wic`. The measurement records WIC as each release loads the data, and again with the stored draw applied to the release's take-up input.

## What is compared

| Environment | policyengine-us | policyengine-core | spm-calculator |
|---|---|---|---|
| `pinned` | 2.2.2 | 3.34.10 | 1.1.0 |
| `head` | 2.144.4 | 3.36.1 | resolved by the installer |

`pinned` is the set the `policyengine` 6.20.2 bundle names. `head` is the newest policyengine-us on PyPI on 2026-11-17.

The dataset is the public Microcosm US default, `populace_us_2024.h5` at revision `populace-us-2024-spm-20260915` of the Hugging Face dataset `policyengine/populace-us` (sha256 `6496cc43…aee84`). Each run downloads it and checks the hash. No record-level data is stored in this repository: results are aggregates.

## Method

`scripts/measure.py` runs inside an environment holding one release. It builds `policyengine_us.Microsimulation()` on the release's default dataset and writes JSON. `scripts/compare.py` joins two runs. `scripts/rules.py` holds the classification and comparison rules, with property-based tests in `tests/`.

Every total is a weighted sum from a real microsimulation run. Rows whose variable a release does not define are reported as such.

The `Measure` workflow builds both environments on GitHub-hosted runners and uploads the results.

## Limits

- The panel reports movement between two releases. It does not score either release against external targets.
- Two releases are compared; nothing is said about the releases between them.
- The WIC row with the stored draw applied sets the take-up input by `person_id` for each month of 2024. It is this repository's own application of the draw.

## Run it yourself

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r envs/head.txt
.venv/bin/python scripts/measure.py --label head --out results/head
```

A run needs about 1 GB of download and several GB of memory.
