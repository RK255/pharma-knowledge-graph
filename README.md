# Pharmaceutical Knowledge Graph Pipeline

## Pipeline Steps

| Step | Name | Description |
|------|------|-------------|
| 01 | Dailymed Parser | Parse FDA SPL XML files |
| 02 | RxNorm Loader | Load RxNorm terminology |
| 03 | NDC Bridge | Bridge NDC to RxNorm |
| 04 | PubChem Enrichment | Enrich with PubChem data |
| 05 | Data Enrichment | Additional enrichment steps |
| 06 | Graph Loaders | Load data into Neo4j |
| 07 | API Backend | FastAPI backend service |
| 08 | Clinical Weights | Expert-curated clinical weights |
| 09 | Drug Interactions | Extract drug interactions |
| 10 | Pharmacological Classes | Build drug-class relationships |

## Usage

```bash
# Show pipeline status
python run_pipeline.py --status

# Run specific step
python run_pipeline.py --step 10

# Run all steps
python run_pipeline.py --all
