
# Demo Pharmaceutical Ontology

This ontology describes the entities, properties, and relationships used in the demo dataset,
which contains 5 drug ingredients (rosuvastatin, semaglutide, bupropion, metoprolol, penicillin G)
and their Level 1 and Level 2 connections in the pharmaceutical knowledge graph.

## Entity Types (16)

### Core Drug Types

| Type | Description | Count in Demo |
|------|-------------|---------------|
| Ingredient | Active pharmaceutical ingredient (generic) | 9 |
| PreciseIngredient | Specific salt/form of an ingredient | 11 |
| MultipleIngredient | Combination ingredient | 5 |

### Clinical Drug Types (Generic)

| Type | Description | Count in Demo |
|------|-------------|---------------|
| ClinicalDrug | Fully specified generic drug product | 75 |
| ClinicalDrugComponent | Ingredient + strength (generic) | 59 |
| ClinicalDrugForm | Drug + dose form (generic) | 14 |
| ClinicalDrugGroup | Drug group (generic) | 20 |
| ClinicalDrugGroupPrecise | Precise drug group (generic) | 15 |

### Branded Drug Types

| Type | Description | Count in Demo |
|------|-------------|---------------|
| BrandedDrug | Fully specified branded drug product | 66 |
| BrandedDrugComponent | Ingredient + strength (branded) | 62 |
| BrandedDrugForm | Drug + dose form (branded) | 16 |
| BrandedDrugGroup | Drug group (branded) | 36 |
| BrandName | Trade name | 20 |

### Other Types

| Type | Description | Count in Demo |
|------|-------------|---------------|
| DoseForm | Route/form of administration | 10 |
| DoseFormGroup | Group of dose forms | 4 |
| TallManSynonym | Tall man lettering synonym | 29 |

## Properties (9)

| Property | Description | Count in Demo |
|----------|-------------|---------------|
| name | Entity name | 451 |
| rxcui | RxNorm Concept Unique Identifier | 451 |
| tty | RxNorm Term Type | 451 |
| smiles | SMILES chemical notation | 9 |
| inchikey | InChI Key | 9 |
| iupac_name | IUPAC chemical name | 9 |
| mesh_classes | MeSH classification | 9 |
| pmid | PubMed ID | 9 |
| sid | Source ID | 9 |

## Relations (22)

### Hierarchical Relations

| Relation | Inverse | Description |
|----------|---------|-------------|
| is_a | inverse_isa | Subclass relationship |
| inverse_isa | is_a | Inverse of is_a |

### Composition Relations

| Relation | Inverse | Description |
|----------|---------|-------------|
| has_ingredient | ingredient_of | Drug contains ingredient |
| ingredient_of | has_ingredient | Ingredient is in drug |
| has_precise_ingredient | precise_ingredient_of | Drug contains precise ingredient |
| precise_ingredient_of | has_precise_ingredient | Precise ingredient is in drug |
| has_ingredients | ingredients_of | Multiple ingredients |
| ingredients_of | has_ingredients | In multiple ingredients |
| has_part | part_of | Has component part |
| part_of | has_part | Is component part |

### Structure Relations

| Relation | Inverse | Description |
|----------|---------|-------------|
| constitutes | consists_of | Component constitutes drug |
| consists_of | constitutes | Drug consists of component |
| has_dose_form | dose_form_of | Drug has dose form |
| dose_form_of | has_dose_form | Form of drug |
| has_doseformgroup | doseformgroup_of | Drug has dose form group |
| doseformgroup_of | has_doseformgroup | Group of dose form |

### Brand Relations

| Relation | Inverse | Description |
|----------|---------|-------------|
| tradename_of | has_tradename | Ingredient has trade name |
| has_tradename | tradename_of | Trade name for ingredient |

### Form Relations

| Relation | Inverse | Description |
|----------|---------|-------------|
| form_of | has_form | Precise ingredient is form of ingredient |
| has_form | form_of | Ingredient has precise form |

### Other Relations

| Relation | Inverse | Description |
|----------|---------|-------------|
| has_boss | boss_of | Has boss (brand organization) |
| boss_of | has_boss | Boss of |

## Data Files

- `demo_entities.jsonl` - 451 entities
- `demo_relations.jsonl` - 3,224 relations
- `demo_schema.json` - Schema definition with IDs
