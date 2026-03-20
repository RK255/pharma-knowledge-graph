# GRC-20 Pharmaceutical Knowledge Graph Schema

**Version:** 3.0.0  
**Generated:** 2026-03-06  
**Total Entities:** 1,143,244  
**Entity Types:** 30  
**Attributes:** 34  
**Relations:** 53  

---

## Overview

This document describes the schema for the GRC-20 Pharmaceutical Knowledge Graph, which integrates data from multiple authoritative sources:

| Source | Description | Entity Count | Primary Content |
|--------|-------------|--------------|-----------------|
| **RxNorm** | NLM's normalized naming system for drugs | ~330,000 | Drug concepts, ingredients, dose forms, relationships |
| **DailyMed** | FDA SPL package insert data | ~3,000 | Package inserts, sections, manufacturer info |
| **PubChem** | NIH's chemical database | ~2,900 | Chemical properties, identifiers, synonyms |
| **NDC Bridge** | FDA NDC to RxNorm mapping | ~250,000 | NDC codes linked to drugs |

---

## Entity Types

### Core Drug Entities (RxNorm)

| Type | ID | Description | TTY Codes | Count |
|------|-------|-------------|-----------|-------|
| **Ingredient** | `8uPJu9J5wpUQprjjwpbaQe` | Active pharmaceutical ingredients | IN, PIN, MIN | ~28,000 |
| **PreciseIngredient** | `QRSj1KHuH65v1jMfcKDCJg` | Precisely defined ingredients | PIN | ~2,000 |
| **MultipleIngredient** | `Xw4SsyhS3XGPNm6bSXT89Y` | Multi-ingredient compounds | MIN | ~10,000 |
| **SpecificSubstance** | `8pYvqZWeQTMige4GDF3LBP` | Specific substance definitions | SS | ~5,000 |
| **ClinicalDrug** | `N7w9zjvcYYrbkXBHV9gMjo` | Clinical drug products | SCD | ~85,000 |
| **BrandedDrug** | `YCNgj5mHvgrWMqV3fjv8Ky` | Branded drug products | SBD | ~100,000 |
| **BrandedDrugComponent** | `VeUiTJr93NGR5cyZaGn6Jd` | Components of branded drugs | SBDC | ~50,000 |
| **ClinicalDrugComponent** | `SqgKjVPyQQ7HH3bVpPLX2n` | Components of clinical drugs | SCC | ~40,000 |
| **BrandName** | `EA1JdK4kFXFjbpGDLhPwA3` | Brand/trade names | BN, TBN | ~40,000 |
| **DoseForm** | `VAkPxuLsXvTZsKXhfAWpjW` | Dosage forms (tablet, capsule, etc.) | DF, EDF | ~300 |
| **DoseFormGroup** | `4UfgjHAsRKZwvH2jFuKguP` | Grouped dose forms | DG | ~50 |

### Extended Drug Entities (RxNorm Extended)

| Type | ID | Description | TTY Codes | Count |
|------|-------|-------------|-----------|-------|
| **Drug** | `2Lrexk4c9uumQ6hgPk3kaL` | Generic drug entities | Various | ~5,000 |
| **SemanticDrug** | `QNDFxpTYSBP5kxKAqJqZRY` | Semantic clinical drugs | SCDC | ~15,000 |
| **SemanticBrandedDrug** | `YwQkaFZKCdrmmGQHZZEpov` | Semantic branded drugs | SBDC | ~20,000 |

### DailyMed/FDA Entities

| Type | ID | Description | Source | Count |
|------|-------|-------------|--------|-------|
| **PackageInsert** | `HoYHubmhgWM9j3BJZXPytL` | FDA SPL documents | DailyMed | ~2,000 |
| **Section** | `BMtTqgGWWkC4oPGUjF2fVZ` | Document sections | DailyMed | ~1,900 |
| **Manufacturer** | `BKvUeEpDLWnZBJqURhAwYr` | Drug manufacturers | DailyMed | ~100 |

### Knowledge Entities (PubChem/External)

