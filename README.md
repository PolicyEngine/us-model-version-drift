# US model version drift

How far PolicyEngine US results on the default dataset move between two releases of the model, with the data held fixed.

## Results

One run, on 2026-11-17: [workflow run 44141335692](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/44141335692). Every figure below comes from the files in `results/`, and [`results/comparison.md`](results/comparison.md) lists every row.

| Environment | policyengine-us | policyengine-core | spm-calculator |
|---|---|---|---|
| `pinned` | 2.2.2 | 3.34.10 | 1.1.0 |
| `head` | 2.144.4 | 3.36.1 | 1.1.0 |

`pinned` holds the releases the `policyengine` 6.20.2 package names for the United States. `head` holds the newest policyengine-us and policyengine-core on PyPI that day. Both environments read the same bytes: the Microcosm US default dataset, `populace_us_2024.h5` (sha256 `6496cc43…aee84`).

### Neither release reads the dataset's WIC take-up draw

The dataset stores each person's WIC take-up draw as `would_claim_wic`. Neither release defines a variable of that name. Both define `takes_up_wic_if_eligible`, which defaults to true, so `policyengine_us.Microsimulation()` treats every eligible person as taking up WIC.

| WIC, 2024 | 2.2.2 | 2.144.4 |
|---|---|---|
| As the release loads the dataset | $11.52bn | $11.31bn |
| With the stored draw applied | $6.63bn | $6.47bn |
| Difference | $4.88bn (+74%) | $4.84bn (+75%) |

