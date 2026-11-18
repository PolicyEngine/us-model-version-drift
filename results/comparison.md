# Comparison

- Baseline (`pinned`): policyengine-us 2.2.2, policyengine-core 3.34.10, spm-calculator 1.1.0
- Tested (`head`): policyengine-us 2.144.4, policyengine-core 3.36.1, spm-calculator 1.1.0
- Dataset: `populace_us_2024.h5` at `populace-us-2024-spm-20260915`, sha256 `6496cc4393d4…`, the same bytes in both runs

## Column contract

The dataset stores 377 distinct columns across six tables.

| Class | Baseline | Tested |
|---|---|---|
| input_variable | 184 | 180 |
| computed_variable | 4 | 7 |
| not_a_variable | 26 | 27 |
| raw_field | 163 | 163 |

Model-named columns only the tested release does not define (2): `first_home_mortgage_interest`, `second_home_mortgage_interest`

Model-named columns only the baseline does not define (1): `tax_unit_role_input`

Model-named columns neither defines (25): `family_source_id`, `family_support_channel`, `family_support_clone_index`, `filing_status_input`, `household_source_id`, `household_support_channel`, `household_support_clone_index`, `marital_unit_source_id`, `marital_unit_support_channel`, `marital_unit_support_clone_index`, `medicare_part_b_premiums`, `person_source_id`, `person_support_channel`, `person_support_clone_index`, `source_household_id`, `source_person_id`, `source_row_id`, `source_year`, `spm_unit_source_id`, `spm_unit_support_channel`, `spm_unit_support_clone_index`, `tax_unit_source_id`, `tax_unit_support_channel`, `tax_unit_support_clone_index`, `would_claim_wic`

Stored columns that are not variables of the release, raw fields included: 189 (baseline), 190 (tested).

Stored columns the release computes (it has a formula for the variable, or adds or subtracts others):

- Baseline (4): `has_marketplace_health_coverage`, `is_spm_independent_minor_role`, `person_id`, `weeks_worked`
- Tested (7): `has_marketplace_health_coverage`, `is_spm_independent_minor_role`, `person_id`, `social_security_dependents`, `social_security_disability`, `social_security_retirement`, `social_security_survivors`

Tested release's own declarations: required source inputs missing from the data: none; stored columns it says a dataset must not store: none.

Baseline release's own declarations: required source inputs missing from the data: none; stored columns it says a dataset must not store: none.

## WIC take-up

| | Baseline | Tested |
|---|---|---|
| `would_claim_wic` is a variable | no | no |
| WIC, 2024, as the release loads the data | 11.52bn | 11.31bn |
| Take-up input share true, as loaded (January 2024, weighted) | 100.0% | 100.0% |
| WIC, 2024, with the stored draw applied | 6.63bn | 6.47bn |
| Take-up input share true, stored draw applied | 3.8% | 3.8% |
| As loaded minus stored draw | 4.88bn | 4.84bn |
| As loaded, relative to stored draw | +73.63% | +74.82% |

## Panel, 2024

