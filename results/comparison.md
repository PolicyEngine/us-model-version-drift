# Comparison

- Baseline (`pinned`): policyengine-us 2.2.2, policyengine-core 3.34.10, spm-calculator 1.1.0
- Tested (`head`): policyengine-us 2.154.0, policyengine-core 3.37.2, spm-calculator 1.1.0
- Dataset: `populace_us_2024.h5` at `populace-us-2024-spm-20260915`, sha256 `6496cc4393d4…`, the same bytes in both runs

## Column contract

The dataset stores 377 distinct columns across six tables.

| Class | Baseline | Tested |
|---|---|---|
| input_variable | 184 | 180 |
| computed_variable | 4 | 7 |
| not_a_variable | 26 | 27 |
| raw_field | 163 | 163 |

The classes describe how each release defines a stored column's name. They do not show what the loader does with the column: policyengine-core can load stored values for a variable that has a formula.

Model-named columns only the tested release does not define (2): `first_home_mortgage_interest`, `second_home_mortgage_interest`

Model-named columns only the baseline does not define (1): `tax_unit_role_input`

Model-named columns neither defines (25): `family_source_id`, `family_support_channel`, `family_support_clone_index`, `filing_status_input`, `household_source_id`, `household_support_channel`, `household_support_clone_index`, `marital_unit_source_id`, `marital_unit_support_channel`, `marital_unit_support_clone_index`, `medicare_part_b_premiums`, `person_source_id`, `person_support_channel`, `person_support_clone_index`, `source_household_id`, `source_person_id`, `source_row_id`, `source_year`, `spm_unit_source_id`, `spm_unit_support_channel`, `spm_unit_support_clone_index`, `tax_unit_source_id`, `tax_unit_support_channel`, `tax_unit_support_clone_index`, `would_claim_wic`

Stored columns that are not variables of the release, raw fields included: 189 (baseline), 190 (tested).

