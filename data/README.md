# Input data

The lab input files are not copied into this project. The framework reads
them in place from the read-only lab folder set in
`config/validation_rules.yaml` (`paths.input_dir`, default
`C:/qa-lab/python-project-2/input`), or from `P2_INPUT_DIR` if set.

| Guideline name | Actual lab file | Format |
|---|---|---|
| `data/source/distributor_sales.txt` | `dim_Distributor_sales_50k.json` | JSON array |
| `data/reference/customer_master.json` | `dim_Customer_Master_50k.txt` | comma-delimited text |
| (not in guideline) | `Fact_Sales_50k_CSV.csv` | CSV |

The lab guide's file names and formats do not match the files provided;
the actual names are used.
