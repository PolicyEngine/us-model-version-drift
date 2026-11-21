# US model version drift

How far PolicyEngine US results on the default dataset move between two releases of the model, with the data held fixed.

## Results

Measured on 2026-11-21: [workflow run 44904663719](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/44904663719). Every figure below comes from the files in `results/`, and [`results/comparison.md`](results/comparison.md) lists every row.

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

### Run time

RUNTIME_PARAGRAPH

## What this does not show

- The panel reports movement between two releases. It scores neither release against external targets.
- The two environments differ in policyengine-us and in policyengine-core, so a row's movement can come from either package.
- Nothing here attributes a row's movement to a particular change.
- A national total can hide changes that offset each other across households.
- Each release extends the 2024 file to 2026 with its own uprating factors. The 2026 rows therefore mix differences in rules with differences in uprating.
- Two releases, one dataset. AGREEMENT_SENTENCE
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
- The earlier runs in `results/earlier/` agree with this one.

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
