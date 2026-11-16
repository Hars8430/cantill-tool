"""One command for any company, driven by its config.

Usage:  python -m src.cantill.run configs/companyA.yaml
        python -m src.cantill.run configs/companyB.yaml
Writes results/<output_prefix>__<company>.csv, one row per input record (excluded rows included).
"""
import sys
from pathlib import Path
import pandas as pd

from .config import load_config
from .ingest import ingest_company_a
from .ingest_b import ingest_company_b
from .match import match_company_a, norm_name
from .dedupe import build_keys
from .classify import classify_items

OUT_COLUMNS = ["record_id", "include", "exclusion_reason", "supplier_key", "item_key",
               "spend", "l1", "l2", "l3", "l4", "confidence"]


def run_company(cfg_path: str) -> pd.DataFrame:
    cfg = load_config(cfg_path)
    company = cfg["company"]
    if company == "A":
        df = match_company_a(ingest_company_a(cfg_path))   # two systems: match, then count once
    elif company in ("B", "C"):
        df = ingest_company_b(cfg_path)                    # one system: nothing to match (B and C share this path)
    else:
        raise ValueError(f"no ingestion for company {company} yet")

    df["supplier_norm"] = df["supplier_name"].map(norm_name)
    df = build_keys(df)
    items = classify_items(df, cfg["files"]["taxonomy"])
    df = df.merge(items[["item_key", "category_l1", "category_l2", "category_l3", "confidence"]],
                  on="item_key", how="left")

    included = df["status_code"] == ""
    out = pd.DataFrame({
        "record_id": df["record_id"],
        "include": included.astype(int),
        "exclusion_reason": df["status_code"],
        "supplier_key": df["supplier_key"],
        "item_key": df["item_key"],
        "spend": df["amount_net"].where(included, 0.0).round(2),
        "l1": df["category_l1"].where(included, ""),
        "l2": df["category_l2"].where(included, ""),
        "l3": df["category_l3"].where(included, ""),
        "l4": "",
        "confidence": df["confidence"].where(included, 0.0).round(3),
    })
    return out[OUT_COLUMNS]


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "configs/companyA.yaml"
    cfg = load_config(cfg_path)
    out = run_company(cfg_path)
    Path("results").mkdir(exist_ok=True)
    target = Path("results") / f"{cfg['output_prefix']}__{cfg['company']}.csv"
    out.to_csv(target, index=False)
    print("wrote", target, "rows:", len(out))
    print("included:", out.include.sum(), "| excluded:", (out.include == 0).sum())
    print("exclusion reasons:", out.exclusion_reason[out.include == 0].value_counts().to_dict())
    print("total spend:", round(out.spend.sum(), 2))
    print("distinct suppliers:", out.loc[out.include == 1, "supplier_key"].nunique(),
          "| distinct items:", out.loc[out.include == 1, "item_key"].nunique())