| Type | ID | Description | Source | Count |
|------|-------|-------------|--------|-------|
| **DrugClass** | `N9XzcTmhWTPPVvMWvujE4A` | Pharmacological classes | MeSH/RxNorm | ~2,000 |
| **Relation** | `7VAHP97EpjoEcTzWy5eBWK` | Relationship entities | GRC-20 System | ~810,000 |
| **Provenance** | `LA1DqP5v6QAdsgLPXGF3YA` | Data source provenance | Pipeline | 5 |

### GRC-20 System Types

| Type | ID | Description |
|------|-------|-------------|
| **Type** | `Jfmby78N4BCseZinBmdVov` | Meta-type for type definitions |
| **Attribute** | `GscJ2GELQjmLoaVrYyR3xm` | Meta-type for attribute definitions |
| **RelationType** | `3WxYoAVreE4qFhkDUs5J3q` | Meta-type for relation type definitions |

---

## Attributes

### Identity Attributes (All Sources)

| Attribute | ID | Type | Description | Sources |
|-----------|-------|------|-------------|---------|
| **name** | `LuBWqZAu6pz54eiJS5mLv8` | string | Primary name/label | RxNorm, DailyMed, PubChem |
| **rxcui** | `Xj5oEnByf72bBBDwuhTNk9` | string | RxNorm Concept Unique Identifier | RxNorm |
| **ndc_code** | `5kfsHgNaBa1MyoPnujvWcF` | string | National Drug Code | NDC Bridge |
| **pubchem_cid** | `C6PYexgtUqDCnEwkHVYPJg` | integer | PubChem Compound ID | PubChem |
| **sid** | `UAyFng63uEqZrhb77nZeS4` | string | PubChem Substance ID | PubChem |
| **tty** | `LStnttgWUVLE9SiqkeyHNE` | string | RxNorm Term Type | RxNorm |

### Chemical Properties (PubChem)

| Attribute | ID | Type | Description | Source |
|-----------|-------|------|-------------|--------|
| **smiles** | `TC6A8rKVqNRa59vxGkxrPm` | string | SMILES notation | PubChem |
| **inchikey** | `6BzDQSvkPuWZNiYr3yx44Y` | string | InChI Key | PubChem |
| **iupac_name** | `J4nw5Z538TGyQjQqjxBCQa` | string | IUPAC systematic name | PubChem |
| **molecular_formula** | `JVA8rCKim4NaQtJfSxDS5C` | string | Molecular formula | PubChem |
| **molecular_weight** | `BNmgGuUjtS9pLivUZnxtrY` | float | Molecular weight (g/mol) | PubChem |

### Classification Attributes (RxNorm/MeSH)

| Attribute | ID | Type | Description | Source |
|-----------|-------|------|-------------|--------|
| **class_code** | `H2AfGKsw2zTmW8W1YXu8cD` | string | Classification code | MeSH |
| **class_name** | `86Kyy1NF4zKyrsiLWwpmwD` | string | Classification name | MeSH |
| **class_type** | `YXaHx8psN13F1s7kQGaBkP` | string | Classification type | MeSH |
| **mesh_classes** | `HNKzDjusfaiy7eXcnkUFSx` | string | MeSH class identifiers | PubChem |

### Regulatory/FDA Attributes (DailyMed)

| Attribute | ID | Type | Description | Source |
|-----------|-------|------|-------------|--------|
| **fda_set_id** | `NJndhZAxeYCcE8SaW9Mp5S` | string | FDA SPL Set ID | DailyMed |
| **set_id** | `N1TUM1i4cebpwBxfMAvMur` | string | Document set identifier | DailyMed |
| **effective_time** | `AyEDu6WPoEDab35gNWHx7r` | date | Effective date | DailyMed |
| **section_type** | `YaxUwbN9YkeKfuNro7HujG` | string | SPL section type | DailyMed |
| **content** | `R6YEyg2Xc56jRiFx3sRSLg` | string | Section content text | DailyMed |
| **clinical_weight** | `98vHbU6NirXYuePAcnBtr7` | float | Clinical significance weight | Pipeline |

