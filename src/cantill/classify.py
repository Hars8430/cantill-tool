"""Classify each item group into the company's category tree, with no labels.

Method (local tier, no API keys):
  - Each tree node's L3 name is the candidate text (the L1/L2 names added noise in testing).
  - Each item group's text is its most common line description (plus the supplier name as a weak hint).
  - Character n-gram TF-IDF handles OCR errors and abbreviations. Cosine similarity picks the best L3 path.
  - Below the confidence threshold, the result stops at the parent level (L2) and L3 is left blank.
Labels are never read here. They are used only in evaluate.py.
"""
import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import load_config

CONF_THRESHOLD = 0.05  # below this, L3 is blank and the parent level is kept (brief rule). Chosen by you; see DECISIONS.md


def clean(text: str) -> str:
    t = re.sub(r"[^A-Za-z0-9 ]", " ", str(text).lower())
    return " ".join(t.split())


def load_tree(path: str) -> pd.DataFrame:
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    t["path"] = t["category_l1"] + " > " + t["category_l2"] + " > " + t["category_l3"]
    t["text"] = t["category_l1"] + " " + t["category_l2"] + " " + t["category_l3"]
    return t.drop_duplicates(subset=["category_l1", "category_l2", "category_l3"]).reset_index(drop=True)


def item_texts(df: pd.DataFrame) -> pd.DataFrame:
    """One row per item group: its most common description, and its supplier as a weak hint."""
    g = df.groupby("item_key")
    rows = []
    for key, sub in g:
        descs = sub["description"].str.strip()
        descs = descs[descs != ""]
        text = descs.value_counts().index[0] if len(descs) else ""
        rows.append({"item_key": key, "text": clean(text), "spend": sub.loc[sub["status_code"] == "", "amount_net"].sum(),
                     "supplier_hint": clean(sub["supplier_name"].mode().iat[0]) if len(sub) else ""})
    return pd.DataFrame(rows)


def classify_items(df: pd.DataFrame, tree_path: str) -> pd.DataFrame:
    tree = load_tree(tree_path)
    items = item_texts(df)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    vec.fit(list(tree["category_l3"].map(clean)) + list(items["text"]))
    tree_m = vec.transform(tree["category_l3"].map(clean))
    item_m = vec.transform(items["text"])
    sims = cosine_similarity(item_m, tree_m)
    best = sims.argmax(axis=1)
    score = sims.max(axis=1)
    items["best"] = best
    items["confidence"] = score.round(3)
    for lvl in ["category_l1", "category_l2", "category_l3"]:
        items[lvl] = tree[lvl].values[best]
    below = items["confidence"] < CONF_THRESHOLD
    items.loc[below, "category_l3"] = ""
    items.loc[below, "confidence"] = items.loc[below, "confidence"]
    return items


if __name__ == "__main__":
    import sys
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/companyA.yaml")
    from .ingest import ingest_company_a
    from .match import match_company_a, norm_name
    from .dedupe import build_keys
    df = match_company_a(ingest_company_a("configs/companyA.yaml"))
    df["supplier_norm"] = df["supplier_name"].map(norm_name)
    df = build_keys(df)
    items = classify_items(df, cfg["files"]["taxonomy"])
    print("item groups:", len(items), "| below threshold:", (items.category_l3 == "").sum())
    print("spend-weighted share below threshold:", round(items.loc[items.category_l3 == "", "spend"].sum() / items.spend.sum(), 3))
    print(items.sort_values("spend", ascending=False).head(8)[["text", "category_l2", "category_l3", "confidence"]].to_string())


def apply_supplier_prior(df: pd.DataFrame, tree: pd.DataFrame, min_share: float = 0.6,
                         conf_cut: float = 0.05) -> pd.DataFrame:
    """Zero-label supplier prior.

    For each supplier, look at its confident lines (confidence >= conf_cut) and find the L3 category
    holding the largest spend share. If that share is at least min_share, the supplier's uncertain
    lines (below conf_cut, or with blank L3) take that L3 and its L1/L2 parents.
    Uses only the data and the tree. Labels are never read.
    """
    df = df.copy()
    inc = df[df["status_code"] == ""]
    strong = inc[(inc["confidence"] >= conf_cut) & (inc["category_l3"] != "")]
    if strong.empty:
        return df
    spend = strong.groupby(["supplier_key", "category_l3"])["amount_net"].sum()
    totals = spend.groupby(level=0).sum()
    top = spend.groupby(level=0).idxmax().map(lambda t: t[1])
    share = spend.groupby(level=0).max() / totals
    prior_l3 = top[share >= min_share]

    parents = tree.drop_duplicates("category_l3").set_index("category_l3")[["category_l1", "category_l2"]]
    weak = ((df["status_code"] == "") & ((df["confidence"] < conf_cut) | (df["category_l3"] == ""))
            & df["supplier_key"].isin(prior_l3.index))
    if weak.any():
        l3 = df.loc[weak, "supplier_key"].map(prior_l3)
        df.loc[weak, "category_l3"] = l3.values
        df.loc[weak, "category_l1"] = l3.map(parents["category_l1"]).values
        df.loc[weak, "category_l2"] = l3.map(parents["category_l2"]).values
        df.loc[weak, "confidence"] = conf_cut
    return df
