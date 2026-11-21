# US model version drift

How far PolicyEngine US results on the default dataset move between two releases of the model, with the data held fixed.

## Results

Measured on 2026-11-21: [workflow run 44907751024](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/44907751024). Every figure below comes from the files in `results/`, and [`results/comparison.md`](results/comparison.md) lists every row.

| Environment | policyengine-us | policyengine-core | spm-calculator |
|---|---|---|---|
| `pinned` | 2.2.2 | 3.34.10 | 1.1.0 |
| `head` | 2.144.4 | 3.36.1 | 1.1.0 |

`pinned` holds the releases the `policyengine` 6.20.2 package names for the United States. `head` holds the newest policyengine-us and policyengine-core on PyPI on 2026-11-17. Both environments read the same bytes: the Microcosm US default dataset, `populace_us_2024.h5` (sha256 `6496cc43…aee84`). Each release checks the file it loads against that hash.

### Neither release reads the dataset's WIC take-up draw

The dataset stores each person's WIC take-up draw as `would_claim_wic`. Neither release defines a variable of that name. Both define `takes_up_wic_if_eligible`, which defaults to true, so `policyengine_us.Microsimulation()` treats every eligible person as taking up WIC.

| WIC, 2024 | 2.2.2 | 2.144.4 |
|---|---|---|
| As the release loads the dataset | $11.52bn | $11.31bn |
| With the stored draw applied | $6.63bn | $6.47bn |
| Difference | $4.88bn (+74%) | $4.84bn (+75%) |