- "With the stored draw applied" means this repository copied `would_claim_wic` into `takes_up_wic_if_eligible` for each month of 2024, matching people by `person_id`. All 166,321 people matched.
- The `policyengine` package renames the column when it loads this dataset (`LEGACY_INPUT_RENAMES` in its `tax_benefit_models/us/legacy_inputs.py`, read at version 6.20.2). The gap above therefore applies to code that calls policyengine-us directly. This repository ran nothing through `policyengine`.
- policyengine-core logs one warning for each load. It counts the stored columns that match no variable (189 and 190 here) and names the first ten in sorted order. Those ten are raw Census fields.
- [PolicyEngine/microcosm#1026](https://github.com/PolicyEngine/microcosm/issues/1026) tracks the stored column.

### Column contract

The dataset stores 377 distinct columns across six tables.

| Class of stored column | 2.2.2 | 2.144.4 |
|---|---|---|
| An input variable of the release | 184 | 180 |
| A variable the release computes | 4 | 7 |
| A model-style name the release does not define | 26 | 27 |
| A raw field, named outside the model's convention | 163 | 163 |

"Computes" means the release gives the variable a formula, or defines it as a sum or difference of other variables.

- Neither release defines 25 of the model-style names. Twenty-two hold source and lineage identifiers. The other three are `would_claim_wic`, `medicare_part_b_premiums` and `filing_status_input`.
- 2.144.4 defines neither `first_home_mortgage_interest` nor `second_home_mortgage_interest`. 2.2.2 reads both as inputs.
- 2.144.4 reads `tax_unit_role_input` as an input. 2.2.2 does not define it.
- 2.2.2 reads four stored Social Security columns as inputs (`social_security_retirement`, `social_security_disability`, `social_security_survivors`, `social_security_dependents`). 2.144.4 computes all four. `weeks_worked` moved the other way.
- Each release declares one input a dataset must supply, `is_spm_independent_minor_role`, and the dataset stores it. The dataset stores none of the 21 columns each release says a dataset must not store.

### Aggregate panel

Each row is a weighted total over the dataset, or a weighted count for the two count rows. The change is `head` relative to `pinned`.

In 2024, 16 of the 19 rows with a ratio moved less than 2.5%. In 2026, 15 of 20 did.

| Row | 2024 | 2026 |
|---|---|---|
| Federal income tax | +1.8% | −0.6% |
| Child Tax Credit | +0.8% | +0.9% |
| Earned Income Tax Credit | +0.8% | +2.5% |
| SNAP | −2.4% | −5.2% |
| SSI | −2.1% | −2.0% |
| TANF | −0.1% | +2.7% |
| State income tax | −4.0% | −6.1% |
| Medicare benefit cost (`medicare_cost`) | +56.6% | +35.7% |
| Household net income | +0.6% | −1.0% |
| People in poverty under the model's Supplemental Poverty Measure (`person_in_poverty`) | −6.2% | +1.0% |

In dollars and people for 2024: federal income tax rose $41bn, state income tax fell $21bn, Medicare benefit cost rose $293bn, and the count of people in poverty fell from 44.3 million to 41.5 million.

### Fit to Microcosm's critical calibration targets

A second run, on 2026-11-18 ([workflow run 44345993218](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/44345993218)), scored both releases with Microcosm's own scorer (`tools/build_us_compatibility_recertification.py score` at microcosm commit `85d513b`). It scored them against the targets in the default dataset's published calibration diagnostics. [`results/critical-targets/critical_targets.md`](results/critical-targets/critical_targets.md) lists every row.

- Both releases keep all 21 scored target rows of Microcosm's 18 exact critical requirements within tolerance. Both also keep all 9 national dollar rows of SOI Table 1.4 within ±25%.
- The tightest row is federal income tax liability against SOI historic table 2. Its error is +0.3% under 2.2.2 and +2.1% under 2.144.4, against a ±5% tolerance.
- The scorer did not score one critical row: the itemized-deduction total from SOI table 4.3.
- 8 of the 9 Table 1.4 rows have the same estimate under both releases. Only taxable Social Security moves, from −10.9% to −10.5%.
- The scorer's programme totals equal this repository's 2024 panel to within one part in 10⁸, and a test checks this. The scorer runs in batches of households; the panel runs on the whole file.
- 2.144.4 reads one stored column that 2.2.2 does not define, `tax_unit_role_input`. Under 2.2.2, the tax-unit roles the engine assigns differ from the stored ones for 27,382 people (63.1 million weighted); under 2.144.4, for none. That column accounts for −$35.8bn of the $112.2bn rise in adjusted gross income.
- Microcosm's stored-input check fails under both releases. Both ignore `would_claim_wic` and `medicare_part_b_premiums`, and 2.144.4 also ignores the two mortgage-interest columns.

Every requirement is an IRS Statistics of Income (SOI) or Social Security Administration row for 2024. None covers Medicare, SNAP, SSI, state income tax, poverty or WIC, the rows that moved most between the releases. Passing these rows does not show that the head release is safe to promote.

The scorer needs a Supplemental Poverty Measure (SPM) geography, and the published diagnostics record none. `scripts/prepare_scoring.py` adds `{"geography_kind": "county"}`, the selection in Microcosm's published scoring of an October build and in the `policyengine` bundle. It checks that nothing else in the file changes. No critical target is a poverty measure.

### Run time

On a GitHub-hosted `ubuntu-latest` runner, one process that downloads the dataset, builds the simulation and computes one year of the panel took 268 and 275 seconds on 2.2.2, and 777 and 812 seconds on 2.144.4.

## What this does not show

- The panel reports movement between two releases. Only the critical-target scoring compares either release with external figures, and only for the rows Microcosm names, in 2024.
- The two environments differ in policyengine-us and in policyengine-core, so a row's movement can come from either package.
- Nothing here attributes a row's movement to a particular change.
- Two releases, one dataset, one run. The 2024 panel of an earlier run matched this one in every digit.

## Method

`scripts/measure.py` runs inside an environment that holds one release. It builds `policyengine_us.Microsimulation()` on the release's default dataset and writes JSON, one part for each process: the column contract, one panel year, WIC as loaded, and WIC with the stored draw applied. `scripts/compare.py` joins two runs. `scripts/rules.py` holds the classification and comparison rules.

Every total comes from a real microsimulation run. Each run downloads the dataset from the Hugging Face dataset `policyengine/populace-us` at revision `populace-us-2024-spm-20260915` and checks its hash. This repository stores aggregates and column names, and no records.

The tests in `tests/` check the rules with property-based tests, and check the committed results: the comparison regenerates byte for byte from the two runs' files, both runs read the same dataset bytes, each run used the releases its environment file pins, and the measurement code still matches the hashes in `results/provenance.json`.

## Measure again

The `Measure` workflow builds both environments on GitHub-hosted runners and uploads the results. A run takes about 50 minutes, so it starts by hand:

```bash
gh workflow run measure.yml --ref <branch>
```

Then download the run's `results-pinned` and `results-head` artifacts into `results/pinned` and `results/head`, and record the run:

```bash
python scripts/provenance.py --run <run id> --event workflow_dispatch --head-sha <commit> --completed <UTC time>
```

```bash
python scripts/compare.py results/pinned results/head --out results
```

## Score again

The `Score` workflow runs on pull requests that change the scoring code, and by hand:

```bash
gh workflow run score.yml --ref <branch>
```

Download `drift.json` and `critical_targets.json` from its `results-critical-targets` artifact, and `scoring_inputs.json` from any `scores-*` artifact, into `results/critical-targets`. Then record the run's ids and code hashes in `results/critical-targets/provenance.json` and rebuild the tables:

```bash
python scripts/critical_targets.py --render results/critical-targets --out results/critical-targets
```

## Run one environment yourself

```bash
uv venv --python 3.13 .venv
```

```bash
uv pip install --python .venv/bin/python -r envs/head.txt
```

```bash
.venv/bin/python scripts/measure.py --label head --out results/head --part panel --period 2024
```

A run downloads about 830 MB. Holding two panel years in one process exhausted a 16 GB runner, so each part runs in its own process.
