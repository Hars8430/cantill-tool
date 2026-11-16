# Cantill spend classification tool

Config-driven pipeline: ingest raw purchase data, clean it, count spend once,
de-duplicate suppliers and items, and classify each line into a company's category tree.

## Setup
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## Run (one command)
    python -m src.cantill.run configs/companyA.yaml

Writes results/<output_prefix>__A.csv, one row per input record (excluded rows included).
Labels in data/raw are used for evaluation only; the classifier never reads them.
