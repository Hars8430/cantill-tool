"""Ingest Company A's two systems into one normalised table.

Output columns (one row per input record, nothing dropped yet):
  record_id, source, supplier_name, supplier_id, invoice_number, po,
  description, date, date_ok, amount_net, currency, status_code, quantity
status_code is '' for spend-eligible lines, else CANCELLED / NOT_APPROVED.
"""
import re
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

from .config import load_config

COLUMNS = ["record_id", "source", "supplier_name", "supplier_id", "invoice_number",
           "po", "description", "date", "date_ok", "amount_net", "currency",
           "status_code", "quantity"]


def parse_amount(series: pd.Series, thousands: str = ",") -> pd.Series:
    s = series.astype(str).str.strip()
    if thousands:
        s = s.str.replace(thousands, "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def parse_vat_rate(series: pd.Series, default_rate: float) -> pd.Series:
    """Accepts '15', '0.15', '15%', '0', or blank. Blank means the default rate."""
    s = series.astype(str).str.strip()
    out = []
    for v in s:
        if v == "":
            out.append(default_rate)
            continue
        is_pct = v.endswith("%")
        num = float(v.rstrip("%"))
        # '15' or '15%' mean 15 percent; '0.15' is already a fraction; '0' means zero
        if is_pct or num > 1:
            num = num / 100.0
        out.append(num)
    return pd.Series(out, index=series.index, dtype=float)


def parse_dates(series: pd.Series, formats: list[str]) -> tuple[pd.Series, pd.Series]:
    """Try each format in order. Returns (date, date_ok). Blank or unparseable -> NaT, date_ok False."""
    s = series.astype(str).str.strip()
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for fmt in formats:
        todo = result.isna() & (s != "")
        if not todo.any():
            break
        parsed = pd.to_datetime(s[todo], format=fmt, errors="coerce")
        result.loc[todo] = parsed
    return result, result.notna()


def ingest_company_a(cfg_path: str) -> pd.DataFrame:
    cfg = load_config(cfg_path)
    base = Path(cfg_path).resolve().parent.parent  # repo root: configs/ sits one level below it
    erp_cfg, tool_cfg = cfg["erp"], cfg["tool"]
    thousands = tool_cfg.get("thousands_separator", ",")

    # ---- ERP: already net, already ZAR --------------------------------
    erp = pd.read_csv(base / cfg["files"]["erp"], dtype=str, keep_default_na=False)
    erp_dates, erp_ok = parse_dates(erp[erp_cfg["date"]], erp_cfg["date_formats"])
    erp_out = pd.DataFrame({
        "record_id": erp_cfg["record_prefix"] + ":" + erp[erp_cfg["id"]],
        "source": "ERP",
        "supplier_name": erp[erp_cfg["supplier_name"]],
        "supplier_id": erp[erp_cfg["supplier_id"]],
        "invoice_number": erp[erp_cfg["po"]] + "/" + erp[erp_cfg["po_item"]],  # PO line, used as the doc key
        "po": erp[erp_cfg["po"]],
        "description": erp[erp_cfg["description_columns"]].agg(" ".join, axis=1).str.strip(),
        "date": erp_dates,
        "date_ok": erp_ok,
        "amount_net": parse_amount(erp[erp_cfg["amount"]], thousands="").astype(float),
        "currency": cfg["reporting_currency"],
        "status_code": "",
        "quantity": parse_amount(erp[erp_cfg["quantity"]], thousands="").astype(float),
    })

    # ---- Tool: gross, needs VAT removed, may need a status check -------
    tool = pd.read_csv(base / cfg["files"]["tool"], dtype=str, keep_default_na=False)
    gross = parse_amount(tool[tool_cfg["amount"]], thousands=thousands)
    rate = parse_vat_rate(tool[tool_cfg["vat"]["column"]], tool_cfg["vat"]["default_rate"])
    tool_dates, tool_ok = parse_dates(tool[tool_cfg["date"]], tool_cfg["date_formats"])

    st = tool_cfg["status"]
    status_col = tool[st["column"]].str.strip()
    status_code = status_col.map(st["exclusions"]).fillna("")
    not_approved = ~status_col.isin(st["count_as_spend"]) & (status_code == "")
    status_code = status_code.mask(not_approved, "NOT_APPROVED")

    tool_out = pd.DataFrame({
        "record_id": tool_cfg["record_prefix"] + ":" + tool[tool_cfg["id"]],
        "source": "TOOL",
        "supplier_name": tool[tool_cfg["supplier_name"]],
        "supplier_id": "",
        "invoice_number": tool[tool_cfg["invoice_number"]],
        "po": tool[tool_cfg["po"]],
        "description": tool[tool_cfg["description"]],
        "date": tool_dates,
        "date_ok": tool_ok,
        "amount_net": (gross / (1 + rate)).round(2),
        "currency": cfg["reporting_currency"],
        "status_code": status_code,
        "quantity": parse_amount(tool[tool_cfg["quantity"]], thousands="").astype(float),
    })

    out = pd.concat([erp_out, tool_out], ignore_index=True)[COLUMNS]
    return out


if __name__ == "__main__":
    import sys
    df = ingest_company_a(sys.argv[1] if len(sys.argv) > 1 else "configs/companyA.yaml")
    print(df.groupby("source").size())
    print("\nstatus codes:\n", df.groupby(["source", "status_code"]).size())
    print("\nunparseable dates:", (~df["date_ok"]).groupby(df["source"]).sum().to_dict())
    print("\nnet amount totals:\n", df.groupby("source")["amount_net"].sum().round(2))