### Provenance Attributes (Pipeline)

| Attribute | ID | Type | Description | Source |
|-----------|-------|------|-------------|--------|
| **provenance** | `LA1DqP5v6QAdsgLPXGF3YA` | entity | Link to provenance entity | Pipeline |
| **source** | `1YW71C9zxbKKw1if3cHnxw` | string | Data source name | Pipeline |
| **citation** | `NiUvsGxauz9xTnBRmtDaiS` | string | Citation string | Pipeline |
| **date_accessed** | `DzBh3RwY7pLutFnyRQjny8` | date | Date data was accessed | Pipeline |
| **source_url** | `NNhSs3oz6Kq6iFfmkEnqy9` | url | Source website URL | Pipeline |
| **provenance_type** | `YP6dZLUSNXnBKxDgi4JzrL` | string | Type: IMPORTED, GENERATED, etc. | Pipeline |

### Reference Attributes (Various)

| Attribute | ID | Type | Description | Source |
|-----------|-------|------|-------------|--------|
| **pmid** | `CgFeDU8jsDjjz6DxnZpCug` | string | PubMed ID | PubChem |
| **pubchem_date** | `PMedFdu7JhU3bomaGS6rkL` | date | PubChem retrieval date | PubChem |
| **rela_code** | `4e89AQTvdi29W51n9Wk4xN` | string | RxNorm relationship code | RxNorm |
| **source_tty** | `MYSBeHU36bZ459oXrZYCXu` | string | Source term type | RxNorm |
| **target_tty** | `BPhM4WY4ry3rJcqjDeAZHA` | string | Target term type | RxNorm |
| **sequence** | `PB6K4qL2RyF1xtH1KQ67sN` | integer | Ordinal position | Pipeline |
| **evidence** | `K44kcyzcDhK29mY85Qbf7t` | string | Evidence/confidence score | Pipeline |

---

## Relations

### Ingredient Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **has_ingredient** | `BvscE1yH5z9xhKqpL1Wv2m` | Drug has ingredient | RxNorm | ~55,000 |
| **ingredient_of** | `AqpL1Wv2mBvscE1yH5z9xhK` | Inverse: ingredient in drug | RxNorm | ~55,000 |

### Dose Form Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **has_dose_form** | `RxVyH5z9xhKqpL1Wv2mBvs` | Drug has dose form | RxNorm | ~32,000 |
| **dose_form_of** | `cE1yH5z9xhKqpL1Wv2mBvs` | Inverse: dose form for drug | RxNorm | ~32,000 |
| **has_doseformgroup** | `qpL1Wv2mBvscE1yH5z9xhK` | Drug has dose form group | RxNorm | ~13,000 |
| **doseformgroup_of** | `Wv2mBvscE1yH5z9xhKqpL1` | Inverse: group for drug | RxNorm | ~13,000 |

### Brand/Trade Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **has_tradename** | `9xhKqpL1Wv2mBvscE1yH5z` | Drug has trade name | RxNorm | ~41,000 |
| **tradename_of** | `hKqpL1Wv2mBvscE1yH5z9x` | Inverse: trade name for drug | RxNorm | ~41,000 |

### Composition Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **constitutes** | `KqpL1Wv2mBvscE1yH5z9xh` | Component constitutes drug | RxNorm | ~36,000 |
| **consists_of** | `pL1Wv2mBvscE1yH5z9xhKq` | Drug consists of component | RxNorm | ~36,000 |
| **has_precise_ingredient** | `L1Wv2mBvscE1yH5z9xhKqp` | Drug has precise ingredient | RxNorm | ~5,000 |
| **precise_ingredient_of** | `1Wv2mBvscE1yH5z9xhKqpL` | Inverse | RxNorm | ~5,000 |
| **has_ingredients** | `Wv2mBvscE1yH5z9xhKqpL1` | Drug has multiple ingredients | RxNorm | ~3,000 |
| **ingredients_of** | `vscE1yH5z9xhKqpL1Wv2mB` | Inverse | RxNorm | ~3,000 |

