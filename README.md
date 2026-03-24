# Pharmaceutical Knowledge Graph Pipeline

A production pipeline that transforms pharmaceutical data from multiple sources into a unified GRC-20 compliant knowledge graph.

## Quick Start

```bash
cd pipeline
python run_pipeline.py
Data Model

The pipeline transforms pharmaceutical data from multiple sources into a unified knowledge graph following GRC-20 format.
Entity Hierarchy
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
│                                            │ ... (26 sections)   │              │
│                                            └─────────────────────┘              │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
Relation Directions
From	Relation	To	Description
IN	has_ingredient	SCDC/SCDF/SCDG	Ingredient to drug components
SCDC/SCDF/SCDG	consists_of	SCD	Components to clinical drugs
SCD	tradename_of	SBD	Clinical to branded drugs
NDC	maps_to_rxcui	SBD	NDC codes to branded drugs
PackageInsert	maps_to_rxcui	SBD	Labels to branded drugs
PackageInsert	has_section	Section	Labels to sections
Entity Types (RxNorm TTY Codes)
Code	Type	Description	Count
IN	Ingredient	Active pharmaceutical ingredients	~6K
SCDC	ClinicalDrugComponent	Strength + ingredient combo	~10K
SCDF	ClinicalDrugForm	Dose form (tablet, injection)	~6K
SCDG	ClinicalDrugGroup	Dose form groups	~6K
SCD	ClinicalDrug	Complete clinical drug product	~12K
SBD	BrandedDrug	Branded drug products	~8K
BN	BrandName	Brand names (Rybelsus, Ozempic)	~4K
NDC	NDC	National Drug Codes	~250K
PackageInsert	PackageInsert	FDA drug labels	~51K
Section	Section	Label sections	~1M
Data Sources
Source	Records	Description
RxNorm	~100K entities	Drug terminology and relationships
DailyMed	~51K labels	FDA package inserts with sections
FDA NDC	~250K codes	Product packaging identifiers
PubChem	~3K compounds	Chemical structures and properties
Pipeline Steps
00_schema/          → Schema definition and validation
01_dailymed/        → Parse SPL XML → PackageInsert + Sections
02_rxnorm/          → RxNorm RDF → IN/SCDC/SCDF/SCDG/SCD/SBD entities + relations
03_ndc_bridge/      → FDA NDC Directory → NDC entities + maps_to_rxcui
04_pubchem/         → PubChem API → Chemical enrichment
05_triple_converter/→ Merge all sources → GRC-20 format
06_loaders/         → Neo4j bulk import
