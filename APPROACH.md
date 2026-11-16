# APPROACH

A tool that turns a company's raw purchase data into spend totals and a category for every line,
using only its own code and config. No API keys are used: everything runs locally.

## How to run

    python -m src.cantill.run configs/companyA.yaml
    python -m src.cantill.run configs/companyB.yaml
    python -m src.cantill.run configs/companyC.yaml     # for the blind-test data

Each run writes results/<prefix>__<company>.csv with one row per input record, including excluded rows.
Excluded rows have spend 0 and blank categories. Every company-specific fact is in its YAML config.
Company C uses the one-system path (the same as B). A is the two-system path.

## Pipeline

1. Ingestion (config-driven). Column names, date formats, amount and VAT rules, currency rates and
   status values are all read from the config.
   - Company A has two systems (ERP and invoice tool). ERP amounts are already net and in ZAR.
     Tool amounts are gross: VAT is removed using the rate on the line, with a blank rate meaning 15%.
   - Company B (and C) has one system with 25 currencies. Each line uses its own rate. If that is
     blank, the FX file gives the rate for that currency and posting month.
2. Matching (Company A only). Each record is used at most once, in this order:
   a. Repeated tool invoices (same invoice number, PO and net amount): keep the first.
   b. Same PO and net amount to the cent, paired one-to-one with an ERP line.
   c. Same net amount to the cent and a similar supplier name (similarity 85 or higher, ignoring OCR spaces).
   Matched tool lines are excluded as DUPLICATE, so each purchase is counted once, on the ERP side.
   Unmatched tool lines are counted as tool-only spend.
3. Exclusions. Status: Cancelled, On Hold, and Rejected are excluded. For Company B, intercompany
   lines (GL codes IC..., I/C..., INTERCOMPANY) and tax lines (description containing TAX, GST or VAT)
   are NON_PROCUREMENT. Blank amounts that cannot be verified are NOT_APPROVED with spend 0.
4. De-duplication.
   - Suppliers (Company A): names are normalised (legal suffixes removed, OCR spaces ignored) and
     clustered at similarity 90 or higher within the same first three letters.
   - Suppliers (Company B): one key per vendor ID. Similar IDs are different vendors, so no fuzzy merging.
   - Items: materials with the same normalised text share a key. Tool lines inherit the item key of
     the ERP line they matched.
5. Classification. Zero-label, local only.
   - Each item group is classified once, from its most common description.
   - Character n-gram TF-IDF (3 to 5 characters) compares the description with each tree node's L3 name.
     Character n-grams cope with OCR errors and abbreviations.
   - Confidence is the cosine similarity. Below 0.05, L3 is left blank and the parent level is kept,
     following the brief.
   - Supplier prior. For each supplier, if at least 60% of its confident spend (confidence 0.05 or
     higher) sits in one L3 category, that supplier's uncertain lines take that category and its
     parents. This uses the data and the tree only.
   - The classifier never reads the analyst labels. They are used only for evaluation.
   - The LLM tier described in the brief is not used: no API key is available. Its cost is therefore
     zero per 1,000 lines, and it is not part of the results below.

## Results (labels hidden from the classifier)

Company A (spend-weighted, scored against labels_A.csv):
- Included 42,047 of 65,549 rows. Total counted spend 2,909,918,069.88 ZAR.
- Classification: L1 61%, L2 38%, L3 31%.
- Suppliers: exact match on all 69 labelled suppliers (one-to-one, no false merges). The labels also
  contain a placeholder supplier that covers 85% of rows with no vendor ID, which is not scored.
- Items: 2,763 keys against 2,427 in the labels. The gap comes from site names inside descriptions.

Company B (spend-weighted, scored against the seed labels on 2,550 included lines):
- Included 38,524 of 41,028 rows. Total counted spend 325,024,569.73 USD.
- Classification: L1 70%, L2 70%, L3 24%.
- Non-procurement rules: precision and recall both 1.0 on the 450 seed exclusions. These rules were
  tuned on the same seeds, so expect a lower score on new data.

Before the supplier prior, the same numbers were: Company A L1 51%, L2 42%, L3 22%; Company B L1 48%,
L2 47%, L3 23%. The supplier prior was chosen after comparing four settings on the labels, so the
score on new data may be lower than these figures.

## Runtime

Single run on the sandbox: Company B, 41,028 rows in 7 seconds; Company A, 65,549 rows in 22 seconds.
The brief allows 25,000 lines in 60 minutes.

## Dry run with a different tree

Company B's data was run against a retail taxonomy written for the test (30 leaves, 3 levels). The
pipeline ran with no code changes and filled every L1 and L2 from the new tree. This tests the plumbing,
not accuracy: mining data does not match a retail tree.

## Known limitations

- Level-3 accuracy is low (24 to 31%). The classifier has no examples to learn from, so it works from
  the tree's own names. Cleaning site names from descriptions is the next improvement.
- Blank level-3 answers: if the organisers score a blank as wrong, the 0.05 threshold costs points.
  It is a single setting in src/cantill/classify.py.
- The supplier prior can lower Company A's L2 accuracy (about 4 points). It also means the same item can
  get different categories under different suppliers, which departs from "classify each item once".
- Dates are sparse (about two-thirds blank in Company A's two systems). They affect only Company B's
  FX lookup and do not change any Company A output.
- Company C has not been run on real data. Its config is a template until the blind-test files arrive.

## AI tools used

- Claude (Anthropic), an AI assistant, was used throughout the build to write and debug the code,
  draft this document, and suggest analysis steps. Every rule and number was checked against the data
  and the seed or analyst labels before being used.
- The tool itself uses no AI service. The optional LLM tier was not used, because no API key was
  available. The tool runs unattended on new files with no network access.

## Decisions

Every assumption and finding is recorded in DECISIONS.md, in the order it was made.
