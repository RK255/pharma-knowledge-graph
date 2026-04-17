"""
03_link_dailymed_to_rxnorm_by_setid.py

Links DailyMed PackageInserts to RxNorm entities using SPL Set IDs.
This replaces the fragile NDC-NDC matching approach with Set ID-based linking.

Primary method: Set ID matching
Output: GRC-20 relations (PackageInsert -> RxNorm)
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict

# Add schema path
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/pipeline/00_schema')
from pharma_schema import PharmaSchema

# Initialize schema
schema = PharmaSchema()

# GRC-20 IDs
PACKAGEINSERT_TYPE = "0af427a2b7df5f6dbdb4fb86a54359fd"
FDA_SET_ID_PROPERTY = "78d0af3db973513e8be0cb76afa5e9c4"
NDC_CODE_PROPERTY = "694ec99a6c8e555caba8d8bb72f302c8"

# Get relation type ID
MAPS_TO_RXCUI_REL = schema.rel("maps_to_rxcui")

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/grc20_v2"


def generate_uuid(seed_string: str) -> str:
    """Generate deterministic UUID from seed string."""
    import hashlib
    return hashlib.md5(seed_string.encode()).hexdigest()


def load_set_id_mappings():
    """Load NDC → Set ID mappings from RxNorm"""
    setid_file = f'{BASE_DIR}/data/raw_data/ndc_to_setid_final_v3.json'
    
    if not os.path.exists(setid_file):
        print(f"Warning: Set ID mapping file not found: {setid_file}")
        return {}, {}
    
    with open(setid_file, 'r') as f:
        data = json.load(f)
    
    ndc_to_setid = data.get('ndc_to_setid', {})
    print(f"Loaded {len(ndc_to_setid):,} NDC → Set ID mappings")
    
    return ndc_to_setid, data


def load_ndc_to_rxcui_mappings():
    """Load NDC → RxCUI mappings from bridge"""
    bridge_file = f'{BASE_DIR}/data/raw_data/ndc_to_rxcui.json'
    
    if not os.path.exists(bridge_file):
        print(f"Warning: NDC bridge file not found: {bridge_file}")
        return {}
    
    with open(bridge_file, 'r') as f:
        data = json.load(f)
    
    # Handle both formats
    if 'ndc_to_rxcui' in data:
        ndc_to_rxcui = data['ndc_to_rxcui']
    else:
        ndc_to_rxcui = data
    
    print(f"Loaded {len(ndc_to_rxcui):,} NDC → RxCUI mappings")
    
    return ndc_to_rxcui


def load_dailymed_package_inserts():
    """Load DailyMed PackageInsert entities from GRC-20 JSONL"""
    dailymed_file = f'{DATA_DIR}/dailymed_entities.jsonl'
    
    if not os.path.exists(dailymed_file):
        print(f"Error: DailyMed entities file not found: {dailymed_file}")
        return []
    
    package_inserts = []
    
    print("Loading DailyMed entities...")
    with open(dailymed_file, 'r') as f:
        line_count = 0
        for line in f:
            try:
                entity = json.loads(line)
                
                # Check if this is a PackageInsert
                if 'types' in entity and PACKAGEINSERT_TYPE in entity['types']:
                    package_inserts.append(entity)
                
                line_count += 1
                if line_count % 100000 == 0:
                    print(f"  Processed {line_count:,} lines, found {len(package_inserts):,} PackageInserts...", end='\r')
            except json.JSONDecodeError:
                continue
    
    print(f"\nLoaded {len(package_inserts):,} PackageInserts from {line_count:,} entities")
    
    return package_inserts


def load_rxcui_to_entity_mapping():
    """Load RxNorm entities to build RxCUI -> entity ID mapping"""
    rxnorm_file = f'{DATA_DIR}/grc20_merged_entities.jsonl'
    
    if not os.path.exists(rxnorm_file):
        # Try alternative location
        rxnorm_file = f'{DATA_DIR}/rxnorm_entities.jsonl'
    
    if not os.path.exists(rxnorm_file):
        print(f"Warning: RxNorm entities file not found")
        return {}
    
    rxcui_to_entity = {}
    
    print("Loading RxNorm entities for RxCUI mapping...")
    rxcui_prop_id = schema.prop("rxcui")
    
    with open(rxnorm_file, 'r') as f:
        line_count = 0
        for line in f:
            try:
                entity = json.loads(line)
                
                # Find RxCUI in values
                for val in entity.get('values', []):
                    if val.get('property') == rxcui_prop_id:
                        rxcui = val.get('value')
                        if rxcui:
                            rxcui_to_entity[str(rxcui)] = entity['id']
                        break
                
                line_count += 1
                if line_count % 100000 == 0:
                    print(f"  Processed {line_count:,} entities, found {len(rxcui_to_entity):,} RxCUIs...", end='\r')
            except json.JSONDecodeError:
                continue
    
    print(f"\nLoaded {len(rxcui_to_entity):,} RxCUI -> entity mappings from {line_count:,} entities")
    
    return rxcui_to_entity


def extract_set_id_from_package_insert(package_insert):
    """Extract Set ID from a PackageInsert entity (GRC-20 format)."""
    if 'values' not in package_insert:
        return None
    
    for value_obj in package_insert['values']:
        if value_obj.get('property') == FDA_SET_ID_PROPERTY:
            set_id = value_obj.get('value')
            if set_id:
                return set_id
    
    return None


def link_package_insert_to_rxnorm(package_insert, ndc_to_setid, ndc_to_rxcui, rxcui_to_entity):
    """
    Link a PackageInsert to RxNorm entities using Set ID.
    
    Returns: list of relation dicts
    """
    pi_id = package_insert.get('id', 'unknown')
    relations = []
    
    # Set ID linking
    set_id = extract_set_id_from_package_insert(package_insert)
    
    if set_id:
        # Find all RxCUIs that have NDCs with this Set ID
        rxcuis = set()
        
        for ndc, sid in ndc_to_setid.items():
            if sid == set_id:
                if ndc in ndc_to_rxcui:
                    rxcui_val = ndc_to_rxcui[ndc]
                    # Handle list or single value
                    if isinstance(rxcui_val, list):
                        rxcuis.update([str(r) for r in rxcui_val])
                    else:
                        rxcuis.add(str(rxcui_val))
        
        # Create relations for each RxCUI that exists in our entities
        for rxcui in rxcuis:
            if rxcui in rxcui_to_entity:
                rxnorm_id = rxcui_to_entity[rxcui]
                
                # Create relation
                rel_id = generate_uuid(f"pi_rxnorm_link:{pi_id}:{rxnorm_id}")
                relation = {
                    'id': rel_id,
                    'type': MAPS_TO_RXCUI_REL,
                    'from': pi_id,
                    'to': rxnorm_id,
                    'values': []
                }
                relations.append(relation)
    
    return relations


def main():
    print("=" * 80)
    print("LINKING DAILYMED PACKAGE INSERTS TO RXNORM VIA SET IDs")
    print("=" * 80 + "\n")
    
    # Load mappings
    ndc_to_setid, setid_data = load_set_id_mappings()
    ndc_to_rxcui = load_ndc_to_rxcui_mappings()
    rxcui_to_entity = load_rxcui_to_entity_mapping()
    
    # Load PackageInserts
    package_inserts = load_dailymed_package_inserts()
    
    if not package_inserts:
        print("\nError: No PackageInserts loaded. Please check the file path.")
        return
    
    # Create relations
    print("\nCreating PackageInsert -> RxNorm relations...")
    relations_out = []
    linked_pis = set()
    
    for i, pi in enumerate(package_inserts):
        relations = link_package_insert_to_rxnorm(pi, ndc_to_setid, ndc_to_rxcui, rxcui_to_entity)
        relations_out.extend(relations)
        
        if relations:
            linked_pis.add(pi['id'])
        
        if (i + 1) % 1000 == 0:
            print(f"  Processed {i+1:,}/{len(package_inserts):,} PackageInserts, created {len(relations_out):,} relations...", end='\r')
    
    print(f"\n  Processed {len(package_inserts):,} PackageInserts")
    print(f"  Created {len(relations_out):,} relations")
    print(f"  Linked {len(linked_pis):,} PackageInserts")
    
    # Remove duplicates (shouldn't be any with deterministic IDs, but just in case)
    unique_relations = {rel['id']: rel for rel in relations_out}
    relations_out = list(unique_relations.values())
    print(f"  After deduplication: {len(relations_out):,} relations")
    
    # Write relations
    print("\n" + "=" * 80)
    print("WRITING OUTPUT")
    print("=" * 80 + "\n")
    
    rel_path = f'{DATA_DIR}/dailymed_rxnorm_links_relations.jsonl'
    with open(rel_path, 'w') as f:
        for rel in relations_out:
            f.write(json.dumps(rel) + '\n')
    
    print(f"✅ Wrote {len(relations_out):,} relations to {rel_path}")
    
    # Write summary
    summary = {
        'exported_at': datetime.now().isoformat(),
        'schema_version': '4.2.0',
        'source': 'dailymed_entities.jsonl + ndc_to_setid_final_v3.json + ndc_to_rxcui.json',
        'linking_method': 'set_id',
        'stats': {
            'total_package_inserts': len(package_inserts),
            'linked_package_inserts': len(linked_pis),
            'unlinked_package_inserts': len(package_inserts) - len(linked_pis),
            'total_relations': len(relations_out),
            'coverage_percent': len(linked_pis) / len(package_inserts) * 100 if package_inserts else 0,
            'ndc_to_setid_count': len(ndc_to_setid),
            'ndc_to_rxcui_count': len(ndc_to_rxcui),
            'rxcui_entities_count': len(rxcui_to_entity)
        }
    }
    
    summary_path = f'{DATA_DIR}/dailymed_rxnorm_links_summary.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"✅ Wrote summary to {summary_path}")
    
    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"""
Summary:
  - Total PackageInserts: {summary['stats']['total_package_inserts']:,}
  - Linked PackageInserts: {summary['stats']['linked_package_inserts']:,}
  - Unlinked PackageInserts: {summary['stats']['unlinked_package_inserts']:,}
  - Total relations: {summary['stats']['total_relations']:,}
  - Coverage: {summary['stats']['coverage_percent']:.1f}%

Output files:
  - Relations: {rel_path}
  - Summary: {summary_path}
""")

if __name__ == '__main__':
    main()
