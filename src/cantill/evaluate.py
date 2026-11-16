"""Score classification against the analyst labels. Labels are used here only, never by the classifier."""
import pandas as pd


def score(df_records: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """df_records: record_id, l1, l2, l3, spend (counted rows). labels: record_id, category_l1..3."""
    m = df_records.merge(labels, on="record_id", how="inner")
    w = m["spend"]
    out = {}
    for lvl in ["1", "2", "3"]:
        ok = (m[f"l{lvl}"] == m[f"category_l{lvl}"]).astype(float)
        out[f"L{lvl}_acc_count"] = round(ok.mean(), 4)
        out[f"L{lvl}_acc_spend"] = round((ok * w).sum() / w.sum(), 4) if w.sum() else 0
    out["rows_scored"] = len(m)
    return out