### Hierarchy Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **is_a** | `E1yH5z9xhKqpL1Wv2mBvsc` | Taxonomic parent | RxNorm | ~78,000 |
| **inverse_isa** | `yH5z9xhKqpL1Wv2mBvscE1` | Taxonomic child | RxNorm | ~78,000 |
| **form_of** | `5z9xhKqpL1Wv2mBvscE1yH` | Drug form relationship | RxNorm | ~8,000 |
| **has_form** | `z9xhKqpL1Wv2mBvscE1yH5` | Inverse | RxNorm | ~8,000 |

### Mapping Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **maps_to_rxcui** | `hKqpL1Wv2mBvscE1yH5z9x` | NDC maps to RxNorm | NDC Bridge | ~246,000 |
| **equivalent_to** | `qpL1Wv2mBvscE1yH5z9xhK` | Semantic equivalence | RxNorm | ~4,000 |

### Part/Contains Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **has_part** | `KqpL1Wv2mBvscE1yH5z9xh` | Drug has part | RxNorm | ~3,000 |
| **part_of** | `pL1Wv2mBvscE1yH5z9xhKq` | Part belongs to drug | RxNorm | ~3,000 |
| **contains** | `L1Wv2mBvscE1yH5z9xhKqp` | Drug contains ingredient | RxNorm | ~2,000 |
| **contained_in** | `1Wv2mBvscE1yH5z9xhKqpL` | Inverse | RxNorm | ~2,000 |

### Special Relationships

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **has_boss** | `Wv2mBvscE1yH5z9xhKqpL1` | Active moiety relationship | RxNorm | ~3,400 |
| **boss_of** | `vscE1yH5z9xhKqpL1Wv2mB` | Inverse | RxNorm | ~3,400 |
| **reformulation_of** | `cE1yH5z9xhKqpL1Wv2mBvs` | Reformulation relationship | RxNorm | ~1 |
| **reformulated_to** | `RxVyH5z9xhKqpL1Wv2mBvs` | Inverse | RxNorm | ~1 |
| **quantified_form_of** | `E1yH5z9xhKqpL1Wv2mBvsc` | Quantified dose form | RxNorm | ~6 |
| **has_quantified_form** | `yH5z9xhKqpL1Wv2mBvscE1` | Inverse | RxNorm | ~6 |

### Document Relationships (DailyMed)

| Relation | ID | Description | Source | Count |
|----------|-------|-------------|--------|-------|
| **has_section** | `5z9xhKqpL1Wv2mBvscE1yH` | Document has section | DailyMed | ~2,000 |
| **manufactured_by** | `z9xhKqpL1Wv2mBvscE1yH5` | Drug manufactured by | DailyMed | ~100 |

---

## Provenance Sources

| Source | Entity ID | Type | Citation | Date |
|--------|-----------|------|----------|------|
| **RxNorm** | `Qc2GnZosDUhfpBUU9digRR` | IMPORTED | RxNorm Release (2026-02-02). National Library of Medicine. | 2026-03-05 |
| **RxNorm RXNSAT** | `RuZxMVbYk7Mg6n4N7q1yQ3` | IMPORTED | RxNorm RXNSAT - Additional attributes from NLM | 2026-03-05 |
| **FDA SPL - DailyMed** | `JPkTcNd9Re97mvmRRnXFWf` | IMPORTED | FDA SPL - Structured Product Labels from DailyMed | 2026-03-05 |
| **PubChem** | `C2BGfrEWSSMbrcx7NoAoNE` | IMPORTED | PubChem Compound Database. National Center for Biotechnology Information. | 2026-03-05 |
| **Pipeline Generated** | `Vi38GjMNzRSCtLHHdAQWbH` | GENERATED | Generated by GRC-20 Pharmaceutical Knowledge Graph Pipeline | 2026-03-05 |

---

## GRC-20 System IDs

These are reserved IDs defined by the GRC-20 specification:

