"""Builds a small replica of the lab: three input files plus a SQLite database
holding the four tables, seeded with the defects found by profiling the lab:

  * fact_sales.customer_key = distributor customer number + 1 (never in the master)
  * customer columns, customer_key and customer_pan blank in the target
  * the same policy_number carries a different PAN in sales and in the master
  * duplicate customer_id values in the customer master
  * distributor_name always blank; region_code and customer ids sometimes blank
  * REJECTED and CANCELLED sales excluded from the target
"""
import json
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES = yaml.safe_load(open(ROOT / "config" / "validation_rules.yaml"))
SCHEMAS = RULES["schemas"]


def pan(rng):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(rng.choice(letters) for _ in range(5)) + f"{rng.randint(1000, 9999)}" + rng.choice(letters)


def mdy(d):
    return f"{d.month}/{d.day}/{d.year}"


def mdy_hm(ts):
    return f"{ts.month}/{ts.day}/{ts.year} {ts.hour}:{ts.minute:02d}"


def build(out_dir, n=3000, seed=7):
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime(2026, 9, 4, 10, 26, 9)

    # ---------------- customer master (one customer per policy, as in the lab)
    master = []
    for i in range(1, n + 1):
        dob = date(1960, 1, 1) + timedelta(days=rng.randint(0, 14000))
        master.append({
            "customer_key": i, "customer_id": f"CUC{rng.randint(1000000, 1999999)}", "customer_pan": pan(rng),
            "policy_number": f"POLCSV{i:08d}", "first_name": rng.choice(["Asha", "Ravi", "Meera", "Kiran"]),
            "last_name": rng.choice(["Rao", "Shah", "Iyer", "Das"]), "gender": rng.choice("MFO"),
            "date_of_birth": dob, "email": f"cust{i}@example.com", "mobile": f"9{rng.randint(100000000, 999999999)}",
            "address_line": f"{i} Main Road, Sector {i % 40}", "city": rng.choice(["Pune", "Delhi", "Chennai"]),
            "state": rng.choice(["Maharashtra", "Delhi", "Tamil Nadu"]), "pincode": f"{rng.randint(110001, 699999)}",
            "country": "India", "kyc_status": rng.choice(["VERIFIED", "PENDING"]),
            "customer_segment": rng.choice(["HNI", "CORPORATE", "RETAIL", "PREMIUM"]),
            "annual_income": round(rng.uniform(300000, 5000000), 2), "onboarded_on": date(2020, 1, 1) + timedelta(days=rng.randint(0, 1800)),
            "active_flag": "Y", "created_at": now - timedelta(days=400), "updated_at": now - timedelta(days=20)})
    for i in rng.sample(range(n), n // 40):                       # duplicate customer_id
        master[i]["customer_id"] = master[(i + 1) % n]["customer_id"]

    # ---------------- distributor sales and fact
    dist, fact = [], []
    for i in range(1, n + 1):
        sale = date(2026, 1, 1) + timedelta(days=rng.randint(0, 35))
        mf = rng.random() < 0.57
        code = (f"MF_{rng.choice(['EQ', 'DEBT', 'SIP'])}_{rng.randint(1, 9)}" if mf
                else f"INS_{rng.choice(['TERM', 'ULIP'])}_{rng.randint(1, 9)}")
        ptype = rng.choice(["MF", "SIP", "Debt Fund", "Equity Fund"]) if mf else rng.choice(["Insurance", "ULIP", "INS"])
        status = rng.choices(["APPROVED", "REJECTED", "CANCELLED"], [90, 5, 5])[0]
        if mf:
            units, nav = round(rng.uniform(100, 6000), 4), round(rng.uniform(10, 200), 4)
            gross = round(units * nav, 2)
        else:
            units = nav = None
            gross = round(rng.uniform(1000, 250000), 2)
        commission = round(gross * rng.uniform(0.002, 0.04), 2)
        cust_num = rng.randint(100003, 399999)
        cust_id = "" if rng.random() < 0.03 else f"CUST{cust_num}"
        created = datetime.combine(sale, datetime.min.time()) + timedelta(hours=rng.randint(8, 18), minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        txn = f"DSC20260101{i:06d}"
        folio = f"FOL{i:08d}" if mf else None
        dist.append({"distributor_txn_id": txn, "sale_date": sale, "distributor_code": f"DST{rng.randint(1, 40):03d}",
                     "distributor_name": "", "customer_id": cust_id, "customer_pan": "" if rng.random() < 0.10 else pan(rng),
                     "product_code": code, "product_name_raw": f"{ptype} Plan {code[-1]}", "product_type_raw": ptype,
                     "policy_number": f"POLCSV{i:08d}", "folio_number": folio, "gross_amount": gross,
                     "commission_amount": commission, "region_code": "" if rng.random() < 0.166 else rng.choice(["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]),
                     "status": status, "created_at": created, "updated_at": created + timedelta(hours=2)})
        fact.append({"sales_sk": 900000 + i, "distributor_txn_id": txn, "sale_date_key": int(sale.strftime("%Y%m%d")),
                     "distributor_key": rng.randint(1, 40), "product_key": rng.randint(1, 30),
                     "customer_key": cust_num + 1 if cust_id else rng.randint(100004, 400000), "region_key": rng.randint(1, 5),
                     "gross_amount": gross, "net_amount": round(gross - commission, 2), "commission_amount": commission,
                     "tax_amount": round(commission * rng.uniform(0.1, 0.2), 2), "discount_amount": round(gross * rng.uniform(0, 0.05), 2),
                     "premium_amount": None if mf else round(gross * 0.9, 2), "sum_assured": None if mf else round(gross * 20, 2),
                     "units_allocated": units, "nav_at_purchase": nav, "commission_pct": round(commission / gross * 100, 3),
                     "txn_count": 1, "is_new_customer_flag": rng.choice("YN"), "is_high_value_flag": "Y" if gross >= 100000 else "N",
                     "policy_number": f"POLCSV{i:08d}", "folio_number": folio, "status": status,
                     "src_created_at": created, "src_updated_at": created + timedelta(hours=2),
                     "etl_run_id": "FACT_RUN_20260904", "etl_load_ts_utc": now})

    # ---------------- target: APPROVED only, customer enrichment missing
    d_by = {d["distributor_txn_id"]: d for d in dist}
    dm = []
    for k, f in enumerate([f for f in fact if f["status"] == "APPROVED"], start=1):
        d = d_by[f["distributor_txn_id"]]
        fam = "MF" if d["product_code"].startswith("MF_") else "INS"
        row = {c: None for c in SCHEMAS["customer_360"]}
        row.update({"dm_sk": k, "sales_sk": f["sales_sk"], "distributor_txn_id": f["distributor_txn_id"],
                    "policy_number": f["policy_number"], "customer_id": d["customer_id"] or None, "sale_date": d["sale_date"],
                    "sale_date_key": f["sale_date_key"], "distributor_code": d["distributor_code"],
                    "distributor_name": None, "product_code": d["product_code"], "product_name_raw": d["product_name_raw"],
                    "product_type_raw": d["product_type_raw"], "product_family": fam,
                    "product_category": "MUTUAL_FUND" if fam == "MF" else "INSURANCE", "folio_number": f["folio_number"],
                    "region_code": d["region_code"] or None, "region_key": f["region_key"], "status": f["status"],
                    "is_kyc_verified_flag": "N", "is_ins_txn_flag": "Y" if fam == "INS" else "N",
                    "is_mf_txn_flag": "Y" if fam == "MF" else "N", "fact_etl_run_id": f["etl_run_id"],
                    "dm_etl_run_id": "DM_RUN_20260904", "dm_load_ts_utc": now})
        for c in ("gross_amount", "net_amount", "commission_amount", "tax_amount", "discount_amount", "premium_amount",
                  "sum_assured", "units_allocated", "nav_at_purchase", "commission_pct", "txn_count",
                  "is_new_customer_flag", "is_high_value_flag", "src_created_at", "src_updated_at"):
            row[c] = f[c]
        dm.append(row)

    # ---------------- files, in the lab formats
    def file_frame(rows, schema):
        df = pd.DataFrame(rows)[list(schema)]
        for c, kind in schema.items():
            if kind == "date":
                df[c] = df[c].map(lambda v: mdy(v) if v else "")
            elif kind == "datetime":
                df[c] = df[c].map(lambda v: mdy_hm(v) if v else "")
        return df.fillna("")

    file_frame(master, SCHEMAS["customer_master"]).to_csv(out / RULES["sources"]["customer_master"]["file"], index=False)
    file_frame(fact, SCHEMAS["fact_sales"]).to_csv(out / RULES["sources"]["fact_sales"]["file"], index=False)
    js = file_frame(dist, SCHEMAS["distributor_sales"])
    for c in ("gross_amount", "commission_amount"):
        js[c] = js[c].map(lambda v: f"{float(v):.2f}")              # amounts stored as text
    with open(out / RULES["sources"]["distributor_sales"]["file"], "w") as fh:
        json.dump(js.to_dict("records"), fh, indent=2)

    # ---------------- SQLite tables, typed as MySQL would return them
    db = out / "demo.db"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    tables = {"customer_master": ("dim_customer_master", master), "distributor_sales": ("dim_distributor_sales", dist),
              "fact_sales": ("fact_sales", fact), "customer_360": ("dm_distributor_sales_customer_360", dm)}
    for logical, (name, rows) in tables.items():
        df = pd.DataFrame(rows)[list(SCHEMAS[logical])]
        for c, kind in SCHEMAS[logical].items():
            if kind in ("date", "datetime"):
                df[c] = df[c].map(lambda v: str(v) if v else None)
            if kind == "text":
                df[c] = df[c].map(lambda v: None if v in ("", None) else v)
        df.to_sql(name, conn, index=False)
    conn.close()
    return out, db


if __name__ == "__main__":
    o, d = build(ROOT / "tests" / "demo" / "_work")
    print("demo data written to", o)
