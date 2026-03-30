# GRC-20 Pharmaceutical Knowledge Graph Pipeline

Builds a GRC-20 compliant knowledge graph from pharmaceutical data sources.

## Output

- **570K+ entities** - Drugs, ingredients, manufacturers, package inserts
- **1.5M+ relations** - Connections between entities with full provenance
- **GRC-20 format** - Ready for knowledge graph applications

## Pipeline Steps

| Step | Name | Description |
|------|------|-------------|
| 1 | DailyMed | Parse FDA drug labels from SPL XML |
| 2 | RxNorm | Convert NIH drug terminology to GRC-20 |
| 3 | NDC Extraction | Extract National Drug Codes from RxNorm |
| 4 | NDC Bridge | Link NDCs to RxNorm entities |
| 5 | PubChem CID | Match RxNorm ingredients to PubChem compounds |
| 6 | PubChem Properties | Fetch molecular properties (SMILES, InChIKey, etc.) |
| 7 | Merge & Enrich | Combine all sources into unified knowledge graph |
| 8 | Link PI to RxNorm | Connect package inserts to drug entities |
| 9 | Link DailyMed to RxNorm | Create additional drug-label relationships |
| 10 | Provenance | Ensure 100% provenance coverage |
| 11 | Validate | Verify schema compliance and data integrity |

## Quick Start

```bash
# First run - configure data sources
python run_pipeline.py --configure

# Run full pipeline
python run_pipeline.py

# Run specific step
python run_pipeline.py --step 7

# Run with document limit (testing)
python run_pipeline.py --limit 100
Data Sources

    DailyMed - FDA Structured Product Labels (drug labels, package inserts)
    RxNorm - NIH normalized names for clinical drugs
    PubChem - Molecular structures and properties

Output Files

Located in data/grc20_v2/:

    grc20_merged_entities.jsonl - All entities
    grc20_merged_relations.jsonl - All relations
    provenance_ledger.json - Source tracking for all data
