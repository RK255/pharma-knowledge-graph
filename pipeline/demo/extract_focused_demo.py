#!/usr/bin/env python3
"""
Extract a focused demo dataset:
- 5 Ingredients (IN) with their properties
- Downstream products (SCDC, SCDF, SCD, SBDC, SBDF, SBD, BrandName)
- NDCs linked to SBDs
"""

import json
from pathlib import Path

# Our 5 target ingredients
TARGET_INGREDIENTS = {
    "bupropion": "42f994c5ce455c968137883f08082bc2",
    "metoprolol": "8c71cc01e4735556a82357680833f262",
    "penicillin G": "e56d0ef7aa9d577bac7db658da505492",
    "rosuvastatin": "253ba70f272e5b25b166f8da19c54ba8",
    "semaglutide": "197d66802ab55e2791fe4e953d8377f5",
}

def load_jsonl(path):
    data = []
    with open(path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def main():
    base_path = Path("data/grc20_v2")
    
    # Load data
    print("Loading data...")
    entities = load_jsonl(base_path / "grc20_merged_entities.jsonl")
    relations = load_jsonl(base_path / "grc20_merged_relations.jsonl")
    
    # Build entity lookup
    entity_map = {e["id"]: e for e in entities}
    
    # Track what we need
    ingredient_ids = set(TARGET_INGREDIENTS.values())
    collected_entities = {}  # id -> entity
    collected_relations = []  # list of relations
    
    # Add our target ingredients
    for ing_id in ingredient_ids:
        if ing_id in entity_map:
            collected_entities[ing_id] = entity_map[ing_id]
            print(f"  Found ingredient: {entity_map[ing_id]['name']}")
    
    # Step 1: Find products that contain our ingredients (ingredient_of relations)
    print("\nFinding products containing ingredients...")
    for rel in relations:
        if rel.get("to") in ingredient_ids:
            # This product contains our ingredient
            collected_relations.append(rel)
            product_id = rel.get("from")
            if product_id in entity_map:
                collected_entities[product_id] = entity_map[product_id]
    
    # Step 2: Find downstream relations from those products
    print("Finding downstream products...")
    product_ids = set(collected_entities.keys()) - ingredient_ids
    
    # Relations to traverse: constitutes, has_dose_form, has_tradename, inverse_isa
    downstream_types = [
        "88c43b5be4eb5fe78b09872e9a9c3c70",  # constitutes
        "29f07e00f9d45f76aef7e6c03f00441b",  # has_dose_form
        "a42836a8c04757e1a995531b8ff3200b",  # has_tradename
        "dd9264e954d650f98f97cc5d471e5a51",  # inverse_isa (is_a)
        "d0b2263a97d651ae8e43aab87e69ea18",  # has_doseformgroup
    ]
    
    for rel in relations:
        if rel.get("from") in product_ids and rel.get("type") in downstream_types:
            collected_relations.append(rel)
            target_id = rel.get("to")
            if target_id in entity_map:
                collected_entities[target_id] = entity_map[target_id]
    
    # Step 3: Find NDCs linked to SBDs
    print("Finding NDCs...")
    ndc_relations = load_jsonl(base_path / "ndc_bridge_relations.jsonl")
    ndc_entities = load_jsonl(base_path / "ndc_bridge_entities.jsonl")
    
    # Map NDC entity IDs
    ndc_entity_map = {e["id"]: e for e in ndc_entities}
    
    # Find NDCs for our SBDs (branded drugs)
    sbd_type = "ab53698cdc9b59ae9b48b6f8131254b3"  # BrandedDrug
    sbd_ids = {eid for eid, e in collected_entities.items() if sbd_type in e.get("types", [])}
    
    print(f"  Found {len(sbd_ids)} SBDs")
    
    for rel in ndc_relations:
        if rel.get("to") in sbd_ids:
            collected_relations.append(rel)
            ndc_id = rel.get("from")
            if ndc_id in ndc_entity_map:
                collected_entities[ndc_id] = ndc_entity_map[ndc_id]
    
    # Output summary
    print(f"\n=== FOCUSED DEMO SUMMARY ===")
    print(f"Ingredients: {len(ingredient_ids)}")
    print(f"Total entities: {len(collected_entities)}")
    print(f"Total relations: {len(collected_relations)}")
    
    # Count by type
    type_counts = {}
    for e in collected_entities.values():
        for t in e.get("types", []):
            type_counts[t] = type_counts.get(t, 0) + 1
    
    print(f"\nEntities by type:")
    for tid, count in sorted(type_counts.items(), key=lambda x: -x[1])[:15]:
        # Find type name from entities
        sample = next((e for e in collected_entities.values() if tid in e.get("types", [])), None)
        type_name = sample.get("tty", tid[:8]) if sample else tid[:8]
        print(f"  {type_name}: {count}")
    
    # Count NDCs
    ndc_type = "76fa853e896f5354b4f2d9d3f86f4261"
    ndc_count = type_counts.get(ndc_type, 0)
    print(f"\nNDCs: {ndc_count}")
    
    # Save results
    output_dir = Path("scripts/production/pipeline/demo_focused")
    output_dir.mkdir(exist_ok=True)
    
    with open(output_dir / "entities.jsonl", "w") as f:
        for e in collected_entities.values():
            f.write(json.dumps(e) + "\n")
    
    with open(output_dir / "relations.jsonl", "w") as f:
        for r in collected_relations:
            f.write(json.dumps(r) + "\n")
    
    print(f"\nSaved to {output_dir}")

if __name__ == "__main__":
    main()
