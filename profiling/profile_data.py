"""Full-volume profiling queries run before the validations were written.

The results confirmed the business rules in config/business_rules.yaml and
exposed the customer enrichment defects. Read-only.

    python -m profiling.profile_data > profiling_output.txt
"""
from src.config_loader import load_config
from src.connectors.mysql_connector import MySQLConnector

QUERIES = {
    "Status distribution per table": [
        "SELECT 'distributor' src, status, COUNT(*) n FROM {S} GROUP BY status",
        "SELECT 'fact' src, status, COUNT(*) n FROM {F} GROUP BY status",
        "SELECT 'target' src, status, COUNT(*) n FROM {DM} GROUP BY status"],
    "Fact rows missing from target, by reason": [
        "SELECT f.status, COUNT(*) n FROM {F} f LEFT JOIN {DM} d ON d.distributor_txn_id = f.distributor_txn_id "
        "WHERE d.distributor_txn_id IS NULL GROUP BY f.status"],
    "customer_key ranges": [
        "SELECT 'master' src, MIN(customer_key) mn, MAX(customer_key) mx FROM {C} UNION ALL "
        "SELECT 'fact', MIN(customer_key), MAX(customer_key) FROM {F} UNION ALL "
        "SELECT 'target', MIN(customer_key), MAX(customer_key) FROM {DM}"],
    "fact customer_key vs distributor customer number": [
        "SELECT COUNT(*) total, SUM(f.customer_key = CAST(SUBSTRING(s.customer_id,5) AS UNSIGNED)) equal_, "
        "SUM(f.customer_key = CAST(SUBSTRING(s.customer_id,5) AS UNSIGNED) + 1) plus_one "
        "FROM {F} f JOIN {S} s ON s.distributor_txn_id = f.distributor_txn_id"],
    "Candidate customer join keys (distributor -> master)": [
        "SELECT 'customer_pan' k, SUM(c.customer_key IS NOT NULL) matched FROM {S} s LEFT JOIN {C} c ON c.customer_pan = s.customer_pan UNION ALL "
        "SELECT 'policy_number', SUM(c.customer_key IS NOT NULL) FROM {S} s LEFT JOIN {C} c ON c.policy_number = s.policy_number UNION ALL "
        "SELECT 'customer_id', SUM(c.customer_key IS NOT NULL) FROM {S} s LEFT JOIN {C} c ON c.customer_id = s.customer_id"],
    "Product derivation in target": [
        "SELECT LEFT(product_code,3) prefix, product_type_raw, product_family, product_category, "
        "is_ins_txn_flag, is_mf_txn_flag, COUNT(*) n FROM {DM} GROUP BY 1,2,3,4,5,6"],
    "High value flag vs gross": [
        "SELECT is_high_value_flag, COUNT(*) n, MIN(gross_amount) mn, MAX(gross_amount) mx FROM {F} GROUP BY 1"],
}


def main():
    cfg = load_config()
    db = MySQLConnector(cfg["db"])
    t = cfg["db"]["tables"]
    names = {"C": t["customer_master"], "S": t["distributor_sales"], "F": t["fact_sales"], "DM": t["customer_360"]}
    for title, sqls in QUERIES.items():
        print(f"\n=== {title} ===")
        for sql in sqls:
            print(db.query(sql.format(**names)).to_string(index=False))
    db.close()


if __name__ == "__main__":
    main()
