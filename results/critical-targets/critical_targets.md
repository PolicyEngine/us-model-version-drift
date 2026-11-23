# Critical targets

- Baseline: policyengine-us 2.2.2, policyengine-core 3.34.10, spm-calculator 1.1.0
- Tested: policyengine-us 2.144.4, policyengine-core 3.36.1, spm-calculator 1.1.0
- Dataset sha256 `6496cc4393d4…`, 57,240 households, period 2024
- Targets and tolerances: the dataset's published calibration diagnostics and Microcosm's critical-target requirements at commit `85d513bb550f`
- Build estimates: Microcosm build `populace-us-2024-buildp-sparse-rmloss100-cae8640-20260728T011454Z`, made with policyengine-us 1.764.6 and policyengine-core 3.26.11. The dataset carries that build's calibration diagnostics unchanged.
- Stored columns the tested engine newly reads: `tax_unit_role_input`

## The 18 exact requirements

21 scored target rows serve the 18 requirements: a requirement can select rows from more than one publication. Within tolerance: 21 under the baseline, 21 under the tested release.

| Requirement | Source | Target | Build estimate | Baseline | Tested | Tolerance | Baseline within | Tested within |
|---|---|---|---|---|---|---|---|---|
| federal_income_tax_amount | `irs_soi ty2022 historic_table_2` | $2,358.7bn | $2,361.5bn (+0.1%) | $2,366.4bn (+0.3%) | $2,407.8bn (+2.1%) | ±5% | in | in |
| income_tax_liability_returns | `irs_soi ty2022 historic_table_2` | 113.56m | 113.20m (-0.3%) | 113.27m (-0.3%) | 113.19m (-0.3%) | ±15% | in | in |
| social_security_benefits | `ssa_supplement cy2024 oasdi_ssi_payments` | $1,471.2bn | $1,464.8bn (-0.4%) | $1,464.8bn (-0.4%) | $1,464.8bn (-0.4%) | ±5% | in | in |
| ctc_amount | `irs_soi ty2022 historic_table_2` | $92.8bn | $89.2bn (-3.9%) | $89.3bn (-3.8%) | $89.7bn (-3.4%) | ±15% | in | in |
| ctc_claims | `irs_soi ty2022 historic_table_2` | 38.07m | 37.97m (-0.3%) | 37.99m (-0.2%) | 38.54m (+1.2%) | ±15% | in | in |
| actc_amount | `irs_soi ty2022 historic_table_2` | $37.9bn | $37.6bn (-0.8%) | $37.5bn (-1.2%) | $37.2bn (-1.8%) | ±15% | in | in |
| actc_claims | `irs_soi ty2022 historic_table_2` | 17.69m | 17.69m (-0.0%) | 17.64m (-0.3%) | 17.57m (-0.7%) | ±15% | in | in |
| eitc_amount | `irs_soi ty2024 filing_season_week47` | $69.0bn | $66.8bn (-3.3%) | $66.6bn (-3.5%) | $67.1bn (-2.8%) | ±15% | in | in |
| eitc_claims | `irs_soi ty2024 filing_season_week47` | 23.84m | 23.69m (-0.6%) | 23.61m (-1.0%) | 23.20m (-2.7%) | ±15% | in | in |
| premium_tax_credit_amount | `irs_soi ty2022 historic_table_2` | $60.4bn | $60.4bn (-0.0%) | $60.1bn (-0.6%) | $60.1bn (-0.5%) | ±15% | in | in |
| premium_tax_credit_returns | `irs_soi ty2022 historic_table_2` | 7.84m | 8.01m (+2.1%) | 7.97m (+1.6%) | 7.93m (+1.1%) | ±15% | in | in |
| taxable_social_security_amount | `irs_soi ty2022 historic_table_2` | $510.8bn | $509.8bn (-0.2%) | $510.8bn (+0.0%) | $513.1bn (+0.5%) | ±15% | in | in |
| taxable_social_security_returns | `irs_soi ty2022 historic_table_2` | 24.48m | 24.47m (-0.0%) | 24.49m (+0.1%) | 24.59m (+0.5%) | ±15% | in | in |
| itemized_deduction_amount | `irs_soi ty2022 historic_table_2` | $728.8bn | $724.6bn (-0.6%) | $720.5bn (-1.1%) | $722.1bn (-0.9%) | ±15% | in | in |
| itemized_deduction_amount | `irs_soi ty2023 table_1_2` | $751.1bn | $724.6bn (-3.5%) | $720.5bn (-4.1%) | $722.1bn (-3.9%) | ±15% | in | in |
| itemized_deduction_amount | `irs_soi ty2023 table_2_1` | $751.1bn | $724.6bn (-3.5%) | $720.5bn (-4.1%) | $722.1bn (-3.9%) | ±15% | in | in |
| salt_deduction_amount | `irs_soi ty2022 historic_table_2` | $137.4bn | $132.4bn (-3.7%) | $131.7bn (-4.1%) | $131.8bn (-4.1%) | ±10% | in | in |
| salt_deduction_amount | `irs_soi ty2023 table_2_1` | $131.6bn | $132.4bn (+0.6%) | $131.7bn (+0.1%) | $131.8bn (+0.1%) | ±10% | in | in |
| medical_expense_deduction_amount | `irs_soi ty2022 historic_table_2` | $89.9bn | $99.1bn (+10.3%) | $98.8bn (+9.9%) | $99.1bn (+10.3%) | ±25% | in | in |
| home_mortgage_interest_amount | `irs_soi ty2023 table_2_1` | $186.3bn | $186.3bn (-0.0%) | $183.7bn (-1.4%) | $184.3bn (-1.1%) | ±20% | in | in |
| home_mortgage_interest_returns | `irs_soi ty2023 table_2_1` | 11.64m | 11.64m (+0.0%) | 11.57m (-0.6%) | 11.62m (-0.2%) | ±15% | in | in |

