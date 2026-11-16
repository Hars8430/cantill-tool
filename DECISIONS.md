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
