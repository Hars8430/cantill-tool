# Cantill spend classification tool

Config-driven pipeline: ingest raw purchase data, clean it, count spend once,
de-duplicate suppliers and items, and classify each line into a company's category tree.

## Setup
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## Run (one command)
    python -m cantill run --config configs/companyA.yaml

(Commands will be filled in as the pipeline is built.)