Each estimate's error against the target follows it in brackets.

Smallest margin under the tested release: federal_income_tax_amount (`irs_soi ty2022 historic_table_2`), 2.9 percentage points inside its tolerance.

Requirements with no scored row: none.

Critical target rows the scorer did not score (1): itemized_deduction_amount (`irs_soi.ty2023.table_4_3.all_returns_excluding_dependents.all.itemized_deductions_amount@2024`).

## SOI Table 1.4 national dollar rows

9 scored rows, tolerance ±25%. Within tolerance: 9 under the baseline, 9 under the tested release. 8 of the 9 rows have the same estimate under both releases, to nine significant figures.

| Row | Target | Baseline | Tested | Baseline within | Tested within |
|---|---|---|---|---|---|
| wages_salaries_amount | $10,773.4bn | $10,736.3bn (-0.3%) | $10,736.3bn (-0.3%) | in | in |
| net_capital_gains_amount | $1,270.9bn | $1,235.4bn (-2.8%) | $1,235.4bn (-2.8%) | in | in |
| taxable_ira_distributions_amount | $476.4bn | $485.1bn (+1.8%) | $485.1bn (+1.8%) | in | in |
| taxable_pension_income_amount | $1,013.4bn | $1,001.7bn (-1.2%) | $1,001.7bn (-1.2%) | in | in |
| unemployment_compensation_amount | $33.6bn | $33.5bn (-0.3%) | $33.5bn (-0.3%) | in | in |
| taxable_social_security_amount | $573.0bn | $510.8bn (-10.9%) | $513.1bn (-10.5%) | in | in |
| capital_gain_distributions_amount | $10.2bn | $10.2bn (+0.0%) | $10.2bn (+0.0%) | in | in |
| estate_trust_net_income_amount | $52.1bn | $52.1bn (+0.0%) | $52.1bn (+0.0%) | in | in |
| estate_trust_net_loss_amount | $5.3bn | $5.3bn (-0.1%) | $5.3bn (-0.1%) | in | in |

## What each engine does with the stored columns

- Baseline: Microcosm's stored-input check failed. It refuses the model-named stored columns that this engine does not define and that Microcosm's register of stored non-variable columns does not list: `medicare_part_b_premiums`, `would_claim_wic`.
- Tested: Microcosm's stored-input check failed. It refuses the model-named stored columns that this engine does not define and that Microcosm's register of stored non-variable columns does not list: `first_home_mortgage_interest`, `medicare_part_b_premiums`, `second_home_mortgage_interest`, `would_claim_wic`.

People whose tax-unit role in the engine differs from the stored role:

- Baseline: 27,382 of 166,321 people (63.1m weighted), in 14,412 tax units (33.3m weighted)
- Tested: 0 of 166,321 people (0.0m weighted), in 0 tax units (0.0m weighted)

## Programme and income totals the scorer also reports

Row labels are Microcosm's. Its Medicare benefit cost is `medicare_cost`, which each release defines as the value of Medicare coverage net of premiums. The last column is the part of the change that comes from the stored columns the tested engine newly reads.

| Row | Baseline | Tested | Relative | From newly read columns |
|---|---|---|---|---|
| federal income tax, net of refundable credits | $2,262.6bn | $2,303.8bn | +1.8% | -$1.5bn |
| Child Tax Credit, total | $147.5bn | $148.7bn | +0.8% | $1.1bn |
| Earned Income Tax Credit, total | $66.6bn | $67.1bn | +0.8% | -$0.4bn |
| Social Security benefits | $1,464.8bn | $1,464.8bn | +0.0% | $0.0bn |
| SNAP benefits | $101.9bn | $99.5bn | -2.4% | -$0.0bn |
| SPM units receiving SNAP | 23.41m | 23.58m | +0.7% | 0.00m |
| SSI payments | $56.1bn | $54.9bn | -2.1% | $0.0bn |
| people enrolled in Medicaid | 72.21m | 71.52m | -1.0% | 0.01m |
| Medicaid benefit value | $880.0bn | $880.0bn | -0.0% | $0.0bn |
| state income tax | $536.2bn | $515.0bn | -4.0% | -$0.6bn |
| Medicare Part B income-related premium (IRMAA) | $0.0bn | $17.4bn | n/a | $0.0bn |
| Medicare Part D income-related surcharge | $0.0bn | $3.3bn | n/a | $0.0bn |
| Medicare benefit cost | $516.7bn | $809.5bn | +56.6% | -$0.0bn |
| adjusted gross income | $16,683.1bn | $16,795.3bn | +0.7% | -$35.8bn |

