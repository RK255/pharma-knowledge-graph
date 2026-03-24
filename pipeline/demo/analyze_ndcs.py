#!/usr/bin/env python3
import json
from pathlib import Path
from collections import defaultdict

def load_jsonl(path):
    data = []
    with open(path) as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

# Load our focused demo
entities = load_jsonl(Path("scripts/production/pipeline/demo_focused/entities.jsonl"))
relations = load_jsonl(Path("scripts/production/pipeline/demo_focused/relations.jsonl"))

# Build lookups
entity_map = {e["id"]: e for e in entities}

# Our ingredients
INGREDIENTS = {
    "bupropion": "42f994c5ce455c968137883f08082bc2",
    "metoprolol": "8c71cc01e4735556a82357680833f262",
    "penicillin G": "e56d0ef7aa9d577bac7db658da505492",
    "rosuvastatin": "253ba70f272e5b25b166f8da19c54ba8",
    "semaglutide": "197d66802ab55e2791fe4e953d8377f5",
}

# Types
NDC_TYPE = "76fa853e896f5354b4f2d9d3f86f4261"
SBD_TYPE = "ab53698cdc9b59ae9b48b6f8131254b3"
BN_TYPE = "702b256eb8b050daa4c359ff7532ac52"  # BrandName

# Find SBDs linked to each ingredient
print("=== NDCs per Ingredient ===\n")

for ing_name, ing_id in INGREDIENTS.items():
    # Find products containing this ingredient
    product_ids = set()
    for rel in relations:
        if rel.get("to") == ing_id and rel.get("from") != ing_id:
            product_ids.add(rel.get("from"))
    
    # Find SBDs for this ingredient
    sbd_ids = {pid for pid in product_ids if pid in entity_map and SBD_TYPE in entity_map[pid].get("types", [])}
    
    # Find brand names
    brand_names = set()
    for rel in relations:
        if rel.get("from") in product_ids and rel.get("type") == "a42836a8c04757e1a995531b8ff3200b":  # has_tradename
            brand_names.add(entity_map.get(rel.get("to"), {}).get("name", "Unknown"))
    
    # Find NDCs for these SBDs
    ndc_ids = set()
    for rel in relations:
        if rel.get("to") in sbd_ids:
            ndc_ids.add(rel.get("from"))
    
    print(f"{ing_name}:")
    print(f"  Brand names: {', '.join(sorted(brand_names)) if brand_names else 'N/A'}")
    print(f"  SBDs (Branded Drugs): {len(sbd_ids)}")
    print(f"  NDCs: {len(ndc_ids)}")
    print()

# Also show sample NDCs for semaglutide
print("=== Sample NDCs for Semaglutide ===")
semaglutide_id = INGREDIENTS["semaglutide"]
sbd_ids_for_sema = set()
for rel in relations:
    if rel.get("to") == semaglutide_id:
        pid = rel.get("from")
        if pid in entity_map and SBD_TYPE in entity_map[pid].get("types", []):
            sbd_ids_for_sema.add(pid)

for rel in relations:
    if rel.get("to") in sbd_ids_for_sema:
        ndc_id = rel.get("from")
        sbd_id = rel.get("to")
        if ndc_id in entity_map:
            print(f"  {entity_map[ndc_id]['name']} -> {entity_map[sbd_id]['name']}")
