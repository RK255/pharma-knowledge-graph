# Pharmaceutical Knowledge Graph

A production-grade pharmaceutical knowledge graph built on GRC-20 format with full provenance tracking.

## Demo Dataset

Included demo with 5 drugs and 2-level relationship traversal. See `pipeline/demo/` for:
- 451 entities
- 3,224 relations
- Ontology documentation

## Architecture
├── pipeline/ # Data ingestion stages (00-06)
├── backend/ # FastAPI + Neo4j + Redis
├── tools/ # Utility scripts (clinical weights, interactions)
└── pipeline/demo/ # Demo dataset for testing
## Pipeline Stages

| Stage | Directory | Description |
|-------|-----------|-------------|
| 00 | 00_schema | Schema definition and validation |
| 01 | 01_dailymed | Parse FDA SPL XML files |
| 02 | 02_rxnorm | Load RxNorm terminology |
| 03 | 03_ndc_bridge | Bridge NDC to RxNorm |
| 04 | 04_pubchem | Enrich with PubChem data |
| 05 | 05_triple_converter | Merge and convert to GRC-20 |
| 06 | 06_loaders | Load data into Neo4j/Redis |

## Schema Overview

### Entity Types (31)

**Core Drug Types:**
- `Ingredient` - Active pharmaceutical ingredient
- `PreciseIngredient` - Specific salt/form of an ingredient
- `MultipleIngredient` - Combination ingredients

**Clinical Drug Types:**
- `ClinicalDrug` - Fully specified generic drug product
- `ClinicalDrugComponent` - Ingredient + strength (generic)
- `ClinicalDrugForm` - Drug + dose form (generic)
- `ClinicalDrugGroup` - Drug group (generic)

**Branded Drug Types:**
- `BrandedDrug` - Fully specified branded drug product
- `BrandedDrugComponent` - Ingredient + strength (branded)
- `BrandedDrugForm` - Drug + dose form (branded)
- `BrandName` - Trade name

**Other Types:**
- `DoseForm`, `DoseFormGroup`, `NDC`, `PubChemCompound`, `Provenance`, and more

### Key Relations

| Relation | Description |
|----------|-------------|
| `has_ingredient` / `ingredient_of` | Drug-ingredient relationships |
| `has_dose_form` / `dose_form_of` | Drug dose forms |
| `tradename_of` / `has_tradename` | Brand relationships |
| `is_a` / `inverse_isa` | Hierarchical classification |
| `maps_to_rxcui` | NDC to RxNorm mapping |

## Quick Start

```bash
# Start Neo4j
docker start neo4j-server

# Start Redis  
docker start redis-server

# Run pipeline
cd pipeline
python run_pipeline.py --all

# Start backend
cd backend
python main.py
Data Sources
Source	Description
RxNorm	Drug terminology
DailyMed	FDA SPL labels
PubChem	Chemical structures
NDC Directory	Product codes
Project Structure
pipeline/
├── 00_schema/
│   ├── pharma_schema.py      # Schema loader
│   ├── ontology/             # CSV schema definitions
│   │   ├── types.csv
│   │   ├── properties.csv
│   │   ├── relation_types.csv
│   │   └── provenance_sources.csv
│   └── schema.json           # Generated schema
├── demo/                     # Demo dataset
└── [01-06]_*/               # Pipeline stages

backend/
├── main.py                   # FastAPI server
├── llm_chat.py               # LLM integration
└── graph_weights_admin.py    # Clinical weights

tools/
├── 08_clinical_weights/      # Expert-curated weights
├── 09_drug_interactions/     # Drug interactions
└── 10_pharmacological_classes/  # Drug classes
License

MIT License