| Row | Variable | Baseline | Tested | Difference | Relative |
|---|---|---|---|---|---|
| income_tax_net | `income_tax` | 2,262.60bn | 2,303.82bn | 41.22bn | +1.82% |
| ctc_total | `ctc` | 147.54bn | 148.66bn | 1.12bn | +0.76% |
| eitc_total | `eitc` | 66.61bn | 67.13bn | 0.51bn | +0.77% |
| social_security_total | `social_security` | 1,464.84bn | 1,464.84bn | 0 | +0.00% |
| snap_total | `snap` | 101.95bn | 99.54bn | -2.41bn | -2.36% |
| snap_units | `snap` | 23,408,655 | 23,579,609 | 170,954 | +0.73% |
| ssi_total | `ssi` | 56.10bn | 54.89bn | -1.20bn | -2.14% |
| medicaid_enrollment | `medicaid_enrolled` | 72,205,082 | 71,515,569 | -689,513 | -0.95% |
| medicaid_total | `medicaid` | 880.02bn | 880.02bn | -11,745 | -0.00% |
| state_income_tax_total | `state_income_tax` | 536.19bn | 515.01bn | -21.18bn | -3.95% |
| medicare_part_d_irmaa_total | `income_adjusted_part_d_premium_surcharge` | 0 | 3.34bn | 3.34bn | n/a |
| medicare_cost_total | `medicare_cost` | 516.73bn | 809.45bn | 292.72bn | +56.65% |
| adjusted_gross_income_total | `adjusted_gross_income` | 16,683.14bn | 16,795.34bn | 112.20bn | +0.67% |
| wic_total | `wic` | 11.52bn | 11.31bn | -0.21bn | -1.79% |
| tanf_total | `tanf` | 5.07bn | 5.06bn | -6,895,669 | -0.14% |
| refundable_ctc_total | `refundable_ctc` | 37.50bn | 37.23bn | -0.26bn | -0.70% |
| employee_payroll_tax_total | `employee_payroll_tax` | 757.47bn | 759.86bn | 2.39bn | +0.32% |
| premium_tax_credit_total | `premium_tax_credit` | 60.06bn | 60.12bn | 65,420,713 | +0.11% |
| household_net_income_total | `household_net_income` | 15,184.28bn | 15,270.73bn | 86.45bn | +0.57% |
| people_in_spm_poverty | `person_in_poverty` | 44,271,756 | 41,545,640 | -2,726,116 | -6.16% |

## Panel, 2026

| Row | Variable | Baseline | Tested | Difference | Relative |
|---|---|---|---|---|---|
| income_tax_net | `income_tax` | 2,610.60bn | 2,595.02bn | -15.58bn | -0.60% |
| ctc_total | `ctc` | 157.47bn | 158.86bn | 1.40bn | +0.89% |
| eitc_total | `eitc` | 68.27bn | 70.00bn | 1.73bn | +2.54% |
| social_security_total | `social_security` | 1,705.55bn | 1,677.87bn | -27.67bn | -1.62% |
| snap_total | `snap` | 100.27bn | 95.10bn | -5.17bn | -5.15% |
| snap_units | `snap` | 22,196,344 | 22,593,839 | 397,495 | +1.79% |
| ssi_total | `ssi` | 57.86bn | 56.69bn | -1.16bn | -2.01% |
| medicaid_enrollment | `medicaid_enrolled` | 70,168,489 | 70,842,956 | 674,467 | +0.96% |
| medicaid_total | `medicaid` | 880.02bn | 880.02bn | 14,506 | +0.00% |
| state_income_tax_total | `state_income_tax` | 613.77bn | 576.64bn | -37.14bn | -6.05% |
| medicare_part_d_irmaa_total | `income_adjusted_part_d_premium_surcharge` | 3.95bn | 4.01bn | 56,375,305 | +1.43% |
| medicare_cost_total | `medicare_cost` | 684.16bn | 928.08bn | 243.92bn | +35.65% |
| adjusted_gross_income_total | `adjusted_gross_income` | 19,158.61bn | 18,986.98bn | -171.63bn | -0.90% |
| wic_total | `wic` | 11.77bn | 11.79bn | 26,466,678 | +0.22% |
| tanf_total | `tanf` | 5.05bn | 5.18bn | 0.14bn | +2.71% |
| refundable_ctc_total | `refundable_ctc` | 40.62bn | 40.62bn | -2,522,467 | -0.01% |
| employee_payroll_tax_total | `employee_payroll_tax` | 852.13bn | 840.52bn | -11.61bn | -1.36% |
| premium_tax_credit_total | `premium_tax_credit` | 46.44bn | 47.24bn | 0.79bn | +1.71% |
| household_net_income_total | `household_net_income` | 17,426.29bn | 17,245.96bn | -180.33bn | -1.03% |
| people_in_spm_poverty | `person_in_poverty` | 47,132,501 | 47,599,202 | 466,701 | +0.99% |

