# GRC-20 Pharmaceutical Knowledge Graph Pipeline

Builds a GRC-20 compliant knowledge graph from pharmaceutical data sources.

## Output

- **570K+ entities** - Drugs, ingredients, manufacturers, package inserts
- **1.5M+ relations** - Connections between entities with full provenance
- **GRC-20 format** - Ready for knowledge graph applications

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
Pipeline Steps
Step	Name	Description
1	DailyMed	Parse FDA drug labels from SPL XML
2	RxNorm	Convert NIH drug terminology to GRC-20
3	NDC Extraction	Extract National Drug Codes from RxNorm
4	NDC Bridge	Link NDCs to RxNorm entities
5	PubChem CID	Match RxNorm ingredients to PubChem compounds
6	PubChem Properties	Fetch molecular properties (SMILES, InChIKey, etc.)
7	Merge & Enrich	Combine all sources into unified knowledge graph
8	Link PI to RxNorm	Connect package inserts to drug entities
9	Link DailyMed to RxNorm	Create additional drug-label relationships
10	Provenance	Ensure 100% provenance coverage
11	Validate	Verify schema compliance and data integrity
Data Model

┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PHARMACEUTICAL KNOWLEDGE GRAPH                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  INGREDIENT (IN)                                                                  │
│  │   Examples: semaglutide, metformin, lisinopril                               │
│  │                                                                                │
│  │  has_ingredient                                                               │
│  └──────────────→ SCDC/SCDF/SCDG (Clinical Drug Components/Forms/Groups)        │
│                     │   SCDC: semaglutide 7 MG (strength component)              │
│                     │   SCDF: semaglutide Oral Tablet (dose form)                │
│                     │   SCDG: semaglutide Oral Product (dose form group)         │
│                     │                                                            │
│                     │  consists_of                                               │
│                     └──────────────→ SCD (Semantic Clinical Drug)               │
│                                        │   semaglutide 7 MG Oral Tablet         │
│                                        │                                         │
│                                        │  tradename_of                          │
│                                        └──────────────→ SBD (Branded Drug)      │
│                                                           │                      │
│                              ┌────────────────────────────┘                      │
│                              │                                                   │
│                              │  maps_to_rxcui                                    │
│                              │                                                   │
│            ┌─────────────────┴─────────────────┐                                │
│            │                                   │                                 │
│            ▼                                   ▼                                 │
│       NDC (Product)                    PackageInsert                            │
│       00169-4307-01                    RYBELSUS-semaglutide                     │
│       00169-4307-13                        │                                    │
│       00169-4307-30                        │  has_section                        │
│                                            └──────────→ Sections                 │
│                                                        │                         │
│                                                        ▼                         │
│                                            ┌─────────────────────┐              │
│                                            │ BOXED_WARNING       │              │
│                                            │ INDICATIONS         │              │
│                                            │ DOSAGE_ADMIN        │              │
│                                            │ CONTRAINDICATIONS   │              │
│                                            │ WARNINGS            │              │
│                                            │ ADVERSE_REACTIONS   │              │
│                                            │ ... (70 sections)   │              │
│                                            └─────────────────────┘              │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
Data Sources
Source	Records	Description
RxNorm	~100K entities	Drug terminology and relationships
DailyMed	~51K labels	FDA package inserts with sections
FDA NDC	~250K codes	Product packaging identifiers
PubChem	~3K compounds	Chemical structures and properties
Output Files

Located in data/grc20_v2/:

    grc20_merged_entities.jsonl - All entities
    grc20_merged_relations.jsonl - All relations
    provenance_ledger.json - Source tracking for all data
    EOF
