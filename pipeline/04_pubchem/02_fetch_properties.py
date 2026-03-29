#!/usr/bin/env python3
"""
PubChem Property Fetcher v7 - Streamlined
Automatically fetches and adds a fixed set of properties to entities.

Usage:
    python 02_fetch_properties.py
"""

import os
import json
import pickle
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

# Add schema path
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from pharma_schema import PharmaSchema

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

# The fixed list of properties we will fetch
PROPERTIES_TO_FETCH = [
    'smiles',      # Canonical SMILES
    'inchikey',    # InChIKey
    'iupac_name',  # IUPAC Name
]

def load_cid_to_in_mapping(output_dir: str) -> Dict[str, str]:
    """Loads the RxCUI -> CID mapping from the previous step."""
    mapping_file = os.path.join(output_dir, "pubchem_cid_mapping.json")
    if not os.path.exists(mapping_file):
        print(f"ERROR: {mapping_file} not found.")
        print("Run 01_enrich_by_cid.py first.")
        return {}

    print(f"Loading RxCUI -> CID mapping from {os.path.basename(mapping_file)}...")
    with open(mapping_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # data['cid_mapping'] is a dict of {rxcui: {'cid': ..., 'entity_id': ..., ...}}
    rxcui_to_cid = {rxcui: info['cid'] for rxcui, info in data.get('cid_mapping', {}).items()}
    print(f"  Loaded {len(rxcui_to_cid):,} RxCUI -> CID mappings.")
    return rxcui_to_cid

def load_entities(input_file: str) -> List[dict]:
    """Loads entities from a JSONL file."""
    print(f"Loading entities from {os.path.basename(input_file)}...")
    entities = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entities.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  WARNING: Could not parse line: {line[:50]}...")
                    continue
    print(f"  Loaded {len(entities):,} entities.")
    return entities

def load_property_pickles(pubchem_dir: str, properties_to_fetch: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Loads property pickle files into a nested dictionary.
    Returns a dict: {property_name: {cid: value}}
    """
    property_data = {}
    print("\nLoading property pickle files...")

    for prop_name in properties_to_fetch:
        # Try to find the pickle file, handling common name variations
        possible_filenames = [f"CID-{prop_name}.pkl", f"cid_{prop_name}.pkl", f"{prop_name}.pkl"]
        prop_file = None
        for filename in possible_filenames:
            filepath = os.path.join(pubchem_dir, filename)
            if os.path.exists(filepath):
                prop_file = filepath
                break
        
        if not prop_file:
            print(f"  WARNING: Could not find pickle file for '{prop_name}'. Tried: {possible_filenames}")
            continue

        print(f"  Loading {prop_name} from {os.path.basename(prop_file)}...")
        try:
            with open(prop_file, 'rb') as f:
                data = pickle.load(f)
            # Ensure keys are strings for consistent lookup
            property_data[prop_name] = {str(k): str(v) for k, v in data.items()}
            print(f"    Loaded {len(property_data[prop_name]):,} CID mappings.")
        except Exception as e:
            print(f"  ERROR: Could not load {prop_file}: {e}")
            import traceback
            traceback.print_exc()

    return property_data

def update_entities_with_properties(
    entities: List[dict],
    schema: PharmaSchema,
    rxcui_to_cid: Dict[str, str],
    property_data: Dict[str, Dict[str, str]]
) -> List[dict]:
    """Updates entities in-place with PubChem properties."""
    print("\nUpdating entities with PubChem properties...")
    
    # Get property IDs from the schema
    prop_ids = {name: schema.prop(name)['id'] for name in PROPERTIES_TO_FETCH}

    stats = {
        'total_entities': len(entities),
        'entities_with_cid': 0,
        'properties_added': 0,
        'entities_updated': 0,
    }

    for entity in entities:
        entity_id = entity.get('id')
        entity_rxcui = None
        updated = False

        # Find the RxCUI for this entity
        for value in entity.get('values', []):
            if value.get('property') == schema.prop('rxcui')['id']:
                entity_rxcui = value.get('value')
                break
        
        if not entity_rxcui:
            continue

        stats['entities_with_cid'] += 1

        # Get the PubChem CID for this RxCUI
        cid = rxcui_to_cid.get(entity_rxcui)
        if not cid:
            continue

        # Add each requested property
        for prop_name, prop_id in prop_ids.items():
            if prop_name in property_data:
                prop_value = property_data[prop_name].get(cid)
                if prop_value:
                    # Add the value to the entity
                    # We assume LWW (Last-Writer-Wins), so we just append/update
                    # For simplicity, we just add it to the values list
                    entity['values'].append({
                        "property": prop_id,
                        "value": prop_value
                    })
                    stats['properties_added'] += 1
                    updated = True

        if updated:
            stats['entities_updated'] += 1

    print(f"  Finished updating entities.")
    print(f"    Entities with RxCUI: {stats['entities_with_cid']:,}")
    print(f"    Entities matched to PubChem CID: {stats['entities_updated']:,}")
    print(f"    Total properties added: {stats['properties_added']:,}")
    return entities

def save_entities(output_file: str, entities: List[dict]) -> None:
    """Saves entities to a JSONL file."""
    print(f"\nSaving updated entities to {os.path.basename(output_file)}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        for entity in entities:
            f.write(json.dumps(entity) + '\n')
    file_size = os.path.getsize(output_file) / 1024 / 1024
    print(f"  Saved {len(entities):,} entities ({file_size:.2f} MB).")

def main():
    print("=" * 70)
    print("PUBCHEM PROPERTY FETCHER v7 (STREAMLINED)")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Automatically fetching properties: {', '.join(PROPERTIES_TO_FETCH)}")

    # 1. Load the RxCUI -> CID mapping
    rxcui_to_cid = load_cid_to_in_mapping(OUTPUT_DIR)
    if not rxcui_to_cid:
        print("ERROR: No RxCUI -> CID mapping found. Exiting.")
        return

    # 2. Load the entities from the previous step
    # We'll use the rxnorm_entities.jsonl from the main output dir
    # as that's what 01_enrich_by_cid.py used as its base.
    input_entities_file = os.path.join(OUTPUT_DIR, "rxnorm_entities.jsonl")
    if not os.path.exists(input_entities_file):
        print(f"ERROR: {input_entities_file} not found.")
        return

    entities = load_entities(input_entities_file)

    # 3. Load property data from pickle files
    property_data = load_property_pickles(PUBCHEM_DIR, PROPERTIES_TO_FETCH)
    if not property_data:
        print("ERROR: No property data loaded. Exiting.")
        return

    # 4. Update entities
    schema = PharmaSchema()
    updated_entities = update_entities_with_properties(entities, schema, rxcui_to_cid, property_data)

    # 5. Save the updated entities
    # We'll save to a new file to avoid overwriting the original
    output_file = os.path.join(OUTPUT_DIR, "rxnorm_entities_enriched.jsonl")
    save_entities(output_file, updated_entities)

    print("\n" + "=" * 70)
    print("PROPERTY FETCHING COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    # No arguments needed anymore
    main()
