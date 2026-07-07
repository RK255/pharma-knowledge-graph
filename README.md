# Pharma Knowledge Graph Pipeline

> A GRC-20 compliant pharmaceutical knowledge graph pipeline that ingests, normalizes, and links drug data from FDA DailyMed, RxNorm, NDC, and PubChem into a unified ontology with full provenance.

**Author:** [Kevin Garvey, PharmD, MBA](https://geopharma.app/resume)

---

## Overview

This pipeline builds a production-grade pharmaceutical knowledge graph from public drug data sources. It produces 570K+ entities and 1.5M+ relations in GRC-20 format, with full provenance tracking for every entity and relation. The output is ready for knowledge graph applications, clinical decision support systems, and drug pricing platforms.

---

## Data Sources

| Source | Records | Role |
|--------|---------|------|
| DailyMed (FDA) | ~51K labels | Package inserts / SPL XML with structured sections |
| RxNorm (NIH) | ~100K entities | Drug terminology and relationships (IN to SCDC to SCD to SBD) |
| FDA NDC | ~250K codes | Product and packaging identifiers |
| PubChem | ~3K compounds | Chemical structures and molecular properties (SMILES, InChIKey) |

---

## Pipeline Architecture

The pipeline runs 12 stages orchestrated by `run_pipeline.py`:

| Step | Stage | Script | Description |
|------|-------|--------|-------------|
| 1 | DailyMed | `01_dailymed/dailymed_pipeline.py` | Parse SPL XML into structured sections |
| 2 | RxNorm | `02_rxnorm/01_rxnorm_to_grc20.py` | Convert RxNorm RRF to GRC-20 entities |
| 3 | NDC | `03_ndc/01_extract_ndcs.py` | Extract NDC codes from FDA directory |
| 4 | NDC | `03_ndc/02_build_ndc_setid.py` | Map NDCs to DailyMed Set IDs |
| 5 | NDC | `03_ndc/02_ndc_bridge_to_grc20.py` | Bridge NDC data into GRC-20 format |
| 6 | PubChem | `04_pubchem/01_enrich_by_cid.py` | Match compounds by PubChem CID |
| 7 | PubChem | `04_pubchem/02_fetch_properties.py` | Fetch molecular properties |
| 8 | Merge | `05_merge/01_merge_enrich.py` | Merge all sources into unified graph |
| 9 | Merge | `05_merge/02_link_pi_to_rxnorm.py` | Link package inserts to RxNorm |
| 10 | DailyMed | `06_dailymed_link/01_link_dailymed_to_rxnorm_by_setid.py` | Link DailyMed to RxNorm by Set ID |
| 11 | Provenance | `provenance_manager.py` | Ensure 100% provenance coverage |
| 12 | Validate | `00_schema/validate_all.py` | Validate final graph against schema |

### Data Model

```
INGREDIENT (IN) ──has_ingredient──→ SCDC/SCDF/SCDG ──consists_of──→ SCD ──tradename_of──→ SBD
        │                                                                          │
        └────────────────── maps_to_rxcui ──────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
              NDC (Product)                  PackageInsert
              00169-4307-01                       │
                                             has_section
                                                  ▼
                                         BOXED_WARNING, INDICATIONS,
                                         DOSAGE_ADMIN, CONTRAINDICATIONS, ...
```

---

## Outputs

The pipeline produces the following in `data/grc20_v2/`:
- `grc20_merged_entities.jsonl` — 570K+ entities in GRC-20 format
- `grc20_merged_relations.jsonl` — 1.5M+ relations
- `provenance_ledger.json` — Full provenance tracking
- `pipeline_config.json` — Pipeline configuration snapshot
- `pipeline_state.json` — Runtime state for resumable execution

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Language | Python 3.10+ |
| Data Processing | Custom parsers, fuzzy matching |
| Graph Format | GRC-20 compliant JSONL |
| Database | Neo4j (optional, for direct loading) |
| External APIs | Venice AI (description enrichment), PubChem REST |

---

## Getting Started

### Prerequisites

- Python 3.10+
- ~50GB disk space for raw data (DailyMed SPL XML, RxNorm RRF, NDC, PubChem)
- Optional: Neo4j for direct graph loading
- Optional: Venice AI API key for description enrichment

### Installation

```bash
# Clone the repo
git clone https://github.com/RK255/pharma-knowledge-graph.git
cd pharma-knowledge-graph

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Set the base data directory (where raw data lives)
export GRC20_BASE_DIR=/path/to/your/data/root
```

### Running the Pipeline

```bash
# Interactive mode (configures data paths)
python run_pipeline.py

# Or run individual stages
python 01_dailymed/dailymed_pipeline.py
python 02_rxnorm/01_rxnorm_to_grc20.py
# ... etc
```

### Validation

```bash
python 00_schema/validate_all.py
```

---

## Project Structure

```
pharma-knowledge-graph/
├── config.py                 # Central config (env-driven paths)
├── run_pipeline.py           # 12-step orchestrator
├── 00_preflight.py            # Interactive config menu
├── 00_schema/                 # GRC-20 schema and validators
├── 01_dailymed/              # DailyMed SPL parsing
├── 02_rxnorm/                # RxNorm to GRC-20 conversion
├── 03_ndc/                   # NDC extraction and bridging
├── 04_pubchem/               # PubChem enrichment
├── 05_merge/                 # Merge and link all sources
├── 06_dailymed_link/         # DailyMed to RxNorm linking
├── 07_export/                # Export and pricing integration
│   └── geo_extract/          # Live extractor package
├── 08_reports/               # Query and reporting scripts
├── provenance_manager.py     # Provenance enforcement
├── shared_state.py           # Cross-step state
└── progress.py               # Progress tracking
```

---

## Background

Built as part of a curator program for a web3 startup building a decentralized pharmaceutical knowledge graph. The goal was to create a production-grade pipeline that bridges clinical pharmacy expertise with modern data engineering, producing a fully provenance-tracked knowledge graph in GRC-20 format.

---

## Author

**Kevin Garvey, PharmD, MBA** — Clinical Pharmacist and Pharmaceutical Data Engineer

- Website: [geopharma.app/resume](https://geopharma.app/resume)
- GitHub: [@RK255](https://github.com/RK255)

---

## License

[MIT](LICENSE)