| System Type | ID | Purpose |
|-------------|-------|---------|
| **Type** | `Jfmby78N4BCseZinBmdVov` | Meta-type for all type entities |
| **Attribute** | `GscJ2GELQjmLoaVrYyR3xm` | Meta-type for all attribute entities |
| **Relation** | `QtC4Ay8HNLwSd1kSARgcDE` | Meta-type for all relation entities |
| **RelationType** | `3WxYoAVreE4qFhkDUs5J3q` | Meta-type for relation type entities |

### Relation Attributes (GRC-20 Built-in)

| Attribute | ID | Purpose |
|-----------|-------|---------|
| **from_entity** | `RERshk4JoYoMC17r1qAo9J` | Source entity in a relation |
| **to_entity** | `Qx8dASiTNsxxP3rJbd4Lzd` | Target entity in a relation |
| **index** | `Qx8dASiTNsxxP3rJbd4Lzd` | Ordinal index in ordered relations |

---

## Value Types

GRC-20 supports the following value types for attributes:

| Type ID | Type Name | Description | Example |
|---------|-----------|-------------|---------|
| 1 | string | Text value | "Aspirin" |
| 2 | integer | Whole number | 23662354 |
| 3 | float | Decimal number | 180.16 |
| 4 | url | URL/URI | "https://pubchem.ncbi.nlm.nih.gov" |
| 5 | date | ISO date | "2026-03-05" |
| 6 | boolean | True/False | true |

---

## Data Flow
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ DailyMed │ │ RxNorm │ │ PubChem │
│ (FDA SPL) │ │ (NLM) │ │ (NIH) │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
│ │ │
▼ ▼ ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 01_dailymed │ │ 02_rxnorm │ │ 04_pubchem │
│ pipeline │ │ pipeline │ │ enricher │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
│ │ │
└───────────────────┼───────────────────┘
▼
┌─────────────┐
│ 03_ndc_ │
│ bridge │
└──────┬──────┘
│
▼
┌─────────────┐
│ 05_triple_ │
│ converter │
│ (merge) │
└──────┬──────┘
│
▼
┌─────────────┐
│ provenance │
│ manager │
└──────┬──────┘
│
▼
┌─────────────┐
│ 00_schema/ │
│ validate │
└──────┬──────┘
│
▼
┌─────────────┐
│ grc20_with_ │
│ relations │
│ .json │
└─────────────┘
---

## Statistics Summary
┌─────────────────────────────────────────────────────────────┐
│ GRC-20 KNOWLEDGE GRAPH │
├─────────────────────────────────────────────────────────────┤
│ Total Entities: 1,143,244│
│ - Nodes: 331,464│
│ - Relations: 811,780│
├─────────────────────────────────────────────────────────────┤
│ Entity Types: 30│
│ Attributes: 34│
│ Relation Types: 53│
├─────────────────────────────────────────────────────────────┤
│ Provenance Coverage: 100.0%│
│ Schema Compliance: 100.0%│
├─────────────────────────────────────────────────────────────┤
│ Sources: │
│ - RxNorm: ~330,000 entities, 800,000+ relations │
│ - DailyMed: ~3,000 entities (Package Inserts) │
│ - PubChem: ~2,900 enriched with properties │
│ - NDC Bridge: ~250,000 NDC-to-RxNorm mappings │
└─────────────────────────────────────────────────────────────┘
---

## File Locations

| File | Path | Size |
|------|------|------|
| Schema Cache | `pipeline/00_schema/schema_cache.json` | ~15 KB |
| RxNorm Entities | `data/grc20_v2/rxnorm_entities.json` | ~734 MB |
| DailyMed Entities | `data/grc20_v2/dailymed_entities.json` | ~13 MB |
| NDC Bridge | `data/grc20_v2/ndc_bridge_entities.json` | ~502 MB |
| PubChem Properties | `data/grc20_v2/pubchem_properties.json` | ~2 MB |
| Merged Output | `data/grc20_v2/grc20_merged.json` | ~1.5 GB |
| Final Output | `data/grc20_v2/grc20_with_relations.json` | ~1.2 GB |

---

*Generated by GRC-20 Pharmaceutical Knowledge Graph Pipeline v3.0.0*
