#!/usr/bin/env python3
"""
Link DailyMed to RxNorm via Set ID
==================================
Creates relations between PackageInserts and RxNorm entities using SPL Set IDs.

Strategy:
  1. Load RxCUI → Set ID mapping
  2. Build reverse mapping: Set ID → RxCUIs
  3. For each PackageInsert (has fda_set_id):
     - Find matching RxCUIs via set_id
     - Create maps_to_rxcui relation

Input:
  - data/raw_data/rxcui_to_setid.json (RxCUI → Set IDs)
  - data/grc20_v2/grc20_merged_entities.jsonl (RxNorm and DailyMed entities)
  
Output:
  - data/grc20_v2/dailymed_rxnorm_links_relations.jsonl
"""

import json
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

# Add schema path
sys.path.insert(0, str(BASE_DIR / "scripts" / "production" / "pipeline" / "00_schema"))
from pharma_schema import PharmaSchema

schema = PharmaSchema()

# Property/relation IDs
RXCUI_PROP = schema.properties.get('rxcui')
FDA_SET_ID_PROP = schema.properties.get('fda_set_id')
MAPS_TO_RXCUI_REL = schema.relations.get("maps_to_rxcui")


def generate_uuid(seed_string: str) -> str:
    """Generate deterministic UUID from seed string."""
    import hashlib
    return hashlib.md5(seed_string.encode()).hexdigest()


def load_setid_mapping():
    """Load RxCUI → Set ID mapping and build reverse mapping."""
    setid_file = RAW_DATA_DIR / "rxcui_to_setid.json"
    
    if not setid_file.exists():
        print(f"ERROR: {setid_file} not found. Run NDC extraction first.")
        sys.exit(1)
    
    with open(setid_file, 'r') as f:
        data = json.load(f)
    
    # Build reverse mapping: set_id → [rxcuis]
    setid_to_rxcui = {}
    rxcui_to_setids = data.get('rxcui_to_setids', {})
    
    for rxcui, setids in rxcui_to_setids.items():
        for setid in setids:
            if setid not in setid_to_rxcui:
                setid_to_rxcui[setid] = []
            setid_to_rxcui[setid].append(rxcui)
    
    print(f"Loaded {len(setid_to_rxcui):,} Set ID → RxCUI mappings")
    return setid_to_rxcui


def load_rxcui_to_entity():
    """Load RxNorm entities and build RxCUI → entity_id mapping."""
    rxcui_to_entity = {}
    entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
    
    print("Loading RxNorm entities for RxCUI mapping...")
    with open(entities_file, 'r') as f:
        for i, line in enumerate(f):
            try:
                entity = json.loads(line)
                
                # Find RxCUI in values
                for val in entity.get('values', []):
                    if val is None:
                        continue
                    if val.get('property') == RXCUI_PROP:
                        rxcui = val.get('value')
                        if rxcui:
                            rxcui_to_entity[str(rxcui)] = entity['id']
                        break
            except json.JSONDecodeError:
                continue
    
    print(f"Loaded {len(rxcui_to_entity):,} RxCUI → entity mappings")
    return rxcui_to_entity


def load_package_inserts():
    """Load PackageInsert entities with fda_set_id."""
    package_inserts = []
    entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
    
    print("Loading DailyMed PackageInserts...")
    with open(entities_file, 'r') as f:
        for line in f:
            try:
                entity = json.loads(line)
                
                # Check if this is a PackageInsert (has fda_set_id)
                for val in entity.get('values', []):
                    if val is None:
                        continue
                    if val.get('property') == FDA_SET_ID_PROP:
                        set_id = val.get('value')
                        if set_id:
                            package_inserts.append({
                                'id': entity['id'],
                                'name': entity.get('name', 'Unknown'),
                                'fda_set_id': set_id,
                            })
                        break
            except json.JSONDecodeError:
                continue
    
    print(f"Loaded {len(package_inserts):,} PackageInserts")
    return package_inserts


def main():
    print("=" * 80)
    print("LINKING DAILYMED PACKAGE INSERTS TO RXNORM VIA SET IDs")
    print("=" * 80)
    
    # Step 1: Load Set ID → RxCUI mapping
    print("\n[1/4] Loading Set ID mappings...")
    setid_to_rxcui = load_setid_mapping()
    
    # Step 2: Load RxCUI → entity mapping
    print("\n[2/4] Loading RxNorm entities...")
    rxcui_to_entity = load_rxcui_to_entity()
    
    # Step 3: Load PackageInserts
    print("\n[3/4] Loading PackageInserts...")
    package_inserts = load_package_inserts()
    
    # Step 4: Create relations
    print("\n[4/4] Creating PackageInsert → RxNorm relations...")
    
    relations = []
    stats = {
        'total_pis': len(package_inserts),
        'pis_linked': 0,
        'pis_not_linked': 0,
        'total_relations': 0,
        'setids_not_found': 0,
        'rxcuis_not_found': 0,
    }
    
    for pi in package_inserts:
        set_id = pi['fda_set_id']
        
        # Find RxCUIs with this set_id
        rxcuis = setid_to_rxcui.get(set_id, [])
        
        if not rxcuis:
            stats['setids_not_found'] += 1
            stats['pis_not_linked'] += 1
            continue
        
        linked = False
        for rxcui in rxcuis:
            entity_id = rxcui_to_entity.get(rxcui)
            if not entity_id:
                stats['rxcuis_not_found'] += 1
                continue
            
            linked = True
            
            # Create maps_to_rxcui relation
            rel = {
                'id': generate_uuid(f"{pi['id']}_maps_to_{entity_id}"),
                'type': MAPS_TO_RXCUI_REL,
                'from': pi['id'],
                'to': entity_id,
            }
            relations.append(rel)
            stats['total_relations'] += 1
        
        if linked:
            stats['pis_linked'] += 1
        else:
            stats['pis_not_linked'] += 1
    
    # Write output
    print("\n" + "=" * 80)
    print("WRITING OUTPUT")
    print("=" * 80)
    
    relations_file = DATA_DIR / "dailymed_rxnorm_links_relations.jsonl"
    with open(relations_file, 'w') as f:
        for rel in relations:
            f.write(json.dumps(rel) + '\n')
    print(f"\n✅ Wrote {len(relations):,} relations to {relations_file}")
    
    # Write summary
    summary = {
        'created': datetime.now().isoformat(),
        'stats': stats,
        'method': 'set_id_matching',
    }
    summary_file = DATA_DIR / "dailymed_rxnorm_links_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"✅ Wrote summary to {summary_file}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total PackageInserts: {stats['total_pis']:,}")
    print(f"Linked: {stats['pis_linked']:,}")
    print(f"Not linked: {stats['pis_not_linked']:,}")
    print(f"Total relations: {stats['total_relations']:,}")
    print(f"Coverage: {100 * stats['pis_linked'] / max(stats['total_pis'], 1):.1f}%")
    print("=" * 80)


if __name__ == '__main__':
    main()
