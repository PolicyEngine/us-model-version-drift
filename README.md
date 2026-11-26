# US model version drift

How far PolicyEngine US results on the default dataset move between two releases of the model, with the data held fixed.

## Results

Measured on 2026-11-26: [workflow run 45800841504](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/45800841504). Every figure below comes from the files in `results/`, and [`results/comparison.md`](results/comparison.md) lists every row. Commit `2a03f3e` keeps the [README](https://github.com/PolicyEngine/us-model-version-drift/blob/2a03f3e/README.md) and [results](https://github.com/PolicyEngine/us-model-version-drift/tree/2a03f3e/results) of the previous measurement, which had policyengine-us 2.144.4 as head.

| Environment | policyengine-us | policyengine-core | spm-calculator |
|---|---|---|---|
| `pinned` | 2.2.2 | 3.34.10 | 1.1.0 |
| `head` | 2.154.0 | 3.37.2 | 1.1.0 |

`pinned` holds the releases the `policyengine` 6.20.2 package names for the United States. `head` holds 2.154.0, the newest policyengine-us on PyPI on 2026-11-26, and policyengine-core 3.37.2, the newest core release that day and the lowest that 2.154.0 accepts. Both environments read the same bytes: the Microcosm US default dataset, `populace_us_2024.h5` (sha256 `6496cc43…aee84`). Each release checks the file it loads against that hash.

### Neither release reads the dataset's WIC take-up draw

The dataset stores each person's WIC take-up draw as `would_claim_wic`. Neither release defines a variable of that name. Both define `takes_up_wic_if_eligible`, which defaults to true, so `policyengine_us.Microsimulation()` treats every eligible person as taking up WIC.

| WIC, 2024 | 2.2.2 | 2.154.0 |
|---|---|---|
| As the release loads the dataset | $11.52bn | $11.31bn |
| With the stored draw applied | $6.63bn | $6.47bn |
| Difference, relative to the total with the stored draw | $4.88bn (+74%) | $4.84bn (+75%) |

- "With the stored draw applied" means this repository copied `would_claim_wic` into `takes_up_wic_if_eligible` for each month of 2024, matching people on `person_id`. Under both releases, no id repeats in the stored table or in the simulation, the table and the simulation hold the same 166,321 ids, and the stored table lists them in the simulation's order. Each matched person's stored `age` equals the simulation's, and every matched person has a stored draw. The measurement stops if an id repeats, the two sets of ids differ, a person lacks a draw, a draw holds a value other than true or false, or the stored age differs for any person. It records the row order but does not require it.
- As loaded, the take-up input defaults to true for every person. Applying the stored draw sets the January 2024 take-up input to true for 3.80% of people, counting each at their person weight. Unweighted, 4.49% of stored person rows carry a true draw.
- This repository applied the stored draw for one year and one total: WIC in 2024.
- The `policyengine` package renames the column when it loads this dataset (`LEGACY_INPUT_RENAMES` in its `tax_benefit_models/us/legacy_inputs.py`, read at version 6.20.2). The gap above therefore applies to code that calls policyengine-us directly. This repository ran nothing through `policyengine`.
- policyengine-core logs one warning for each load. It counts the stored columns that match no variable (189 under 2.2.2, 190 under 2.154.0) and names the first ten in sorted order. All ten name raw Census fields.
- [PolicyEngine/microcosm#1026](https://github.com/PolicyEngine/microcosm/issues/1026) tracks the stored column.

### Column contract

The dataset stores 377 distinct columns across six tables. This table classes each by how the release defines a variable of that name.

| Class of stored column | 2.2.2 | 2.154.0 |
|---|---|---|
| Defined as an input | 184 | 180 |
| Defined as computed | 4 | 7 |
| Not defined, with a model-style name | 26 | 27 |
| Not defined, a raw field named outside the model's convention | 163 | 163 |

"Computed" means policyengine-core's `is_input_variable()` returns false for the variable: it has a formula, or its definition declares it a sum or difference of others. The classes describe the definition. They do not show what the loader does with a column, because policyengine-core can load stored values for a variable that has a formula.

- Neither release defines 25 of the model-style names. Twenty-two hold source and lineage identifiers; `would_claim_wic`, `medicare_part_b_premiums` and `filing_status_input` make up the other three.
- 2.154.0 defines neither `first_home_mortgage_interest` nor `second_home_mortgage_interest`. 2.2.2 defines both as inputs.
- 2.154.0 defines `tax_unit_role_input` as an input. 2.2.2 does not define it.
- 2.2.2 defines four stored Social Security columns as inputs (`social_security_retirement`, `social_security_disability`, `social_security_survivors`, `social_security_dependents`). 2.154.0 gives all four a formula, and its loader moves the stored values into a separate source store for those formulas (`migrate_social_security_inputs` in `policyengine_us/tools/social_security_inputs.py`). Both releases give the same total Social Security in 2024.
- 2.2.2 gives `weeks_worked` a formula that starts in 2025 and carries the previous year's value forward, so for 2024 it reads the stored value. 2.154.0 defines it as an input.
- `policyengine_us.spm` in each release lists one column a dataset must supply, `is_spm_independent_minor_role` (`DATASET_SOURCE_INPUTS`), and 21 a dataset must not store (`REJECTED_DATASET_INPUTS`). The dataset stores the first and none of the 21. The comparison checks names only, not stored values.

### Aggregate panel

Each row reports a weighted total in dollars, except three counts: SPM units that receive SNAP, people enrolled in Medicaid, and people in poverty. The table gives the change from `pinned` to `head` for ten of the 20 rows; [`results/comparison.md`](results/comparison.md) lists them all.

One row cannot move between these releases: Social Security in 2024, which equals the stored values under both. Leaving that row out, 13 of the 18 rows with a ratio moved less than 2.5% in 2024, and 14 of 20 did in 2026. The Earned Income Tax Credit in 2026 (shown as +2.5%) and SNAP in 2024 (shown as −2.5%) each moved 2.54% and count among those that moved more.

Medicaid spending rises from $880.02bn to $918.69bn (+4.4%) in both years, while enrollment falls 1.7% in 2024 and rises 0.2% in 2026. The model shares each state's spending total, a parameter, among the people it enrolls, so enrollment does not change the total. 2.154.0 keeps 2.2.2's latest state totals, labels them fiscal 2023, and adds each state's spending for fiscal 2024 (`parameters/calibration/gov/hhs/medicaid/totals/spending.yaml`), which it reads for 2024 and later years.

One 2024 row has no ratio. 2.2.2 puts Medicare's income-related surcharge on Part D premiums (`income_adjusted_part_d_premium_surcharge`) at $0 and 2.154.0 at $3.34bn. The surcharge depends on income from two years earlier. 2.2.2 reads it from 2022, a year this 2024 file has no inputs for, so 2.2.2 sets every surcharge to zero; its own documentation says the value may be zero. 2.154.0 takes the earliest year the file holds and deflates it back. In 2026, when the surcharge reads 2024 income, 2.2.2 gives $3.95bn and 2.154.0 $4.01bn.

| Row | 2024 | 2026 |
|---|---|---|
| Federal income tax | +1.8% | −0.6% |
| Child Tax Credit | +0.8% | +0.9% |
| Earned Income Tax Credit | +0.8% | +2.5% |
| SNAP | −2.5% | −5.4% |
| SSI | −2.1% | −2.0% |
| TANF | −0.1% | +2.7% |
| State income tax | −4.0% | −6.1% |
| Net value of Medicare coverage (`medicare_cost`) | +56.6% | +35.7% |
| Household net income | +0.6% | −1.0% |
| People in poverty under the model's Supplemental Poverty Measure (`person_in_poverty`) | −5.9% | +0.9% |

In dollars and people for 2024: federal income tax rose $41bn, state income tax fell $21bn, and the count of people in poverty fell from 44.3 million to 41.6 million.

The Medicare row compares two definitions, and other rules changed with them. `medicare_cost` estimates, in each release, the value of Medicare coverage net of premiums, and it rose $293bn (+56.6%) in 2024.

- 2.2.2 values spending per enrollee at $11,080 in 2024, a 2021 figure for Parts A and B, and subtracts the Part A and Part B premiums.
- 2.154.0 uses the Centers for Medicare & Medicaid Services' figure for all Medicare spending per enrollee, $16,779 in 2024, 51% more. It also subtracts the average Part D premium and each person's income-related surcharge on Part D.
- 2.154.0 adds conditions on immigration status to Medicare eligibility (`is_medicare_eligible`).
- 2.154.0 also charges the Part B premium only to people enrolled in Part B (`medicare_part_b_enrolled`). That variable defaults to Medicare enrollment, and the dataset stores no Part B enrollment column, so on this file the condition excludes no Medicare enrollee.
- In each release the income-related surcharge on Part B premiums reads the same income as the Part D surcharge, so 2.2.2 puts both at zero in 2024, for the reason above. The panel has no Part B row; Microcosm's scorer measures the Part B surcharge (below).

The panel has no Medicare enrollment row, so it cannot split the rise among these changes, and the two environments also differ in policyengine-core. Each listed change alters the model, not policy or the data.

### Fit to Microcosm's critical calibration targets

Scored on 2026-11-26: [workflow run 45806827463](https://github.com/PolicyEngine/us-model-version-drift/actions/runs/45806827463). It scored both releases with Microcosm's own scorer (`tools/build_us_compatibility_recertification.py score` at microcosm commit `85d513b`), against the target values in the default dataset's published calibration diagnostics. Microcosm calibrated the build to those values; this repository did not rebuild them from the source publications. The default dataset carries that file unchanged from its parent, Microcosm's build P of July 2026 (`populace-us-2024-buildp-sparse-rmloss100-cae8640-20260728T011454Z`), which `parent_release_manifest.json` in the release names. So the build's own estimates in the tables come from build P, which used policyengine-us 1.764.6 and policyengine-core 3.26.11. [`results/critical-targets/critical_targets.md`](results/critical-targets/critical_targets.md) lists every row.

- Both releases keep all 21 scored target rows of Microcosm's 18 exact critical requirements within tolerance. Both also keep within ±25% all 9 national dollar rows of SOI Table 1.4 that the calibration targets include. Each requirement sets its own tolerance, a limit on the absolute relative error, with no allowance for improving on an earlier build.
- These verdicts differ from Microcosm's publication gate, which checks a build's own estimates. The gate lets a row outside tolerance pass for 13 of the 18 exact requirements if it improves on the previous build and stays within ±25%; the verdicts here allow no such exception. The gate also checks a row this scorer cannot reproduce (below).
- Under 2.154.0, federal income tax liability against SOI Historic Table 2 comes closest to its tolerance: +2.1% against ±5%, 2.9 points inside it. 2.2.2 puts that row's error at +0.3% and comes closest to tolerance on Social Security benefits, at −0.4% against ±5%.
- One row has no score. The itemized-deduction requirement also covers the total from SOI Table 4.3 (all returns excluding dependents), and Microcosm's scorer cannot reproduce that row. The requirement's three other rows have scores.
- 8 of the 9 SOI Table 1.4 rows have the same estimate under both releases, to nine significant figures. Only taxable Social Security moves, from −10.9% to −10.5%.
- 13 of the scorer's 14 programme and income totals also appear as rows of this repository's 2024 panel. Each equals the panel's to within one part in 10⁸ under both releases, and a test checks all 13. The scorer runs in batches of households; the panel runs on the whole file. The fourteenth, Medicare's income-related surcharge on Part B premiums, has no panel row. The scorer puts it at $0 under 2.2.2 and $17.38bn under 2.154.0, for the same reason as the Part D surcharge (above).
- 2.154.0 reads one stored column that 2.2.2 does not define, `tax_unit_role_input`. Under 2.2.2, the tax-unit roles the engine assigns differ from the stored ones for 27,382 people (63.1 million weighted); under 2.154.0, for none. Reading that column lowers adjusted gross income under 2.154.0 by $35.8bn: adjusted gross income rises $112.2bn between the releases with it and $148.0bn without it. Reading it also accounts for $1.05bn of the $1.12bn rise in the Child Tax Credit. With it withheld, 2.154.0 still keeps all 30 scored rows within tolerance.
- Microcosm's stored-input check fails under both releases. It refuses the model-named stored columns that the engine does not define and that Microcosm's register of stored non-variable columns does not list: `would_claim_wic` and `medicare_part_b_premiums` under both, and under 2.154.0 also the two mortgage-interest columns.
- Five earlier scoring runs, from 2026-11-18 to 2026-11-23, scored 2.2.2 against 2.144.4, each with an earlier version of this repository's scoring code. The first two installed packages without `envs/score.constraints.txt`, and five package versions differ between those two installs; `results/critical-targets/earlier/` keeps their freezes. The other three installed under that file. For 2.2.2 they gave the same verdict for every row as this run, and every estimate agrees with this run's to within 3 parts in 10¹⁶; a test checks them to 1 part in 10¹⁵. For 2.144.4, with and without `tax_unit_role_input`, the five runs gave one another the same verdicts and agree to within 3 parts in 10¹⁶. The next subsection compares the last run's 2.144.4 scores with this run's 2.154.0 scores.

Every critical row targets a 2024 national total, and IRS Statistics of Income (SOI) or the Social Security Administration supplies each target. Only three targets come from 2024 data: Social Security benefits, from the Social Security Administration's figures for calendar year 2024, and the two EITC targets, from SOI's filing-season statistics for tax year 2024. The other SOI targets come from tax-year 2022 and 2023 publications. None covers Medicare, poverty, Medicaid spending, state income tax or SNAP (the five panel rows with a ratio that moved most in 2024), SSI, Medicare's Part D surcharge (which went from $0 to $3.34bn and so has no ratio), or WIC. Passing these rows therefore leaves those movements untested against outside figures.

Microcosm's combining step checks that the baseline ran under the engine Microcosm built the parent release with; when Microcosm recertifies a release, its baseline runs that engine. Here the baseline runs 2.2.2, so `scripts/critical_targets.py` gives that check 2.2.2's versions. The step uses them for nothing else, so no estimate, tolerance or verdict depends on them.

The scorer needs a Supplemental Poverty Measure (SPM) geography, and the published diagnostics record none. `scripts/prepare_scoring.py` adds `{"geography_kind": "county"}`, the selection in Microcosm's published scoring of an October build and in the `policyengine` bundle. It checks that nothing else in the file changes. No critical target measures poverty.

### What moved between 2.144.4 and 2.154.0

The previous measurement held policyengine-us 2.144.4 and policyengine-core 3.36.1 as head ([README](https://github.com/PolicyEngine/us-model-version-drift/blob/2a03f3e/README.md) and [results](https://github.com/PolicyEngine/us-model-version-drift/tree/2a03f3e/results) at commit `2a03f3e`). `results/earlier/run-44907751024-panel-rows.json` keeps that run's panel rows, and `results/critical-targets/earlier/run-45207756243-rows.json` keeps the scores from Score run 45207756243, which scored 2.144.4. Against that Measure run, on the same dataset, none of the 40 pinned rows moved, and 19 of the 40 head rows stayed the same to every digit. Head changed both packages, so a move can come from either.

- Medicaid spending rose 4.4% in both years, from $880.02bn to $918.69bn. 2.144.4 gave the same total as 2.2.2, so the whole rise since 2.2.2 came with 2.154.0, for the reason the aggregate panel gives.
- 2.154.0 enrolls 0.8% fewer people in Medicaid than 2.144.4 did, in both years (70,967,215 against 71,515,569 in 2024). Between the two releases policyengine-us changed several eligibility rules. 2.154.0 no longer counts undocumented residents of Massachusetts and New York as eligible in every group. It keeps them eligible during pregnancy and the postpartum period in both states and, in New York, at 65 or older, and it gives New York's undocumented children a route to CHIP instead. It denies Medicaid's expansion adult group (42 CFR 435.119) to a parent or caretaker relative whose child under the state's age limit (19, or 21 in New Jersey) has no coverage (435.119(c)). Other changes widen eligibility, such as New Jersey's coverage of children under 19 whatever their immigration status, and rewritten household size and income rules can move it either way. The panel cannot split the fall among these changes, or between them and policyengine-core.
- Every other head row moved less than 0.3%. SNAP in 2026 fell most, by 0.27%.
- The four Medicare rows stayed the same to every digit: `medicare_cost` and the Part D surcharge, in 2024 and 2026. The two releases hold the same Medicare variables and parameter files.
- In the scores, 2.154.0 keeps every scored row within tolerance, as 2.144.4 did. Its estimates for the 30 scored rows differ from 2.144.4's by at most 0.03%.

### Run time

On a GitHub-hosted `ubuntu-latest` runner, one process that builds the simulation and computes one year of the panel took 431 and 448 seconds on 2.2.2, and 593 and 639 seconds on 2.154.0. The runner already held the dataset on disk: an earlier step had downloaded it.

Across this run and the three earlier runs in `results/earlier/` that finished both years, a panel year took 268 to 473 seconds on 2.2.2 and 546 to 812 seconds on the head release (2.144.4 in the earlier runs, 2.154.0 in this one). Within a run, the head release took between 1.2 and 3.0 times as long as 2.2.2.

## What this does not show

- The panel reports movement between two releases. Only the critical-target scoring compares either release with external figures, and only for the rows Microcosm names, in 2024.
- The two environments differ in policyengine-us and in policyengine-core, so a row's movement can come from either package.
- The panel measures how far each total moved between the releases, not why. The README names causes of movements in five places, all above. Scoring 2.154.0 without the stored column it newly reads, `tax_unit_role_input`, measures that column's effect on every scored total. The releases' source shows why 2.2.2 puts both Medicare surcharges at zero in 2024, and why Medicaid spending rose. It shows which Medicare definitions and rules changed, though the panel cannot split the Medicare rise among them. And it shows which Medicaid eligibility rules changed between 2.144.4 and 2.154.0, though the panel cannot split the fall in enrollment among them. The README attributes no other movement to a cause. (The WIC section measures something else: the effect of applying the stored take-up draw within each release.)
- A national total can hide changes that offset each other across households.
- Each release extends the 2024 file to 2026 with its own uprating factors. The 2026 rows therefore mix differences in rules with differences in uprating.
- Two releases, one dataset. Four earlier runs, from 2026-11-17 to 2026-11-21 and under earlier versions of this code, measured the same panel with 2.144.4 as head. The first, 44133383190, stopped partway into 2026 (see the last section). Of the rows they measured, 284 in all, the 140 under 2.2.2 equal this run's in every digit (`results/earlier/`). The other 144 rows came from 2.144.4, and each equals the matching row of the last of those runs in every digit; the subsection on 2.144.4 and 2.154.0 compares that run with this one.
- The lock files fix every package version in both environments. The environments run Python 3.13; `results/*/environment.json` records its patch version, and nothing pins it.

## Method

`scripts/measure.py` runs inside an environment that holds one release. It builds `policyengine_us.Microsimulation()` on the release's default dataset and writes JSON, one part for each process: the column contract, one panel year, WIC as loaded, and WIC with the stored draw applied. `scripts/compare.py` joins two runs. `scripts/rules.py` holds the classification and comparison rules.

Each run writes its workflow run id and the hashes of its measurement code into `environment.json`. `scripts/provenance.py` records a run only if both environments' files name that run and carry the same hashes, and only if every file in `results/pinned` and `results/head`, at any depth, matches the file that run uploaded, byte for byte, with none missing or extra. It records each file's hash.

Every total comes from a real microsimulation run. Each run downloads the dataset from the Hugging Face dataset `policyengine/populace-us` at revision `populace-us-2024-spm-20260915` and checks its hash. It also checks that the release certifies that same hash for its own default dataset. Each release loads its default from the tag `populace-us-2024-spm-20260909` and verifies the file against that hash, so both copies hold the same bytes. This repository stores aggregates and column names, and no records. One cell of the filing-status table in `results/critical-targets/drift.json` counts a single tax unit, so its weighted total equals that unit's weight; the dataset itself publishes every weight.

A run fails if it cannot measure everything. A panel row with no finite value fails its part. So does a stored draw with a missing value or a value other than true or false, or whose ids or ages do not line up, an environment that differs from its lock file, or a release with another default dataset. A part never replaces an existing file, and `scripts/compare.py` refuses an incomplete run and two runs that disagree on what a row measures.

The tests in `tests/` check the rules with property-based tests, and check the committed results:

- The comparison regenerates byte for byte from the two runs' files.
- The measurement code still matches the hashes the run wrote into its files, and both environments' files name the run in `results/provenance.json`.
- Every result file still has the hash `results/provenance.json` records. Recording took those hashes from the run's artifacts; the tests do not download the artifacts again.
- The figures this README takes from `results/` recompute from it (`tests/test_readme.py`).
- Each run installed exactly its lock file.
- Each run measured exactly the panel the code defines.
- The column classes follow from the recorded definitions.
- The earlier runs in `results/earlier/` gave exactly this run's panel rows for 2.2.2, the release both measured.
- The critical-target tables rebuild byte for byte from `drift.json` and three values `critical_targets.json` records (the exact requirement ids, Microcosm's summary and the scoring inputs), every score file still has the hash `results/critical-targets/provenance.json` records, the scores used the measured releases and dataset, and the earlier scoring runs in `results/critical-targets/earlier/` agree with this one for 2.2.2, the release both scored.

## Measure again

The `Measure` workflow builds both environments on GitHub-hosted runners and uploads the results. The recorded run took 37 minutes, from its start to the end of its last job (`results/provenance.json`). It starts on a pull request whenever the measurement code no longer matches the committed results, and by hand:

```bash
gh workflow run measure.yml --ref <branch>
```

Then replace `results/pinned` and `results/head` with the run's `results-pinned` and `results-head` artifacts, record the run and rebuild the comparison. Recording downloads the run's artifacts and fails unless the committed files, at any depth, match them exactly:

```bash
python scripts/provenance.py record measure --run <run id>
```

```bash
python scripts/compare.py results/pinned results/head --out results
```

`results/provenance.json` records the run's commit, its start time and the time its last job finished, read from GitHub, and the hash of each result file.

## Score again

The `Score` workflow runs Microcosm's scorer on GitHub-hosted runners: each release as stored, and the head release without the stored columns it newly reads. The recorded run took 12 minutes, from its start to the end of its last job (`results/critical-targets/provenance.json`). It starts on a pull request whenever the scoring code no longer matches the committed scores, and by hand:

```bash
gh workflow run score.yml --ref <branch>
```

Before any download, each job checks that both committed measurements read the dataset `scripts/prepare_scoring.py` pins (its hash, file and repository, and a revision that names the pinned release folder), and then downloads from that folder. A measurement on another dataset stops the run before it scores anything. The counterfactual job scores only when the head release newly reads a stored column; otherwise it records its environment and inputs and scores nothing. The combining step refuses a counterfactual that would withhold a column the baseline also reads, and refuses an output folder that already exists.

Then replace the files in `results/critical-targets` (keeping `earlier/`) with the run's `results-critical-targets` artifact, and record the run. Recording downloads the run's artifact and fails unless the committed files, at any depth except `earlier/`, match its files exactly:

```bash
python scripts/provenance.py record score --run <run id>
```

The scores also go stale when the measured releases or dataset change, and a test then fails until a new run replaces them.

The tables rebuild without Microcosm from `drift.json` and three values `critical_targets.json` records (the exact requirement ids, Microcosm's summary and the scoring inputs), and a test checks that they match byte for byte:

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
