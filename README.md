# Distributor Sales Customer 360 - Python QA Automation

Assignment 2, Submission 2: Test Design and Automation Build.

The framework reconciles three distributor sales sources with the
`dm_distributor_sales_customer_360` data mart in the `python_project2` MySQL
database. It runs **72 validations** across five layers and writes a
validation summary, a record-level mismatch report, an executive report and
execution logs.

---

## 1. What it validates

The lab pipeline is:

```
Fact_Sales_50k_CSV.csv          -> fact_sales             --+  join on distributor_txn_id
dim_Distributor_sales_50k.json  -> dim_distributor_sales  --+
dim_Customer_Master_50k.txt     -> dim_customer_master    --+  join on customer_key
                                                             |
                    APPROVED only + 9 derived columns -> dm_distributor_sales_customer_360
```

| Layer (guideline) | Meaning in this lab | IDs | Checks |
|---|---|---|---|
| Source-to-Staging | Each input file against its loaded MySQL table: layout, counts, keys, every field | SRC-V01 to V15 | 15 |
| Data Quality | Mandatory fields, duplicates, invalid amounts and dates, allowed values, customer and product references | DQ-V01 to V17 | 17 |
| Staging-to-Data Mart | Status filter, record reconciliation, carried columns, customer enrichment, derived columns, business rules | DM-V01 to V18, BR-V01 to V09 | 27 |
| Aggregate Model | Totals, insurance premium, mutual fund sales, average ticket size, summaries by product, region, day, distributor | AGG-V01 to V08 | 8 |
| Data Mart-to-Reporting | Executive report metrics recomputed with independent SQL in MySQL | RPT-V01 to V05 | 5 |

Section 4 of the Submission 2 guideline lists Retail CSV, Online API,
`stg_*` tables and dashboards. Those belong to a different pipeline and do
not exist in this lab, so the five layers are mapped onto the real objects
as shown above.

---

## 2. Project structure

```
financial_sales_qa_project/
├── config/
│   ├── db_config.yaml            MySQL host, database, user, table names (no password)
│   ├── validation_rules.yaml     file paths, schemas, keys, mandatory fields, allowed values,
│   │                             tolerances, date formats, column mappings
│   └── business_rules.yaml       status filter, product derivation, calculation rules
├── data/README.md                where the input files are read from
├── src/
│   ├── main.py                   entry point and run orchestration
│   ├── config_loader.py          YAML loading + environment overrides
│   ├── context.py                loads each dataset once; turns load failures into ERROR results
│   ├── normalise.py              text / number / date normalisation for comparison
│   ├── result.py                 ValidationResult and the check registry
│   ├── logger.py                 console, execution.log, error.log
│   ├── connectors/
│   │   ├── mysql_connector.py    read-only MySQL (SELECT only)
│   │   ├── file_connector.py     delimited text and CSV
│   │   └── json_connector.py     JSON array of records
│   ├── validators/
│   │   ├── count_validator.py            counts and schema/layout
│   │   ├── duplicate_validator.py        duplicate keys
│   │   ├── null_validator.py             mandatory fields and completeness
│   │   ├── customer_validator.py         customer reference and enrichment
│   │   ├── reconciliation_validator.py   key sets and field-level comparison
│   │   ├── transformation_validator.py   derived columns
│   │   ├── business_rule_validator.py    calculations, product rules, value validity
│   │   ├── aggregate_validator.py        totals and summaries
│   │   └── report_validator.py           report metrics vs SQL
│   └── reports/
│       ├── report_writer.py      validation_summary.csv, executive_qa_report.txt
│       └── mismatch_report.py    mismatch_report.csv
├── profiling/profile_data.py     full-volume profiling queries used to confirm the rules
├── output/
│   ├── logs/                     execution.log, error.log
│   └── validation_reports/       validation_summary.csv, mismatch_report.csv, executive_qa_report.txt
├── tests/
│   ├── test_count.py  test_duplicates.py  test_nulls.py
│   ├── test_customer_reference.py  test_reconciliation.py  test_business_rules.py
│   ├── test_end_to_end.py        full run on a seeded replica
│   └── demo/                     offline replica (SQLite + generated files)
├── requirements.txt
└── README.md
```

---

## 3. Setup on the lab VM

```powershell
cd C:\qa-lab\python-project-2\learner
git clone <repository url> financial_sales_qa_project
cd financial_sales_qa_project
python -m pip install -r requirements.txt
```

`mysql-connector-python` and `pandas` are already installed on the lab VM;
`PyYAML` and `pytest` may need installing.

Set the database password for the current PowerShell window. It is never
stored in a file:

```powershell
$env:P2_DB_PASSWORD = '<learner password from the lab guide>'
```

Other settings can be overridden the same way without editing YAML:
`P2_DB_HOST`, `P2_DB_PORT`, `P2_DB_NAME`, `P2_DB_USER`, `P2_INPUT_DIR`,
`P2_OUTPUT_DIR`.

---

## 4. Running

```powershell
python -m src.main                      # all 72 validations (about 1-2 minutes at 50,000 rows)
python -m src.main --layer source       # one layer: source | dq | datamart | aggregate | reporting
python -m src.main --layer dq --layer datamart
python -m pytest -q                     # 43 unit and end-to-end tests (no database needed)
python -m tests.demo.run_offline_demo   # full run on the offline replica, output in tests/demo/_output
```

Exit code: `0` all checks passed, `1` at least one FAIL or ERROR,
`2` configuration error.

### Status values

