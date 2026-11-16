"""Match Company A's ERP and tool records so each real purchase is counted once.

Order of rules (each record matched at most once):
  1. repeat_invoice : same invoice number, PO and net amount appears more than once in the tool -> keep the first, rest DUPLICATE
  2. po_amount      : tool line and ERP line share a PO number and net amount to the cent, paired 1:1 -> tool line DUPLICATE, ERP kept
  3. fuzzy          : tool line with the same net amount to the cent and a similar supplier name to an unmatched ERP line -> tool line DUPLICATE
Anything left on the tool side with status approved/paid is tool-only spend and stays counted.
"""
import re
import pandas as pd
from rapidfuzz import fuzz

FUZZY_SUPPLIER_MIN = 85
LEGAL = re.compile(r"\(PTY\)|\bPTY\b|\bLTD\b|\bLIMITED\b|\bSA\b|\bINC\b|\bCC\b", re.I)


def norm_name(s: str) -> str:
    s = LEGAL.sub(" ", str(s).upper())
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


def name_score(a: str, b: str) -> float:
    """OCR often splits words (YAR VEX vs YARVEX), so compare with spaces removed too."""
    a2, b2 = a.replace(" ", ""), b.replace(" ", "")
    return max(fuzz.token_set_ratio(a, b), fuzz.ratio(a2, b2))


def po_key(s: str) -> str:
    m = re.search(r"(\d{10})", str(s))
    return m.group(1) if m else ""


def match_company_a(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["match_tier"] = ""
    df["matched_to"] = ""
    df["supplier_norm"] = df["supplier_name"].map(norm_name)
    df["po_key"] = df["po"].map(po_key)
    df["amt"] = df["amount_net"].round(2)
    is_tool = df["source"] == "TOOL"
    is_erp = df["source"] == "ERP"

    # ---- 1. repeated tool invoices --------------------------------------
    tool_ok = is_tool & (df["status_code"] == "")
    t = df[tool_ok]
    repeats = t.index[t.duplicated(subset=["invoice_number", "po_key", "amt"], keep="first")]
    df.loc[repeats, "status_code"] = "DUPLICATE"
    df.loc[repeats, "match_tier"] = "repeat_invoice"

    # ---- 2. PO + net amount, 1:1 -----------------------------------------
    erp_pool = {}
    for idx, row in df[is_erp & df["po_key"].ne("")].iterrows():
        erp_pool.setdefault((row["po_key"], row["amt"]), []).append(idx)
    for idx, row in df[is_tool & (df["status_code"] == "") & df["po_key"].ne("")].iterrows():
        pool = erp_pool.get((row["po_key"], row["amt"]))
        if pool:
            erp_idx = pool.pop(0)
            df.loc[idx, "status_code"] = "DUPLICATE"
            df.loc[idx, "match_tier"] = "po_amount"
            df.loc[idx, "matched_to"] = df.loc[erp_idx, "record_id"]
            df.loc[erp_idx, "match_tier"] = "po_amount"
            df.loc[erp_idx, "matched_to"] = df.loc[idx, "record_id"]

    # ---- 3. same amount, similar supplier ----------------------------------
    erp_left = df[is_erp & (df["match_tier"] == "")]
    by_amt = {}
    for idx, row in erp_left.iterrows():
        by_amt.setdefault(row["amt"], []).append(idx)
    for idx, row in df[is_tool & (df["status_code"] == "")].iterrows():
        cands = by_amt.get(row["amt"], [])
        best, best_score = None, 0
        for c in cands:
            if df.loc[c, "match_tier"] != "":
                continue
            score = name_score(row["supplier_norm"], df.loc[c, "supplier_norm"])
            if score > best_score:
                best, best_score = c, score
        if best is not None and best_score >= FUZZY_SUPPLIER_MIN:
            df.loc[idx, "status_code"] = "DUPLICATE"
            df.loc[idx, "match_tier"] = "fuzzy"
            df.loc[idx, "matched_to"] = df.loc[best, "record_id"]
            df.loc[best, "match_tier"] = "fuzzy"
            df.loc[best, "matched_to"] = df.loc[idx, "record_id"]

    return df


if __name__ == "__main__":
    import sys
    from .ingest import ingest_company_a
    df = match_company_a(ingest_company_a(sys.argv[1] if len(sys.argv) > 1 else "configs/companyA.yaml"))
    print("tool/erp by match_tier:\n", df.groupby(["source", "match_tier"]).size())
    print("\nstatus after matching:\n", df.groupby(["source", "status_code"]).size())
    counted = df[df.status_code == ""]
    print("\ncounted spend (net, ZAR) by source:\n", counted.groupby("source")["amount_net"].sum().round(2))
    print("\nTOTAL counted spend ZAR:", round(counted["amount_net"].sum(), 2))