Stored columns whose variable the release defines as computed (policyengine-core's `is_input_variable()` is false for it):

- Baseline (4): `has_marketplace_health_coverage`, `is_spm_independent_minor_role`, `person_id`, `weeks_worked`
- Tested (7): `has_marketplace_health_coverage`, `is_spm_independent_minor_role`, `person_id`, `social_security_dependents`, `social_security_disability`, `social_security_retirement`, `social_security_survivors`

Tested release, the two lists in `policyengine_us.spm`, checked by column name: `DATASET_SOURCE_INPUTS` names missing from the data: none; `REJECTED_DATASET_INPUTS` names the data stores: none.

Baseline release, the two lists in `policyengine_us.spm`, checked by column name: `DATASET_SOURCE_INPUTS` names missing from the data: none; `REJECTED_DATASET_INPUTS` names the data stores: none.

## WIC take-up

| | Baseline | Tested |
|---|---|---|
| `would_claim_wic` is a variable | no | no |
| WIC, 2024, as the release loads the data | $11.52bn | $11.31bn |
| WIC, 2024, with the stored draw applied | $6.63bn | $6.47bn |
| Take-up input true, as loaded: share of all people, person-weighted, January 2024 | 100.00% | 100.00% |
| Take-up input true, stored draw applied: share of all people, person-weighted, January 2024 | 3.80% | 3.80% |
| Stored draw true: share of stored person rows, unweighted | 4.49% | 4.49% |
| People in the simulation | 166,321 | 166,321 |
| Stored person rows | 166,321 | 166,321 |
| As loaded minus stored draw | $4.88bn | $4.84bn |
| As loaded, relative to stored draw | +73.63% | +74.82% |

The stored draw is matched to the simulation's people on `person_id`. The measurement stops unless each side's ids are unique and the two sides hold the same ids.

## Panel, 2024

| Row | Variable | Unit | Baseline | Tested | Difference | Relative |
|---|---|---|---|---|---|---|
| income_tax_net | `income_tax` | dollars | $2,262.60bn | $2,303.82bn | $41.22bn | +1.82% |
| ctc_total | `ctc` | dollars | $147.54bn | $148.66bn | $1.12bn | +0.76% |
| eitc_total | `eitc` | dollars | $66.61bn | $67.13bn | $0.51bn | +0.77% |
| social_security_total | `social_security` | dollars | $1,464.84bn | $1,464.84bn | $0.00bn | +0.00% |
| snap_total | `snap` | dollars | $101.95bn | $99.36bn | −$2.59bn | −2.54% |
| snap_units | `snap` | SPM units | 23.41m | 23.55m | 0.14m | +0.60% |
| ssi_total | `ssi` | dollars | $56.10bn | $54.89bn | −$1.20bn | −2.14% |
| medicaid_enrollment | `medicaid_enrolled` | people | 72.21m | 70.97m | −1.24m | −1.71% |
| medicaid_total | `medicaid` | dollars | $880.02bn | $918.69bn | $38.67bn | +4.39% |
| state_income_tax_total | `state_income_tax` | dollars | $536.19bn | $514.94bn | −$21.25bn | −3.96% |
| medicare_part_d_irmaa_total | `income_adjusted_part_d_premium_surcharge` | dollars | $0.00bn | $3.34bn | $3.34bn | n/a |
| medicare_cost_total | `medicare_cost` | dollars | $516.73bn | $809.45bn | $292.72bn | +56.65% |
| adjusted_gross_income_total | `adjusted_gross_income` | dollars | $16,683.14bn | $16,795.34bn | $112.20bn | +0.67% |
| wic_total | `wic` | dollars | $11.52bn | $11.31bn | −$0.21bn | −1.79% |
| tanf_total | `tanf` | dollars | $5.07bn | $5.06bn | −$0.01bn | −0.14% |
| refundable_ctc_total | `refundable_ctc` | dollars | $37.50bn | $37.23bn | −$0.26bn | −0.70% |
| employee_payroll_tax_total | `employee_payroll_tax` | dollars | $757.47bn | $759.86bn | $2.39bn | +0.32% |
| premium_tax_credit_total | `premium_tax_credit` | dollars | $60.06bn | $60.12bn | $0.07bn | +0.11% |
| household_net_income_total | `household_net_income` | dollars | $15,184.28bn | $15,270.60bn | $86.32bn | +0.57% |
| people_in_spm_poverty | `person_in_poverty` | people | 44.27m | 41.64m | −2.63m | −5.95% |

## Panel, 2026

| Row | Variable | Unit | Baseline | Tested | Difference | Relative |
|---|---|---|---|---|---|---|
| income_tax_net | `income_tax` | dollars | $2,610.60bn | $2,595.03bn | −$15.57bn | −0.60% |
| ctc_total | `ctc` | dollars | $157.47bn | $158.86bn | $1.40bn | +0.89% |
| eitc_total | `eitc` | dollars | $68.27bn | $70.00bn | $1.73bn | +2.54% |
| social_security_total | `social_security` | dollars | $1,705.55bn | $1,677.87bn | −$27.67bn | −1.62% |
| snap_total | `snap` | dollars | $100.27bn | $94.84bn | −$5.42bn | −5.41% |
| snap_units | `snap` | SPM units | 22.20m | 22.60m | 0.40m | +1.81% |
| ssi_total | `ssi` | dollars | $57.86bn | $56.69bn | −$1.16bn | −2.01% |
| medicaid_enrollment | `medicaid_enrolled` | people | 70.17m | 70.30m | 0.13m | +0.19% |
| medicaid_total | `medicaid` | dollars | $880.02bn | $918.69bn | $38.67bn | +4.39% |
| state_income_tax_total | `state_income_tax` | dollars | $613.77bn | $576.42bn | −$37.36bn | −6.09% |
| medicare_part_d_irmaa_total | `income_adjusted_part_d_premium_surcharge` | dollars | $3.95bn | $4.01bn | $0.06bn | +1.43% |
| medicare_cost_total | `medicare_cost` | dollars | $684.16bn | $928.08bn | $243.92bn | +35.65% |
| adjusted_gross_income_total | `adjusted_gross_income` | dollars | $19,158.61bn | $18,986.98bn | −$171.63bn | −0.90% |
| wic_total | `wic` | dollars | $11.77bn | $11.79bn | $0.03bn | +0.22% |
| tanf_total | `tanf` | dollars | $5.05bn | $5.18bn | $0.14bn | +2.71% |
| refundable_ctc_total | `refundable_ctc` | dollars | $40.62bn | $40.62bn | −$0.00bn | −0.01% |
| employee_payroll_tax_total | `employee_payroll_tax` | dollars | $852.13bn | $840.52bn | −$11.61bn | −1.36% |
| premium_tax_credit_total | `premium_tax_credit` | dollars | $46.44bn | $47.24bn | $0.79bn | +1.71% |
| household_net_income_total | `household_net_income` | dollars | $17,426.29bn | $17,245.92bn | −$180.37bn | −1.04% |
| people_in_spm_poverty | `person_in_poverty` | people | 47.13m | 47.57m | 0.44m | +0.93% |

