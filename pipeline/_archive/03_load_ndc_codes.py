#!/usr/bin/env python3
"""
Load NDC codes into NDC bridge entities by matching NDC entity IDs to the raw mapping.
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

NDC_PROP_ID = "652c0094d6835a7b875fcfe6bf3c361a"
ND_REL_TYPE = "3388fed7686d55618cdedbc4cd1cfa09"


def main():
    # Load NDC → RxCUI mapping
    with open(RAW_DATA_DIR / "ndc_to_rxcui.json") as f:
        data = json.load(f)
    ndc_to_rxcui = data.get('ndc_to_rxcui', {})
    print(f"Loaded {len(ndc_to_rxcui):,} NDC → RxCUI mappings")
    
    # Load NDC bridge relations to get NDC entity IDs
    ndc_entities = set()
    with open(DATA_DIR / "ndc_bridge_relations.jsonl") as f:
        for line in f:
            rel = json.loads(line)
            if rel['type'] == ND_REL_TYPE:
                ndc_entities.add(rel['from'])
    print(f"Found {len(ndc_entities):,} NDC entity IDs in relations")
    
    # Now we need to map old NDC entity IDs to NDC codes
    # The old format had entity_id = NDC code (11-digit string)
    # The new format has entity_id = UUID
    
    # Load old format NDC bridge to get entity_id → NDC code mapping
    old_bridge_path = DATA_DIR / "ndc_bridge_entities.json"
    if not old_bridge_path.exists():
        print(f"ERROR: Old bridge not found")
        return
    
    with open(old_bridge_path) as f:
        old_data = json.load(f)
    
    # Build mapping from old entity_id to NDC code
    old_id_to_ndc = {}
    if isinstance(old_data, dict):
        if 'entities' in old_data:
            for e in old_data['entities']:
                if e.get('entity_id') and e.get('ndc'):
                    old_id_to_ndc[e['entity_id']] = e['ndc']
        elif 'id' in old_data:
            old_id_to_ndc[old_data['id']] = old_data.get('ndc')
    
    print(f"Found {len(old_id_to_ndc):,} old NDC entities")
    
    # Find which NDC entity IDs appear in the new format relations
    # and need NDC code values added
    entities_to_update = {}
    for from_id in ndc_entities:
        if from_id in old_id_to_ndc:
            entities_to_update[from_id] = old_id_to_ndc[from_id]
    
    print(f"Found {len(entities_to_update):,} entities to update")
    
    # Now update the entities and relations files
    entities_count = 0
    with open(DATA_DIR / "ndc_bridge_entities.jsonl") as f_in, \
         open(DATA_DIR / "ndc_bridge_entities_updated.jsonl", 'w') as f_out:
        
        for line in f_in:
            entity = json.loads(line)
            if entity['id'] in entities_to_update:
                ndc_code = entities_to_update[entity['id']]
                if entity.get('values') is None:
                    entity['values'] = []
                entity['values'].append({
                    'property': NDC_PROP_ID,
                    'value': ndc_code
                })
                entities_count += 1
            f_out.write(json.dumps(entity) + '\n')
    
    print(f"Updated {entities_count:,} entities")
    print(f"Wrote to {DATA_DIR / 'ndc_bridge_entities_updated.jsonl'}")
    
    # Update relations
    rels_count = 0
    with open(DATA_DIR / "ndc_bridge_relations.jsonl") as f_in, \
         open(DATA_DIR / "ndc_bridge_relations_updated.jsonl", 'w') as f_out:
        
        for line in f_in:
            rel = json.loads(line)
            from_id = rel.get('from')
            if from_id in entities_to_update:
                if rel.get('properties') is None:
                    rel['properties'] = {}
                rel['properties']['ndc'] = entities_to_update[from_id]
                rels_count += 1
            f_out.write(json.dumps(rel) + '\n')
    
    print(f"Updated {rels_count:,} relations")
    print(f"Wrote to {DATA_DIR / 'ndc_bridge_relations_updated.jsonl'}")


if __name__ == "__main__":
    main()
