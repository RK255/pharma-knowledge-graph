#!/usr/bin/env python3
"""
DailyMed to RxNorm Linker via NDC Bridge
=========================================
Creates relations between DailyMed PackageInserts and RxNorm ClinicalDrugs
using the NDC codes extracted from both sources.

IMPORTANT: One PackageInsert can have MULTIPLE NDCs (different strengths/sizes),
and each NDC can map to a DIFFERENT RxCUI. We create a relation for EACH match.

Input:
  - data/grc20_v2/grc20_merged_entities.jsonl (PackageInsert entities with fda_set_id)
  - data/grc20_v2/dailymed_documents.json (fda_set_id -> ALL NDCs mapping)
  - data/raw_data/ndc_to_rxcui.json (NDC -> RxCUI mapping)
  - data/grc20_v2/rxnorm_entities.jsonl (ClinicalDrug entities)

Output:
  - data/grc20_v2/dailymed_rxnorm_links_relations.jsonl (PackageInsert -> ClinicalDrug relations)
  - data/grc20_v2/dailymed_rxnorm_links_summary.json

Usage:
    python 03_link_dailymed_to_rxnorm.py
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/grc20_v2"

# Add schema path
sys.path.insert(0, f"{BASE_DIR}/scripts/production/pipeline/00_schema")
from pharma_schema import PharmaSchema

schema = PharmaSchema()

# Get relation type ID for maps_to_rxcui (PackageInsert -> ClinicalDrug via NDC)
MAPS_TO_RXCUI_REL = schema.rel("maps_to_rxcui")


def generate_uuid(seed_string: str) -> str:
    """Generate deterministic UUID from seed string."""
    import hashlib
    return hashlib.md5(seed_string.encode()).hexdigest()


def load_ndc_to_rxcui_mapping():
    """Load NDC -> RxCUI mapping from ndc_to_rxcui.json."""
    mapping_path = f"{BASE_DIR}/data/raw_data/ndc_to_rxcui.json"
    with open(mapping_path, 'r') as f:
        data = json.load(f)
    return data.get('ndc_to_rxcui', {})


def load_set_id_to_ndcs():
    """Load fda_set_id -> NDCs mapping from dailymed_documents.json."""
    docs_path = f"{DATA_DIR}/dailymed_documents.json"
    with open(docs_path, 'r') as f:
        docs = json.load(f)
    
    set_id_to_ndcs = {}
    for doc in docs:
        # Use fda_set_id field
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
    print("DAILYMED TO RXNORM LINKER (via NDC Bridge)")
    print("=" * 70)
    
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
    print("\n[3/6] Loading RxNorm entities...")
    rxcui_to_entity = {}
    rxnorm_path = f"{DATA_DIR}/rxnorm_entities.jsonl"
    with open(rxnorm_path, 'r') as f:
        for i, line in enumerate(f):
            if i % 100000 == 0 and i > 0:
                print(f"  Processed {i:,} entities...")
            e = json.loads(line)
            # Find RxCUI in values
            for val in e.get('values', []):
                prop = val.get('property')
                if prop == schema.prop('rxcui'):
                    rxcui = val.get('value')
                    if rxcui:
                        rxcui_to_entity[rxcui] = e['id']
                    break
    print(f"  Found {len(rxcui_to_entity):,} RxCUI -> entity mappings")
    
    # Step 4: Load PackageInserts and build fda_set_id -> entity_id mapping
    print("\n[4/6] Loading PackageInserts from merged entities...")
    set_id_prop = schema.prop('fda_set_id')
    package_insert_type = schema.type_id('PackageInsert')
    
    set_id_to_pi_id = {}
    merged_path = f"{DATA_DIR}/grc20_merged_entities.jsonl"
    
    with open(merged_path, 'r') as f:
        for i, line in enumerate(f):
            if i % 200000 == 0 and i > 0:
                print(f"  Processed {i:,} entities...")
            e = json.loads(line)
            
            # Check if it's a PackageInsert
            if package_insert_type not in e.get('types', []):
                continue
            
            # Find fda_set_id value
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
        'ndc_not_found_in_bridge': 0,
        'rxcui_not_found_in_rxnorm': 0,
    }
    
    seen_links = set()  # (pi_id, rxnorm_id) to avoid duplicates
    pis_linked = set()  # Track unique PIs that got linked
    
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
                # Try original format
                rxcui = ndc_to_rxcui.get(ndc)
            
            if not rxcui:
                stats['ndc_not_found_in_bridge'] += 1
                continue
            
            # Handle case where rxcui is a list
            if isinstance(rxcui, list):
                rxcuis = rxcui
            else:
                rxcuis = [rxcui]
            
            for rxcui_single in rxcuis:
                # Find RxNorm entity
                rxnorm_id = rxcui_to_entity.get(str(rxcui_single))
                if not rxnorm_id:
                    stats['rxcui_not_found_in_rxnorm'] += 1
                    continue
                
                # Avoid duplicate links
                link_key = (pi_id, rxnorm_id)
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)
                
                # Create relation
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
    
    # Step 6: Write output
    print("\n[6/6] Writing output files...")
    
    # Relations
    rel_path = f"{DATA_DIR}/dailymed_rxnorm_links_relations.jsonl"
    with open(rel_path, 'w') as f:
        for rel in relations_out:
            f.write(json.dumps(rel) + '\n')
    print(f"  ✅ Wrote {len(relations_out):,} relations to {rel_path}")
    
    # Summary
    summary = {
        'exported_at': datetime.now().isoformat(),
        'schema_version': '4.0.0',
        'source': 'grc20_merged_entities.jsonl + dailymed_documents.json + ndc_to_rxcui.json + rxnorm_entities.jsonl',
        'stats': stats
    }
    
    summary_path = f"{DATA_DIR}/dailymed_rxnorm_links_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✅ Wrote summary to {summary_path}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"PackageInserts with Set IDs: {stats['total_pis']:,}")
    print(f"PackageInserts with NDCs in docs: {stats['pis_with_ndcs']:,}")
    print(f"PackageInserts linked to RxNorm: {stats['pis_linked']:,}")
    print(f"Total NDCs processed: {stats['total_ndcs_processed']:,}")
    print(f"Total PackageInsert -> RxNorm relations: {stats['total_relations']:,}")
    print(f"NDC not found in bridge: {stats['ndc_not_found_in_bridge']:,}")
    print(f"RxCUI not found in RxNorm: {stats['rxcui_not_found_in_rxnorm']:,}")
    print("=" * 70)
    
    return summary


if __name__ == "__main__":
    main()
