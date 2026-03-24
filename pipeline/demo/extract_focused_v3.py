#!/usr/bin/env python3
"""
Extract a focused demo dataset - v3
Fixed: Don't filter by from_tty, check target TTY instead
"""

import json
from pathlib import Path
from collections import defaultdict

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

def get_tty(entity):
    for v in entity.get("values", []):
        if v.get("property") == "fd0c76eae47c55bbac4cca96203752c1":
            return v.get("value")
    return None

def get_rxcui(entity):
    for v in entity.get("values", []):
        if v.get("property") == "c6f36f8a8e22546ea7618ac008d2f91e":
            return v.get("value")
    return None

def main():
    base_path = Path("data/grc20_v2")
    
    print("Loading data...")
    rxnorm_entities = load_jsonl(base_path / "rxnorm_entities.jsonl")
    rxnorm_relations = load_jsonl(base_path / "rxnorm_relations.jsonl")
    ndc_relations = load_jsonl(base_path / "ndc_bridge_relations.jsonl")
    ndc_entities = load_jsonl(base_path / "ndc_bridge_entities.jsonl")
    
    entity_map = {e["id"]: e for e in rxnorm_entities}
    ndc_entity_map = {e["id"]: e for e in ndc_entities}
    
    print("Building relation indexes...")
    outgoing = defaultdict(list)
    
    for rel in rxnorm_relations:
        from_id = rel.get("from")
        to_id = rel.get("to")
        
        rel_type = None
        from_tty = None
        to_tty = None
        for v in rel.get("values", []):
            if v.get("property") == "9a38ee871c3e539e913214a93acd9b6e":
                rel_type = v.get("value")
            elif v.get("property") == "41ac105d8aa252f5b8259a21b2f547d0":
                from_tty = v.get("value")
            elif v.get("property") == "8dd5dd093a06511fb98fba72f8dad11e":
                to_tty = v.get("value")
        
        outgoing[from_id].append((to_id, rel_type, from_tty, to_tty))
    
    # Build NDC index
    print("Building NDC index...")
    ndc_by_sbd = defaultdict(list)
    for rel in ndc_relations:
        sbd_id = rel.get("to")
        ndc_id = rel.get("from")
        if sbd_id and ndc_id:
            ndc_by_sbd[sbd_id].append(ndc_id)
    
    collected_entities = {}
    results = {}
    
    print("\n=== Processing Ingredients ===\n")
    
    for ing_name, ing_id in TARGET_INGREDIENTS.items():
        print(f"Processing {ing_name}...")
        
        if ing_id not in entity_map:
            print(f"  WARNING: Ingredient not found!")
            continue
        
        ing_entity = entity_map[ing_id]
        collected_entities[ing_id] = ing_entity
        
        result = {
            "name": ing_name,
            "rxcui": get_rxcui(ing_entity),
            "brand_names": [],
            "sbds": [],
            "ndcs": [],
        }
        
        # Step 1: Find brand names via tradename_of (don't filter by from_tty)
        brand_ids = set()
        for to_id, rel_type, from_tty, to_tty in outgoing[ing_id]:
            if rel_type == "tradename_of" and to_tty == "BN":
                brand_ids.add(to_id)
                if to_id in entity_map:
                    collected_entities[to_id] = entity_map[to_id]
                    result["brand_names"].append(entity_map[to_id]["name"])
        
        # Step 2: Find SCDC/SCDF/SCDG via has_ingredient
        # Check target TTY to filter product types
        product_forms = set()
        for to_id, rel_type, from_tty, to_tty in outgoing[ing_id]:
            if rel_type == "has_ingredient" and to_tty in ["SCDC", "SCDF", "SCDG", "SCD", "SBD"]:
                if to_id in entity_map:
                    product_forms.add(to_id)
                    collected_entities[to_id] = entity_map[to_id]
        
        # Step 3: Find SCDs/SBDs via consists_of, tradename_of
        scd_sbd_ids = set()
        for form_id in product_forms:
            for to_id, rel_type, from_tty, to_tty in outgoing[form_id]:
                if rel_type in ["consists_of", "has_dose_form", "has_doseformgroup", "tradename_of"]:
                    if to_id in entity_map:
                        tty = get_tty(entity_map[to_id])
                        if tty in ["SCD", "SBD"]:
                            scd_sbd_ids.add(to_id)
                            collected_entities[to_id] = entity_map[to_id]
        
        # Step 4: Find SBDs via has_ingredient from BrandName
        for brand_id in brand_ids:
            for to_id, rel_type, from_tty, to_tty in outgoing[brand_id]:
                if rel_type == "has_ingredient":
                    if to_id in entity_map:
                        tty = get_tty(entity_map[to_id])
                        if tty == "SBD":
                            scd_sbd_ids.add(to_id)
                            collected_entities[to_id] = entity_map[to_id]
        
        # Step 5: Find NDCs
        for sbd_id in scd_sbd_ids:
            sbd_entity = entity_map.get(sbd_id)
            if sbd_entity:
                tty = get_tty(sbd_entity)
                if tty == "SBD":
                    result["sbds"].append({
                        "name": sbd_entity["name"],
                        "rxcui": get_rxcui(sbd_entity),
                        "ndc_count": len(ndc_by_sbd[sbd_id])
                    })
            
            for ndc_id in ndc_by_sbd[sbd_id]:
                if ndc_id in ndc_entity_map:
                    collected_entities[ndc_id] = ndc_entity_map[ndc_id]
                    result["ndcs"].append(ndc_entity_map[ndc_id]["name"])
        
        results[ing_name] = result
        brands_preview = result['brand_names'][:3]
        print(f"  Brands: {brands_preview}{'...' if len(result['brand_names']) > 3 else ''}")
        print(f"  Product forms: {len(product_forms)}")
        print(f"  SCDs/SBDs: {len(scd_sbd_ids)}")
        print(f"  SBDs: {len(result['sbds'])}")
        print(f"  NDCs: {len(result['ndcs'])}")
    
    # Summary
    print("\n" + "="*60)
    print("FOCUSED DEMO SUMMARY")
    print("="*60)
    
    total_ndcs = 0
    total_sbds = 0
    for ing_name, result in results.items():
        print(f"\n{ing_name.upper()}")
        print(f"  RxCUI: {result['rxcui']}")
        brands_str = ', '.join(result['brand_names']) if result['brand_names'] else 'N/A'
        print(f"  Brands: {brands_str}")
        print(f"  SBDs: {len(result['sbds'])}")
        for sbd in result['sbds'][:2]:
            name = sbd['name'][:55] + '...' if len(sbd['name']) > 55 else sbd['name']
            print(f"    - {name} ({sbd['ndc_count']} NDCs)")
        if len(result['sbds']) > 2:
            print(f"    ... and {len(result['sbds']) - 2} more")
        print(f"  NDCs: {len(result['ndcs'])}")
        total_ndcs += len(result['ndcs'])
        total_sbds += len(result['sbds'])
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {len(results)} ingredients, {total_sbds} SBDs, {total_ndcs} NDCs")
    print(f"Total entities: {len(collected_entities)}")
    
    # Save
    output_dir = Path("scripts/production/pipeline/demo_focused")
    output_dir.mkdir(exist_ok=True)
    
    with open(output_dir / "entities.jsonl", "w") as f:
        for e in collected_entities.values():
            f.write(json.dumps(e) + "\n")
    
    with open(output_dir / "summary.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nSaved to {output_dir}")

if __name__ == "__main__":
    main()
