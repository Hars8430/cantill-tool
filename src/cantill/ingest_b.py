"""Ingest Company B: one invoice-line file, FX to USD, GL-based non-procurement rule, vendor-ID suppliers."""
import re
import numpy as np
from pathlib import Path
import pandas as pd
from .config import load_config

COLUMNS = ["record_id", "source", "supplier_name", "supplier_id", "invoice_number", "po",
           "description", "date", "date_ok", "amount_net", "currency", "status_code", "quantity", "item_id"]


def fx_lookup(fx: pd.DataFrame) -> dict:
    return {(c, m): float(r) for c, m, r in zip(fx["currency"], fx["month"], fx["units_per_usd"])}


def ingest_company_b(cfg_path: str) -> pd.DataFrame:
    cfg = load_config(cfg_path)
    base = Path(cfg_path).resolve().parent.parent
    ic = cfg["invoices"]
    b = pd.read_csv(base / cfg["files"]["invoices"], dtype=str, keep_default_na=False)
    fx = pd.read_csv(base / cfg["files"]["fx"], dtype=str, keep_default_na=False)
    rates = fx_lookup(fx)

    amount = pd.to_numeric(b[ic["amount"]].str.strip(), errors="coerce")
    usd_rate = pd.to_numeric(b[ic["currency_rate"]], errors="coerce")
    is_usd = b[ic["currency"]] == "USD"
    month = b[ic["date"]].str[:7]

    # rate: the line's own rate; if missing, the FX file for that currency and posting month
    fallback = pd.Series([rates.get((c, m), float("nan")) for c, m in zip(b[ic["currency"]], month)], index=b.index)
    rate = usd_rate.where(usd_rate > 0, fallback)
    rate = rate.where(~is_usd, 1.0)
    amount_usd = (amount / rate).round(2)

    dates = pd.to_datetime(b[ic["date"]], format="%Y-%m-%d", errors="coerce")
    gl = b[ic["gl_description"]].str.strip()
    patterns = cfg.get("exclusions", {}).get("non_procurement", {}).get("gl_description_patterns", [])
    desc = b[ic["description"]].str.strip()
    desc_patterns = cfg.get("exclusions", {}).get("non_procurement", {}).get("description_patterns", [])
    np_flag = pd.Series(False, index=b.index)
    for p in patterns:
        np_flag |= gl.str.contains(p, flags=re.IGNORECASE, regex=True)
    for p in desc_patterns:
        np_flag |= desc.str.contains(p, flags=re.IGNORECASE, regex=True)

    out = pd.DataFrame({
        "record_id": b[ic["record_id"]],
        "source": "B",
        "supplier_name": "",
        "supplier_id": b[ic["vendor_id"]],
        "invoice_number": b["invoice_number"],
        "po": b["po_number"],
        "description": b[ic["description"]].str.strip(),
        "date": dates,
        "date_ok": dates.notna(),
        "amount_net": amount_usd,
        "currency": "USD",
        # unparseable amount (blank line_amount): cannot be verified, so not counted
        "status_code": np.where(np_flag, "NON_PROCUREMENT", np.where(amount.isna(), "NOT_APPROVED", "")),
        "quantity": pd.to_numeric(b["quantity"], errors="coerce"),
        "item_id": b[ic["material"]],
    })
    out.loc[amount.isna(), "amount_net"] = 0.0
    out["matched_to"] = ""      # Company B has one system: nothing to match
    out["match_tier"] = ""
    out["rate_source"] = np.where(is_usd, "USD", np.where(usd_rate > 0, "line", "fx_file"))
    return out


if __name__ == "__main__":
    import sys
    import numpy as np  # noqa: F401  (used above via np.where)
    df = ingest_company_b(sys.argv[1] if len(sys.argv) > 1 else "configs/companyB.yaml")
    print(df.groupby("status_code").size())
    print("rate source:", df.rate_source.value_counts().to_dict())
    print("amount_usd NaN:", df.amount_net.isna().sum(), "| total USD (counted):", round(df.loc[df.status_code == "", "amount_net"].sum(), 2))