- "With the stored draw applied" means this repository copied `would_claim_wic` into `takes_up_wic_if_eligible` for each month of 2024, matching people on `person_id`. The ids are unique in the stored table and in the simulation, and both hold the same 166,321 ids. The measurement stops if they do not.
- As loaded, the take-up input is true for every person. With the stored draw applied it is true for 3.80% of people, weighted by person weight (the January 2024 input). The stored draw is true for 4.49% of stored person rows, unweighted.
- The stored draw was applied for one year and one total: WIC in 2024.
- The `policyengine` package renames the column when it loads this dataset (`LEGACY_INPUT_RENAMES` in its `tax_benefit_models/us/legacy_inputs.py`, read at version 6.20.2). The gap above therefore applies to code that calls policyengine-us directly. This repository ran nothing through `policyengine`.
- policyengine-core logs one warning for each load. It counts the stored columns that match no variable (189 and 190 here) and names the first ten in sorted order. Those ten are raw Census fields.
- [PolicyEngine/microcosm#1026](https://github.com/PolicyEngine/microcosm/issues/1026) tracks the stored column.

### Column contract

The dataset stores 377 distinct columns across six tables. This table classes each by how the release defines a variable of that name.

| Class of stored column | 2.2.2 | 2.144.4 |
|---|---|---|
| Defined as an input | 184 | 180 |
| Defined as computed | 4 | 7 |
| Not defined, with a model-style name | 26 | 27 |
| Not defined, a raw field named outside the model's convention | 163 | 163 |

"Computed" means policyengine-core's `is_input_variable()` is false for the variable: it has a formula, or it is declared as a sum or difference of others. The classes describe the definition. They do not show what the loader does with a column, because policyengine-core can load stored values for a variable that has a formula.

- Neither release defines 25 of the model-style names. Twenty-two hold source and lineage identifiers. The other three are `would_claim_wic`, `medicare_part_b_premiums` and `filing_status_input`.
- 2.144.4 defines neither `first_home_mortgage_interest` nor `second_home_mortgage_interest`. 2.2.2 defines both as inputs.
- 2.144.4 defines `tax_unit_role_input` as an input. 2.2.2 does not define it.
- 2.2.2 defines four stored Social Security columns as inputs (`social_security_retirement`, `social_security_disability`, `social_security_survivors`, `social_security_dependents`). 2.144.4 gives all four a formula, and its loader moves the stored values into a separate source store for those formulas (`migrate_social_security_inputs` in `policyengine_us/tools/social_security_inputs.py`). Total Social Security in 2024 is the same under both releases.
- 2.2.2 gives `weeks_worked` a formula that starts in 2025 and carries the previous year's value forward, so for 2024 it reads the stored value. 2.144.4 defines it as an input.
- `policyengine_us.spm` in each release lists one column a dataset must supply, `is_spm_independent_minor_role` (`DATASET_SOURCE_INPUTS`), and 21 a dataset must not store (`REJECTED_DATASET_INPUTS`). The dataset stores the first and none of the 21. This checks names only.

### Aggregate panel

Each row is a weighted total in dollars, except three counts: SPM units that receive SNAP, people enrolled in Medicaid, and people in poverty. The change is `head` relative to `pinned`.

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
| Net value of Medicare coverage (`medicare_cost`) | +56.6% | +35.7% |
| Household net income | +0.6% | −1.0% |
| People in poverty under the model's Supplemental Poverty Measure (`person_in_poverty`) | −6.2% | +1.0% |

In dollars and people for 2024: federal income tax rose $41bn, state income tax fell $21bn, and the count of people in poverty fell from 44.3 million to 41.5 million.

The Medicare row compares two definitions. `medicare_cost` is each release's estimate of the value of Medicare coverage, net of premiums, and it rose $293bn in 2024.

- 2.2.2 values spending per enrollee at $11,080 in 2024, a 2021 figure for Parts A and B, and subtracts the Part A and Part B premiums.
- 2.144.4 uses the Centers for Medicare & Medicaid Services' figure for all Medicare spending per enrollee, $16,779 in 2024. It also subtracts Part D premiums.

The rise reflects that change of definition. It does not show a change in policy or in the data.

### Fit to Microcosm's critical calibration targets

Scored on 2026-11-21: [workflow run SCORE_RUN](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/SCORE_RUN). It scored both releases with Microcosm's own scorer (`tools/build_us_compatibility_recertification.py score` at microcosm commit `85d513b`), against the target values in the default dataset's published calibration diagnostics. Those are the values the build was calibrated to; this repository did not rebuild them from the source publications. [`results/critical-targets/critical_targets.md`](results/critical-targets/critical_targets.md) lists every row.

- Both releases keep all 21 scored target rows of Microcosm's 18 exact critical requirements within tolerance. Both also keep all 9 national dollar rows of SOI Table 1.4 within ±25%. The tolerance is each requirement's own limit on the absolute relative error, with no allowance for improving on an earlier build.
- The tightest row is federal income tax liability against SOI historic table 2. Its error is +0.3% under 2.2.2 and +2.1% under 2.144.4, against a ±5% tolerance.
- One row has no score. The itemized-deduction requirement also covers the total from SOI table 4.3 (all returns excluding dependents), and Microcosm's scorer cannot reproduce that row. The requirement's three other rows are scored.
- 8 of the 9 Table 1.4 rows have the same estimate under both releases. Only taxable Social Security moves, from −10.9% to −10.5%.
- The scorer's programme totals equal this repository's 2024 panel to within one part in 10⁸, and a test checks this. The scorer runs in batches of households; the panel runs on the whole file.
- 2.144.4 reads one stored column that 2.2.2 does not define, `tax_unit_role_input`. Under 2.2.2, the tax-unit roles the engine assigns differ from the stored ones for 27,382 people (63.1 million weighted); under 2.144.4, for none. Reading that column lowers adjusted gross income under 2.144.4 by $35.8bn: the rise between the releases is $112.2bn with it and $148.0bn without it.
- Microcosm's stored-input check fails under both releases. Both ignore `would_claim_wic` and `medicare_part_b_premiums`, and 2.144.4 also ignores the two mortgage-interest columns.
- SCORE_AGREEMENT

Every requirement is an IRS Statistics of Income (SOI) or Social Security Administration row for 2024. None covers Medicare, SNAP, SSI, state income tax, poverty or WIC, the rows that moved most between the releases. Passing these rows does not show that the head release is safe to promote.

The scorer needs a Supplemental Poverty Measure (SPM) geography, and the published diagnostics record none. `scripts/prepare_scoring.py` adds `{"geography_kind": "county"}`, the selection in Microcosm's published scoring of an October build and in the `policyengine` bundle. It checks that nothing else in the file changes. No critical target is a poverty measure.

### Run time

On a GitHub-hosted `ubuntu-latest` runner, one process that builds the simulation and computes one year of the panel took 427 and 446 seconds on 2.2.2, and 554 and 578 seconds on 2.144.4. The dataset was already on the runner's disk: an earlier step had downloaded it.

Times vary a lot between runs. Across this run and the two earlier complete runs in `results/earlier/`, a panel year took 268 to 473 seconds on 2.2.2 and 546 to 812 seconds on 2.144.4. Within a run, 2.144.4 took between 1.2 and 3.0 times as long as 2.2.2.

## What this does not show

- The panel reports movement between two releases. Only the critical-target scoring compares either release with external figures, and only for the rows Microcosm names, in 2024.
- The two environments differ in policyengine-us and in policyengine-core, so a row's movement can come from either package.
- Nothing here attributes a row's movement to a particular change.
- A national total can hide changes that offset each other across households.
- Each release extends the 2024 file to 2026 with its own uprating factors. The 2026 rows therefore mix differences in rules with differences in uprating.
- Two releases, one dataset. Three earlier runs, from 2026-11-17 to 2026-11-21 and under earlier versions of this code, measured the same panel. Every row they measured, 204 in all, equals this run's in every digit (`results/earlier/`).
- The environments install under lock files, so every package version is fixed. The interpreter is Python 3.13; its patch version is recorded in `results/*/environment.json`, not pinned.

## Method

`scripts/measure.py` runs inside an environment that holds one release. It builds `policyengine_us.Microsimulation()` on the release's default dataset and writes JSON, one part for each process: the column contract, one panel year, WIC as loaded, and WIC with the stored draw applied. `scripts/compare.py` joins two runs. `scripts/rules.py` holds the classification and comparison rules.

Each run writes its workflow run id and the hashes of its measurement code into `environment.json`. `scripts/provenance.py` records a run only if both environments' files name that run and carry the same hashes.

Every total comes from a real microsimulation run. Each run downloads the dataset from the Hugging Face dataset `policyengine/populace-us` at revision `populace-us-2024-spm-20260915` and checks its hash. It also checks that the release certifies that same hash for its own default dataset, which each release verifies when it loads the file. This repository stores aggregates and column names, and no records.

A run fails if it cannot measure everything. A panel row with no finite value fails its part. So does a stored draw whose ids do not line up, an environment that differs from its lock file, or a release with another default dataset. A part never replaces an existing file, and `scripts/compare.py` refuses two runs that are incomplete or that disagree on what a row measures.

The tests in `tests/` check the rules with property-based tests, and check the committed results:

- The comparison regenerates byte for byte from the two runs' files.
- The measurement code still matches the hashes the run wrote into its files, and both environments' files name the run in `results/provenance.json`.
- Each run installed exactly its lock file.
- Each run measured exactly the panel the code defines.
- The column classes follow from the recorded definitions.
- The earlier runs in `results/earlier/` gave exactly this run's panel rows.
- The critical-target tables rebuild byte for byte from `drift.json`, the scores used the measured releases and dataset, and the earlier scoring runs in `results/critical-targets/earlier/` agree with this one.

## Measure again

The `Measure` workflow builds both environments on GitHub-hosted runners and uploads the results. A measurement takes about 50 minutes. It starts on a pull request whenever the measurement code no longer matches the committed results, and by hand:

```bash
gh workflow run measure.yml --ref <branch>
```

Then replace `results/pinned` and `results/head` with the run's `results-pinned` and `results-head` artifacts, record the run and rebuild the comparison. Recording fails if the files come from another run:

```bash
python scripts/provenance.py record measure --run <run id>
```

```bash
python scripts/compare.py results/pinned results/head --out results
```

`results/provenance.json` records the run's commit and its start and finish times, read from GitHub.

## Score again

The `Score` workflow runs Microcosm's scorer three times on GitHub-hosted runners: each release as stored, and 2.144.4 without the stored column it newly reads. It takes about 15 minutes. It starts on a pull request whenever the scoring code no longer matches the committed scores, and by hand:

```bash
gh workflow run score.yml --ref <branch>
```

Then replace the files in `results/critical-targets` (keeping `earlier/`) with the run's `results-critical-targets` artifact, and record the run. Recording fails if the files come from another run:

```bash
python scripts/provenance.py record score --run <run id>
```

The tables rebuild from `drift.json` without Microcosm, and a test checks that they match byte for byte:

```bash
python scripts/critical_targets.py --render results/critical-targets --out results/critical-targets
```

## Run one environment yourself

```bash
uv venv --python 3.13 .venv
```

```bash
uv pip install --python .venv/bin/python -r envs/head.txt -c envs/head.lock.txt
```

```bash
.venv/bin/python scripts/measure.py --label head --out out/head --part panel --period 2024
```

A run downloads about 830 MB. The first run, [44133383190](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/44133383190), held two panel years in one process, and both 16 GB runners shut down partway into the second year. Each part now runs in its own process.
