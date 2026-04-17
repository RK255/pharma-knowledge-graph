#!/usr/bin/env python3
"""
PackageInsert to RxNorm Linker (Post-Merge)
============================================
Creates relations between PackageInserts and RxNorm drugs using NDC codes.

This script MUST run AFTER the merge step because it needs the merged entity IDs.

IMPORTANT: One PackageInsert can have MULTIPLE NDCs (different strengths/sizes),
and each NDC can map to a DIFFERENT RxCUI. We create a relation for EACH match.

Input:
  - data/grc20_v2/grc20_merged_entities.jsonl (PackageInsert entities with fda_set_id)
  - data/grc20_v2/dailymed_documents.json (fda_set_id -> ALL NDCs mapping)
  - data/raw_data/ndc_to_rxcui.json (NDC -> RxCUI mapping)
  
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

# Add schema path
sys.path.insert(0, str(BASE_DIR / "scripts" / "production" / "pipeline" / "00_schema"))
from pharma_schema import PharmaSchema

schema = PharmaSchema()

# Get relation type ID for maps_to_rxcui
MAPS_TO_RXCUI_REL = schema.relations.get("maps_to_rxcui")


def generate_uuid(seed_string: str) -> str:
    """Generate deterministic UUID from seed string."""
    import hashlib
    return hashlib.md5(seed_string.encode()).hexdigest()


def load_ndc_to_rxcui_mapping():
    """Load NDC -> RxCUI mapping from ndc_to_rxcui.json."""
    mapping_path = BASE_DIR / "data" / "raw_data" / "ndc_to_rxcui.json"
    with open(mapping_path, 'r') as f:
        data = json.load(f)
    return data.get('ndc_to_rxcui', {})


def load_set_id_to_ndcs():
    """Load fda_set_id -> NDCs mapping from dailymed_documents.json."""
    docs_path = DATA_DIR / "dailymed_documents.json"
    with open(docs_path, 'r') as f:
        docs = json.load(f)
    
    set_id_to_ndcs = {}
    for doc in docs:
        set_id = doc.get('fda_set_id')
        ndcs = doc.get('ndc_codes', [])
        if set_id and ndcs:
            set_id_to_ndcs[set_id] = ndcs
    
    return set_id_to_ndcs


def normalize_ndc(ndc: str) -> str:
    """Normalize NDC to 5-4-2 format for matching."""
    clean = ndc.replace('-', '').replace(' ', '')
    if len(clean) == 10:
        clean = clean.zfill(11)
    return f"{clean[:5]}-{clean[5:9]}-{clean[9:11]}"


def main():
    print("=" * 70)
    print("PACKAGEINSERT TO RXNORM LINKER (Post-Merge)")
    print("=" * 70)
    
    # Check that merged files exist
    merged_entities_path = DATA_DIR / "grc20_merged_entities.jsonl"
    merged_relations_path = DATA_DIR / "grc20_merged_relations.jsonl"
    
    if not merged_entities_path.exists():
        print(f"\n❌ ERROR: {merged_entities_path} not found!")
        print("   This script must run AFTER the merge step.")
        return None
    
    # Step 1: Load NDC -> RxCUI mapping
    print("\n[1/6] Loading NDC -> RxCUI mapping...")
    ndc_to_rxcui = load_ndc_to_rxcui_mapping()
    print(f"  Loaded {len(ndc_to_rxcui):,} NDC -> RxCUI mappings")
    
    # Step 2: Load fda_set_id -> NDCs mapping
    print("\n[2/6] Loading fda_set_id -> NDCs mapping from dailymed_documents.json...")
    set_id_to_ndcs = load_set_id_to_ndcs()
    print(f"  Loaded {len(set_id_to_ndcs):,} Set IDs with NDCs")
    
    # Count total NDCs
    total_ndcs = sum(len(ndcs) for ndcs in set_id_to_ndcs.values())
    print(f"  Total NDCs across all Set IDs: {total_ndcs:,}")
    
    # Step 3: Load RxNorm entities and build RxCUI -> entity_id mapping
    print("\n[3/6] Loading RxNorm entities from merged file...")
    rxcui_to_entity = {}
    
    with open(merged_entities_path, 'r') as f:
        for i, line in enumerate(f):
            if i % 200000 == 0 and i > 0:
                print(f"  Processed {i:,} entities...")
            e = json.loads(line)
            
            # Check if it has an RxCUI (indicates RxNorm entity)
            for val in e.get('values', []):
                if val.get('property') == schema.properties.get('rxcui'):
                    rxcui = val.get('value')
                    if rxcui:
                        rxcui_to_entity[rxcui] = e['id']
                    break
    
    print(f"  Found {len(rxcui_to_entity):,} RxCUI -> entity mappings")
    
    # Step 4: Load PackageInserts and build Set ID -> entity_id mapping
    print("\n[4/6] Loading PackageInserts from merged entities...")
    set_id_prop = schema.properties.get('fda_set_id')
    package_insert_type = schema.type_id('PackageInsert')
    
    set_id_to_pi_id = {}
    with open(merged_entities_path, 'r') as f:
        for i, line in enumerate(f):
            if i % 200000 == 0 and i > 0:
                print(f"  Processed {i:,} entities...")
            e = json.loads(line)
            
            if package_insert_type not in e.get('types', []):
                continue
            
            for val in e.get('values', []):
                if val.get('property') == set_id_prop:
                    set_id = val.get('value')
                    if set_id:
                        set_id_to_pi_id[set_id] = e['id']
                    break
    
    print(f"  Found {len(set_id_to_pi_id):,} PackageInserts with Set IDs")
    
    # Step 5: Create relations - for each PI, link to ALL matching RxCUIs
    print("\n[5/6] Creating PackageInsert -> RxNorm relations...")
    relations_out = []
    
    stats = {
        'total_pis': len(set_id_to_pi_id),
        'pis_with_ndcs': 0,
        'pis_linked': 0,
        'total_relations': 0,
        'total_ndcs_processed': 0,
        'ndc_not_found': 0,
        'rxcui_not_found': 0
    }
    
    seen_links = set()
    pis_linked = set()
    
    for set_id, pi_id in set_id_to_pi_id.items():
        # Get ALL NDCs for this Set ID
        ndcs = set_id_to_ndcs.get(set_id, [])
        if not ndcs:
            continue
        
        stats['pis_with_ndcs'] += 1
        pi_linked = False
        
        for ndc in ndcs:
            stats['total_ndcs_processed'] += 1
            
            # Normalize NDC
            ndc_normalized = normalize_ndc(ndc)
            
            # Look up RxCUI
            rxcui = ndc_to_rxcui.get(ndc_normalized)
            if not rxcui:
                rxcui = ndc_to_rxcui.get(ndc)
            
            if not rxcui:
                stats['ndc_not_found'] += 1
                continue
            
            if isinstance(rxcui, list):
                rxcuis = rxcui
            else:
                rxcuis = [rxcui]
            
            for rxcui_single in rxcuis:
                rxnorm_id = rxcui_to_entity.get(str(rxcui_single))
                if not rxnorm_id:
                    stats['rxcui_not_found'] += 1
                    continue
                
                link_key = (pi_id, rxnorm_id)
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)
                
                rel_id = generate_uuid(f"pi_rxnorm_link:{pi_id}:{rxnorm_id}")
                relation = {
                    'id': rel_id,
                    'type': MAPS_TO_RXCUI_REL,
                    'from': pi_id,
                    'to': rxnorm_id,
                    'values': []
                }
                relations_out.append(relation)
                stats['total_relations'] += 1
                pi_linked = True
        
        if pi_linked:
            pis_linked.add(pi_id)
    
    stats['pis_linked'] = len(pis_linked)
    
    # Step 6: Append relations to merged file
    print("\n[6/6] Appending relations to merged file...")
    
    # Count existing relations
    existing_count = 0
    if merged_relations_path.exists():
        with open(merged_relations_path, 'r') as f:
            for line in f:
                if line.strip():
                    existing_count += 1
        print(f"  Existing relations: {existing_count:,}")
    
    # Append new relations
    with open(merged_relations_path, 'a') as f:
        for rel in relations_out:
            f.write(json.dumps(rel) + '\n')
    
    print(f"  ✅ Appended {len(relations_out):,} relations")
    print(f"  Total relations now: {existing_count + len(relations_out):,}")
    
    # Also write to standalone file for reference
    standalone_path = DATA_DIR / "dailymed_rxnorm_links_relations.jsonl"
    with open(standalone_path, 'w') as f:
        for rel in relations_out:
            f.write(json.dumps(rel) + '\n')
    print(f"  ✅ Also wrote standalone file: {standalone_path}")
    
    # Summary
    summary = {
        'exported_at': datetime.now().isoformat(),
        'schema_version': '4.0.0',
        'source': 'grc20_merged_entities.jsonl + dailymed_documents.json + ndc_to_rxcui.json',
        'stats': stats
    }
    
    summary_path = DATA_DIR / "dailymed_rxnorm_links_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✅ Wrote summary to {summary_path}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"PackageInserts with Set IDs: {stats['total_pis']:,}")
    print(f"PackageInserts with NDCs in docs: {stats['pis_with_ndcs']:,}")
    print(f"PackageInserts linked to RxNorm: {stats['pis_linked']:,}")
    print(f"Total NDCs processed: {stats['total_ndcs_processed']:,}")
    print(f"Total relations: {stats['total_relations']:,}")
    print(f"NDC not found: {stats['ndc_not_found']:,}")
    print(f"RxCUI not found: {stats['rxcui_not_found']:,}")
    print("=" * 70)
    
    return summary


if __name__ == "__main__":
    main()
