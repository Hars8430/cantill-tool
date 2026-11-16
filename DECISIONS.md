# DECISIONS

Assumptions and findings, recorded as we go. Newest at the bottom.

## Data findings (profiled 16 Nov)
- A tool export: 28,520 lines. Status values: Paid 19,837; Approved 8,180; Cancelled 188; On Hold 172; Rejected 143.
  Only Paid and Approved count as spend. Cancelled, On Hold and Rejected are excluded (CANCELLED / NOT_APPROVED).
- A VAT rate formats: "15", "0.15", "15%", "0", blank. Blank is treated as 15% (per brief).
- A ERP: 37,029 lines (Material 17,959; Service 11,232; Free Text 5,551; Catalogue 2,287). 94 vendor_ids, 193 supplier name strings, 3,140 material numbers.
- B: 41,028 lines across 8 ERP source systems. There is no status column, so every B line is assumed approved.
- B: no supplier names, only vendor IDs. B suppliers will be keyed on vendor ID.

## Assumptions
- Reporting currency: ZAR for A, USD for B and C.
- Output file prefix: harsh_singh (so files are harsh_singh__A.csv, harsh_singh__B.csv, harsh_singh__A2.csv, etc.). Spaces are replaced with underscores in file names.

## Company A ingestion (step 3 findings)
- ERP posting_date is blank on 24,370 of 37,029 lines (66%). Tool invoice_date is blank on 18,660 of 28,520 (65%). Dates are therefore sparse on both sides.
- Dates do not affect Company A's output: A is already in ZAR (no FX) and the output has no date column. Dates matter only for Company B's FX lookup. Where both dates exist, the ERP date is used.
- Tool slash dates are parsed day-first (DD/MM/YYYY), based on samples like 19/01/2024 and 24/10/2022.
- Tool status counts: 19,837 Paid + 8,180 Approved count as spend (28,017). 188 Cancelled -> CANCELLED. 315 On Hold + Rejected -> NOT_APPROVED.
- VAT: "15" and "15%" mean 15%, "0.15" is a fraction, "0" means zero, blank uses the 15% default. Net = gross / (1 + rate).
- ERP has no status column: all 37,029 lines are treated as approved.
- ERP document_currency is blank on 15,816 lines. value_zar is already ZAR, so the currency field is not used for A.

## Company A matching (step 4 findings)
- Matching order, each record used at most once: (1) repeated tool invoices, same invoice number + PO + net amount, keep the first, rest DUPLICATE; (2) PO + net amount to the cent, paired 1:1 with ERP lines, tool line DUPLICATE, ERP line kept; (3) same net amount to the cent plus supplier name similarity of at least 85, tool line DUPLICATE.
- Supplier similarity ignores spaces, because OCR splits words (YAR VEX vs YARVEX). Without this, correct PO matches looked like mismatches.
- Results: 1,770 repeat invoices, 15,601 PO matches, 5,628 fuzzy matches. Total DUPLICATE tool lines: 22,999. Tool-only spend left counted: 5,018 lines.
- Counted spend after matching: ERP 2,553,223,000 ZAR (approx.) plus tool-only 356,695,200 ZAR (approx.), total about 2,909,918,070 ZAR. Net of VAT, before the NON_PROCUREMENT rules are applied.
- Every PO and fuzzy match agrees on supplier name at 85% or higher. None were left unverified.
- Not yet done: NON_PROCUREMENT exclusions, item de-duplication, supplier keys, classification. These are the next steps.
