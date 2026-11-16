"""Give every real supplier and every real item one key, however it is typed.

Suppliers: ERP vendor IDs and name strings are clustered on normalised names.
Two names merge only if they are very similar (score >= 90) and share the same first letters
(blocking, so we never compare everything with everything). Merges are conservative.
Items: ERP lines key on material number, then merge materials whose short texts are the same
once normalised. Tool lines inherit the item key of the ERP line they matched; otherwise they get
a key from their own normalised text.
"""
import re
import pandas as pd
from rapidfuzz import fuzz

from .match import norm_name
from .ingest import ingest_company_a
from .match import match_company_a

SUPPLIER_MERGE = 90


class UnionFind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def supplier_keys(names: pd.Series) -> dict:
    """Map each distinct normalised name to a cluster key."""
    uniq = sorted(set(n for n in names if n))
    uf = UnionFind()
    for n in uniq:
        uf.find(n)
    blocks = {}
    for n in uniq:
        blocks.setdefault(n.replace(" ", "")[:3], []).append(n)
    for group in blocks.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if fuzz.ratio(a.replace(" ", ""), b.replace(" ", "")) >= SUPPLIER_MERGE:
                    uf.union(a, b)
    roots = {}
    keymap = {}
    for n in uniq:
        r = uf.find(n)
        roots.setdefault(r, f"SG-{len(roots) + 1:04d}")
        keymap[n] = roots[r]
    return keymap


def item_text_key(text: str) -> str:
    t = re.sub(r"[^A-Z0-9 ]", " ", str(text).upper())
    return " ".join(t.split())


def build_keys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    is_b = df["source"] == "B"
    # Company B has vendor IDs only: one key per vendor ID, no fuzzy merging (similar IDs are different vendors)
    km = supplier_keys(df.loc[~is_b, "supplier_norm"])
    df["supplier_key"] = df["supplier_norm"].map(km).fillna("")
    df.loc[is_b, "supplier_key"] = "VB-" + df.loc[is_b, "supplier_id"]

    # ERP item key: material number, then merge materials that share the same normalised text
    erp = df["source"].isin(["ERP", "B"])  # catalogue-side records: ERP for A, invoice lines for B
    mat = df.loc[erp, "item_id"]
    erp_text = df.loc[erp, "description"].map(item_text_key)
    text_to_key = {}
    item_key_of_material = {}
    for m, t in zip(mat, erp_text):
        if m in item_key_of_material:
            continue
        key = text_to_key.setdefault(t, f"IG-{len(text_to_key) + 1:05d}") if t else f"IG-M-{m}"
        item_key_of_material[m] = key
    df.loc[erp, "item_key"] = mat.map(item_key_of_material)

    # Tool lines: inherit from matched ERP line, else from own text
    erp_key_by_record = dict(zip(df.loc[erp, "record_id"], df.loc[erp, "item_key"]))
    tool = df["source"] == "TOOL"
    inherited = df.loc[tool, "matched_to"].map(erp_key_by_record)
    own = df.loc[tool, "description"].map(item_text_key).map(
        lambda t: text_to_key.setdefault(t, f"IG-{len(text_to_key) + 1:05d}") if t else "IG-T-BLANK")
    df.loc[tool, "item_key"] = inherited.fillna(own)
    return df


if __name__ == "__main__":
    from .config import load_config
    cfg = "configs/companyA.yaml"
    df = match_company_a(ingest_company_a(cfg))
    df["supplier_norm"] = df["supplier_name"].map(norm_name)
    df = build_keys(df)
    erp = df[df.source == "ERP"]
    print("ERP supplier name strings:", erp.supplier_norm.nunique(), "-> supplier keys:", erp.supplier_key.nunique())
    print("ERP vendor IDs:", erp.supplier_id.replace("", pd.NA).nunique(), "(blank for", (erp.supplier_id == "").sum(), "lines)")
    print("all supplier keys:", df.supplier_key.nunique())
    print("ERP material numbers:", erp.item_id.nunique(), "-> ERP item keys:", erp.item_key.nunique())
    print("all item keys:", df.item_key.nunique())
    print("\nsample supplier merges:")
    g = df.groupby("supplier_key")["supplier_norm"].unique()
    multi = g[g.map(len) > 1].head(8)
    for k, names in multi.items():
        print(" ", k, names.tolist()[:4])