| Status | Meaning |
|---|---|
| PASS | The rule holds |
| FAIL | A data defect or rule break, with evidence in the remarks and mismatch report |
| ERROR | The check could not run (file missing, database unreachable, unexpected format). Not a data defect |
| SKIPPED | Nothing to evaluate, with the reason. Example: customer attributes cannot be compared because no row resolves to a customer |

The guideline asks for PASS/FAIL. ERROR and SKIPPED are added so that an
environment problem or a dependency on a failed check is never reported as
a data defect or as a pass.

---

## 5. Outputs

| File | Content |
|---|---|
| `output/validation_reports/validation_summary.csv` | One row per validation: ID, layer, name, source, target, expected, actual, status, variance, remarks, severity, risk reference |
| `output/validation_reports/mismatch_report.csv` | Record-level evidence: validation ID, record key, field, expected (source), actual (target), issue. Capped at 100 rows per validation (`output.max_mismatch_rows_per_check`); totals are in the remarks |
| `output/validation_reports/executive_qa_report.txt` | Run details, results by layer, every FAIL / ERROR / SKIPPED with its reason, data mart metrics |
| `output/logs/execution.log` | Start time, each check and its result, outputs written |
| `output/logs/error.log` | Load failures and unexpected exceptions with tracebacks |

---

## 6. Design

- **Connectors are separate from validations.** Validations receive
  DataFrames, so the same check runs on a file, a table or test data.
- **Reusable primitives.** `compare_counts`, `find_duplicate_keys`,
  `null_counts`, `compare_key_sets`, `compare_fields`, `derive_family` and
  `compare_summaries` are written once and unit-tested.
- **Configuration-driven.** File names, table names, schemas, mappings,
  tolerances, allowed values and rules are in YAML. The lab names differ
  from the lab guide, which this absorbs without code changes.
- **Normalise before comparing.** Files hold text (`"50310.96"`,
  `"1/5/2026 9:30"`); MySQL returns `Decimal`, `date` and `datetime`.
  Values are converted to a common form first, so only genuine differences
  are reported.
- **Error handling.** Each dataset loads once. If a file or the database
  is unavailable, the checks that need it report ERROR with the reason and
  the rest still run. Verified: with the database down, the 5 file-only
  checks still run; with the files missing, the 58 database checks still run.
- **Read-only.** The MySQL connector refuses anything but `SELECT`.
- **Profile before asserting.** The rules were confirmed against all
  50,000 rows (`profiling/profile_data.py`) before any check was written.

---

## 7. Proof the checks work

`tests/demo/build_demo_data.py` builds a replica of the lab (files plus a
SQLite database) seeded with the defects found by profiling.
`tests/test_end_to_end.py` asserts the run reports exactly those 9 FAILs and
3 SKIPPEDs, with no ERROR. Unit tests seed one break per rule and assert it
is caught. At full lab volume (50,000 rows per source) the replica run takes
about 80 seconds.

---

## 8. Assumptions

1. The input files are the source of truth; the MySQL source tables are their loaded copies.
2. `distributor_txn_id` is the business key across sales sources and the target.
3. Only `APPROVED` transactions belong in the target (confirmed: 45,076 = 45,076).
4. `customer_key` is the intended customer join key (it is the target column the pipeline populates).
5. Rules inferred from data, not documentation: product family from the `product_code` prefix,
   `is_high_value_flag = Y` when gross >= 100,000, discount <= 5% of gross, `txn_count = 1`,
   `customer_age` at the sale date.
6. Money compared within 0.01, units and NAV within 0.0001, commission percentage within 0.001.
7. Allowed value lists come from profiling; an unexpected value is reported with the value itself.

## 9. Dependencies

Lab VM with the input files, MySQL `python_project2` with the four tables,
the read-only learner account, Python 3.10+ and the packages in
`requirements.txt`.

## 10. Known limitations

- **No reporting layer in the lab.** There are no views or dashboards, so
  Data Mart-to-Reporting validates the framework's own executive report
  against independent SQL. Dashboard or HTML-page checks would need a
  reporting application.
- **No API in the lab.** The guideline mentions API pagination and errors;
  there is no API source in Python Project 2, so no API connector is built.
- **Customer attribute comparison is blocked by the data.** DM-V11 and
  BR-V08 report SKIPPED because no target row resolves to a customer
  (DM-V09). They will run automatically once the join is fixed.
- **`tax_amount` has no documented or inferable rule**, so it is checked as
  a carried value only.
- **Date formats** are taken from the files seen in the lab. If SRC-V13 or
  DQ-V12 report unparseable dates, add the format to `date_formats`.
- Mismatch rows are capped per validation to keep the report readable.

## 11. Findings from the first full-volume profiling

These are confirmed defects; full analysis follows in Submission 3.

| Finding | Evidence | Detected by |
|---|---|---|
| Customer enrichment fails: 18 customer columns blank on all 45,076 target rows | `customer_key` and every customer attribute blank | DM-V09, DM-V10 |
| `fact_sales.customer_key` never exists in the customer master | fact 100,004-400,000 vs master 1-50,000; equals distributor customer number + 1 on 48,461 rows | DQ-V14 |
| Target `customer_pan` blank although the sale carries one | 40,575 rows differ from distributor sales | DM-V08 |
| `policy_number` links each sale to a customer whose PAN differs | PAN agrees on 0 of 50,000 policy-linked rows | DQ-V16 |
| Duplicate `customer_id` in the customer master | 48,729 distinct of 50,000 | DQ-V08 |
| `distributor_name` blank at source | 100% of rows | DQ-V05 |
| Blank `region_code`, `customer_id`, `customer_pan` at source | 7,496 / 1,539 / 4,965 rows | DQ-V04, DQ-V06 |
