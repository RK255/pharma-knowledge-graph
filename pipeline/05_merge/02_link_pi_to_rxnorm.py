#!/usr/bin/env python3
"""
PackageInsert to RxNorm Linker (Post-Merge)
============================================
Creates relations between PackageInserts and RxNorm drugs using SPL Set IDs.

This script MUST run AFTER the merge step because it needs the merged entity IDs.

Linking Strategy:
  1. Load DailyMed documents (fda_set_id → NDCs mapping)
  2. Load RxCUI → Set ID mapping (from RXNSAT.RRF)
  3. For each PackageInsert:
     - Get fda_set_id from document
     - Find RxCUIs with matching set_id
     - Create maps_to_rxcui relation to those RxCUI entities

Input:
  - data/grc20_v2/grc20_merged_entities.jsonl (PackageInsert entities with fda_set_id)
  - data/grc20_v2/dailymed_documents.json (fda_set_id mapping)
  - data/raw_data/rxcui_to_setid.json (RxCUI → Set ID mapping)
  
Output:
  - Appends to data/grc20_v2/grc20_merged_relations.jsonl
  - data/grc20_v2/dailymed_rxnorm_links_summary.json

Usage:
    python 02_link_pi_to_rxnorm.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

# Add schema path
sys.path.insert(0, str(BASE_DIR / "scripts" / "production" / "pipeline" / "00_schema"))
from pharma_schema import PharmaSchema

schema = PharmaSchema()

# Get property/relation IDs
FDA_SET_ID_PROP = schema.properties.get('fda_set_id')
RXCUI_PROP = schema.properties.get('rxcui')
MAPS_TO_RXCUI_REL = schema.relations.get("maps_to_rxcui")


def generate_uuid(seed_string: str) -> str:
    """Generate deterministic UUID from seed string."""
    import hashlib
    return hashlib.md5(seed_string.encode()).hexdigest()


def load_setid_mapping():
    """Load RxCUI → Set ID mapping."""
    setid_file = RAW_DATA_DIR / "rxcui_to_setid.json"
    
    if not setid_file.exists():
        print(f"ERROR: {setid_file} not found. Run 01_extract_ndcs.py first.")
        sys.exit(1)
    
    with open(setid_file, 'r') as f:
        data = json.load(f)
    
    # Build set_id → rxcuis reverse mapping
    setid_to_rxcui = {}
    rxcui_to_setids = data.get('rxcui_to_setids', {})
    
    for rxcui, setids in rxcui_to_setids.items():
        for setid in setids:
            if setid not in setid_to_rxcui:
                setid_to_rxcui[setid] = []
            setid_to_rxcui[setid].append(rxcui)
    
    print(f"  Loaded {len(setid_to_rxcui):,} Set ID → RxCUI mappings")
    return setid_to_rxcui


def load_dailymed_documents():
    """Load DailyMed documents to get set_id → NDCs mapping."""
    docs_file = DATA_DIR / "dailymed_documents.json"
    
    if not docs_file.exists():
        print(f"ERROR: {docs_file} not found. Run DailyMed parser first.")
        sys.exit(1)
    
    with open(docs_file, 'r') as f:
        docs = json.load(f)
    
    # Build set_id → doc mapping
    setid_to_doc = {}
    for doc in docs:
        set_id = doc.get('fda_set_id')
        if set_id:
            setid_to_doc[set_id] = doc
    
    print(f"  Loaded {len(setid_to_doc):,} Set IDs from DailyMed")
    return setid_to_doc


def load_merged_entities():
    """Load merged entities and build RxCUI → entity_id and set_id → entity_id mappings."""
    entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
    
    if not entities_file.exists():
        print(f"ERROR: {entities_file} not found. Run merge step first.")
        sys.exit(1)
    
    rxcui_to_entity = {}
    setid_to_pi_entity = {}
    pi_entity_count = 0
    
    print(f"  Loading entities from {entities_file}...")
    
    with open(entities_file, 'r') as f:
        for i, line in enumerate(f):
            if i % 200000 == 0 and i > 0:
                print(f"    Processed {i:,} entities...")
            
            e = json.loads(line)
            
            # Check for values
            values = e.get('values', [])
            if not values:
                continue
            
            # Build value lookup
            val_dict = {}
            for val in values:
                if val is None:
                    continue
                prop = val.get('property')
                val_dict[prop] = val.get('value')
            
            # Check if this is an RxNorm entity (has RxCUI)
            rxcui = val_dict.get(RXCUI_PROP)
            if rxcui:
                rxcui_to_entity[rxcui] = e['id']
            
            # Check if this is a PackageInsert (has fda_set_id)
            fda_set_id = val_dict.get(FDA_SET_ID_PROP)
            if fda_set_id:
                setid_to_pi_entity[fda_set_id] = e['id']
                pi_entity_count += 1
    
    print(f"    Found {len(rxcui_to_entity):,} RxCUI entities")
    print(f"    Found {pi_entity_count:,} PackageInsert entities with Set IDs")
    
    return rxcui_to_entity, setid_to_pi_entity


def main():
    print("=" * 80)
    print("PACKAGEINSERT TO RXNORM LINKER (Set ID Based)")
    print("=" * 80)
    
    # Step 1: Load Set ID → RxCUI mapping
    print("\n[1/5] Loading Set ID → RxCUI mapping from RxNorm...")
    setid_to_rxcui = load_setid_mapping()
    
    # Step 2: Load DailyMed documents
    print("\n[2/5] Loading DailyMed documents...")
    setid_to_doc = load_dailymed_documents()
    
    # Step 3: Load merged entities
    print("\n[3/5] Loading merged entities...")
    rxcui_to_entity, setid_to_pi_entity = load_merged_entities()
    
    # Step 4: Create PackageInsert → RxNorm relations
    print("\n[4/5] Creating PackageInsert → RxNorm relations via Set ID...")
    
    relations = []
    stats = {
        'total_pis': len(setid_to_pi_entity),
        'pis_with_match': 0,
        'pis_without_match': 0,
        'total_relations': 0,
        'setids_not_in_rxnorm': 0,
        'rxcuis_not_in_entities': 0,
    }
    
    for set_id, pi_entity_id in setid_to_pi_entity.items():
        # Find RxCUIs with this set_id
        rxcuis = setid_to_rxcui.get(set_id, [])
        
        if not rxcuis:
            stats['setids_not_in_rxnorm'] += 1
            stats['pis_without_match'] += 1
            continue
        
        matched = False
        for rxcui in rxcuis:
            # Find entity for this RxCUI
            rxnorm_entity_id = rxcui_to_entity.get(rxcui)
            
            if not rxnorm_entity_id:
                stats['rxcuis_not_in_entities'] += 1
                continue
            
            matched = True
            
            # Create maps_to_rxcui relation
            rel = {
                'id': generate_uuid(f"{pi_entity_id}_maps_to_{rxnorm_entity_id}"),
                'type': MAPS_TO_RXCUI_REL,
                'from': pi_entity_id,
                'to': rxnorm_entity_id,
            }
            relations.append(rel)
            stats['total_relations'] += 1
        
        if matched:
            stats['pis_with_match'] += 1
        else:
            stats['pis_without_match'] += 1
    
    # Step 5: Append relations to merged file
    print("\n[5/5] Appending relations to merged file...")
    
    relations_file = DATA_DIR / "grc20_merged_relations.jsonl"
    
    # Count existing relations
    existing_count = 0
    if relations_file.exists():
        with open(relations_file, 'r') as f:
            for _ in f:
                existing_count += 1
    
    # Append new relations
    with open(relations_file, 'a') as f:
        for rel in relations:
            f.write(json.dumps(rel) + '\n')
    
    print(f"  Existing relations: {existing_count:,}")
    print(f"  ✅ Appended {len(relations):,} relations")
    print(f"  Total relations now: {existing_count + len(relations):,}")
    
    # Save standalone links file
    links_file = DATA_DIR / "dailymed_rxnorm_links_relations.jsonl"
    with open(links_file, 'w') as f:
        for rel in relations:
            f.write(json.dumps(rel) + '\n')
    print(f"  ✅ Also wrote standalone file: {links_file}")
    
    # Save summary
    summary = {
        'created': datetime.now().isoformat(),
        'stats': stats,
        'method': 'set_id_matching',
    }
    
    summary_file = DATA_DIR / "dailymed_rxnorm_links_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✅ Wrote summary to {summary_file}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"PackageInserts with Set IDs: {stats['total_pis']:,}")
    print(f"PackageInserts linked to RxNorm: {stats['pis_with_match']:,}")
    print(f"PackageInserts NOT linked: {stats['pis_without_match']:,}")
    print(f"Total relations created: {stats['total_relations']:,}")
    print(f"Set IDs not found in RxNorm: {stats['setids_not_in_rxnorm']:,}")
    print(f"RxCUIs not in entities: {stats['rxcuis_not_in_entities']:,}")
    print("=" * 80)
    print("  ✅ Complete")


if __name__ == '__main__':
    main()
