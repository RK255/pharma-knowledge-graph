#!/usr/bin/env python3
"""
PubChem Property Fetcher v21 (Includes CID in Output)
Optimized for large datasets with low memory footprint.
Aggressively downloads GZIP files from PubChem FTP if data is missing.
Includes misses reporting for debugging.
"""

import os
import json
import pickle
import gzip
import sys
import argparse
import ftplib
from datetime import datetime
from typing import Dict, List, Set, Any, Tuple
from pathlib import Path

# Add schema path
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from pharma_schema import PharmaSchema
import config
BASE_DIR = str(config.BASE_DIR)
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

# FTP Configuration
PUBCHEM_FTP = "ftp.ncbi.nlm.nih.gov"
PUBCHEM_PATH = "/pubchem/Compound/Extras"

# Property Definitions (CLI Name -> File Prefix)
# Note: pubchem_cid is NOT in this list - it comes from our mapping, not PubChem FTP
AVAILABLE_PROPERTIES = {
    'smiles': 'CID-SMILES',
    'inchikey': 'CID-InChI-Key',
    'iupac_name': 'CID-IUPAC',
    'molecular_weight': 'CID-Mass',
    'mesh': 'CID-MeSH',
    'date': 'CID-Date',
    'pmid': 'CID-PMID',
    'sid': 'CID-SID',
    'component': 'CID-Component',
    'cid': 'CID'
}

DEFAULT_PROPERTIES = ['smiles', 'inchikey', 'iupac_name']

def download_from_ftp(file_prefix: str, target_dir: str) -> bool:
    """Downloads a file from PubChem FTP."""
    filename = f"{file_prefix}.gz"
    local_path = os.path.join(target_dir, filename)
    
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
        return True  # File exists and has data
        
    print(f"  Downloading {filename} from {PUBCHEM_FTP}...")
    
    try:
        # Delete existing empty/corrupt file
        if os.path.exists(local_path):
            os.remove(local_path)
            
        with ftplib.FTP(PUBCHEM_FTP) as ftp:
            ftp.login()  # Anonymous login
            ftp.cwd(PUBCHEM_PATH)
            
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f"RETR {filename}", f.write)
            
        print(f"  Downloaded {filename}")
        return True
    except Exception as e:
        print(f"  ERROR: Failed to download {filename}: {e}")
        # Clean up partial download
        if os.path.exists(local_path):
            os.remove(local_path)
        return False

def get_property_file_info(pubchem_dir: str, file_prefix: str) -> Tuple[str, bool, float]:
    """Determines the source file (Pickle or GZIP) for a property."""
    
    # 1. Check for Pickle
    pkl_filename = f"{file_prefix}.pkl"
    pkl_path = os.path.join(pubchem_dir, pkl_filename)
    
    if os.path.exists(pkl_path) and os.path.getsize(pkl_path) > 1000:
        return (pkl_path, True, os.path.getsize(pkl_path) / (1024*1024))

    # 2. Check for GZIP (Local)
    gz_filename = f"{file_prefix}.gz"
    gz_path = os.path.join(pubchem_dir, gz_filename)
    
    if os.path.exists(gz_path) and os.path.getsize(gz_path) > 1000:
        return (gz_path, False, os.path.getsize(gz_path) / (1024*1024))

    # 3. Not found locally
    return (None, False, 0)

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

    rxcui_to_cid = {rxcui: info['cid'] for rxcui, info in data.get('cid_mapping', {}).items()}
    print(f"  Loaded {len(rxcui_to_cid):,} RxCUI -> CID mappings.")
    return rxcui_to_cid

def load_property_data(pubchem_dir: str, prop_name: str) -> Dict[str, str]:
    """Loads property data from Pickle or GZIP."""
    print(f"\nProcessing property: {prop_name}...")
    
    file_prefix = AVAILABLE_PROPERTIES.get(prop_name)
    if not file_prefix:
        print(f"  ERROR: No file mapping defined for '{prop_name}'")
        return {}
    
    source_path, is_pickle, size_mb = get_property_file_info(pubchem_dir, file_prefix)
    
    # If neither exists (or they are empty), download aggressively
    if not source_path:
        print(f"  Local file not found or empty. Attempting FTP download...")
        if download_from_ftp(file_prefix, pubchem_dir):
            # Try checking again
            source_path, is_pickle, size_mb = get_property_file_info(pubchem_dir, file_prefix)
            if not source_path:
                print(f"  ERROR: Download succeeded but file not found.")
                return {}
        else:
            print(f"  ERROR: Could not download source for {prop_name}")
            return {}
    
    if is_pickle:
        print(f"  Loading from cached Pickle: {os.path.basename(source_path)} ({size_mb:.1f} MB)")
        try:
            with open(source_path, 'rb') as f:
                data = pickle.load(f)
            return {str(k): str(v) for k, v in data.items()}
        except Exception as e:
            print(f"  ERROR loading pickle: {e}")
            return {}
    
    # Load from GZIP
    print(f"  Streaming GZIP: {os.path.basename(source_path)} ({size_mb:.1f} MB)")
    data = {}
    try:
        with gzip.open(source_path, 'rt', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line: continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    cid = parts[0]
                    value = "\t".join(parts[1:])
                    data[str(cid)] = value
                
                if (i + 1) % 1000000 == 0:
                    print(f"    Processed {i+1:,} lines...")
    except Exception as e:
        print(f"  ERROR reading GZIP: {e}")
        return {}
        
    print(f"  Loaded {len(data):,} mappings.")
    
    # Cache it
    pkl_path = os.path.join(pubchem_dir, f"{file_prefix}.pkl")
    print(f"  Caching to {os.path.basename(pkl_path)}...")
    try:
        with open(pkl_path, 'wb') as f:
            pickle.dump(data, f)
    except Exception as e:
        print(f"  Warning: Could not save cache: {e}")
        
    return data

def load_properties(pubchem_dir: str, properties_to_fetch: List[str]) -> Dict[str, Dict[str, str]]:
    """Loads all requested properties."""
    property_data = {}
    print("=" * 70)
    print("LOADING PROPERTY DATA")
    print("=" * 70)
    
    for prop_name in properties_to_fetch:
        if prop_name not in AVAILABLE_PROPERTIES:
            print(f"  WARNING: '{prop_name}' is not recognized. Skipping.")
            continue
            
        data = load_property_data(pubchem_dir, prop_name)
        if data:
            property_data[prop_name] = data
        else:
            print(f"  FAILED to load {prop_name}")
            
    return property_data

def resolve_schema_ids(schema: PharmaSchema, prop_names: List[str]) -> Dict[str, str]:
    """
    Resolves the Base58 ID for each requested property name.
    This is needed to WRITE the new properties correctly to the file.
    """
    ids = {}
    print("\n" + "="*70)
    print("RESOLVING SCHEMA IDS FOR OUTPUT")
    print("="*70)
    
    prop_map = schema.properties
    
    if isinstance(prop_map, dict):
        print(f"Detected Schema Structure: Dict (name -> id)")
        for name in prop_names:
            # Case-insensitive lookup
            found_id = None
            for key, val in prop_map.items():
                if key.lower() == name.lower():
                    found_id = val
                    break
            
            if found_id:
                ids[name] = found_id
                print(f"  ✅ '{name}' -> {found_id}")
            else:
                print(f"  ❌ '{name}' -> NOT FOUND in schema")
    else:
        print(f"  ERROR: Unknown schema structure type: {type(prop_map)}")
        
    return ids

def update_entities_stream(
    input_file: str,
    output_file: str,
    rxcui_to_cid: Dict[str, str],
    property_data: Dict[str, Dict[str, str]],
    schema_ids: Dict[str, str],
    misses_file: str = None
) -> Dict[str, int]:
    """
    Streams entities, updates them with resolved Schema IDs, writes output.
    
    FIXED: Removed the 1000 < RxCUI filter that was excluding low-numbered drugs
    like acetaminophen (161) and amoxicillin (723).
    
    UPDATED: Now also writes pubchem_cid as a property.
    
    Returns stats dict.
    """
    print(f"\n{'='*70}")
    print("STREAMING ENTITY UPDATE")
    print(f"{'='*70}")
    
    # Get the CID property ID
    cid_prop_id = schema_ids.get('pubchem_cid')
    if cid_prop_id:
        print(f"  Will write CID to property: {cid_prop_id}")
    
    stats = {
        'total_entities': 0,
        'entities_with_rxcui': 0,
        'entities_matched_cid': 0,
        'entities_no_cid_match': 0,
        'properties_added': 0,
        'cids_written': 0,
    }
    
    misses = []  # Track RxCUIs that had no CID mapping or no properties
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        for line in f_in:
            line = line.strip()
            if not line: continue
            
            try:
                entity = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            stats['total_entities'] += 1
            entity_rxcui = None
            entity_name = entity.get('name', 'UNKNOWN')

            # FIXED: Check if value is numeric AND exists in our CID mapping
            # Previously had a bug: "1000 < int(val_content)" which filtered out
            # important drugs like acetaminophen (RxCUI 161) and amoxicillin (RxCUI 723)
            for value in entity.get('values', []):
                val_content = str(value.get('value', ''))
                if val_content.isdigit() and val_content in rxcui_to_cid:
                    entity_rxcui = val_content
                    break
            
            if not entity_rxcui:
                f_out.write(json.dumps(entity) + '\n')
                continue

            stats['entities_with_rxcui'] += 1

            cid = rxcui_to_cid.get(entity_rxcui)
            if not cid:
                # This shouldn't happen since we check above, but log it anyway
                misses.append({
                    'rxcui': entity_rxcui,
                    'name': entity_name,
                    'reason': 'no_cid_in_mapping'
                })
                stats['entities_no_cid_match'] += 1
                f_out.write(json.dumps(entity) + '\n')
                continue

            stats['entities_matched_cid'] += 1

            # Write CID as a property (NEW)
            if cid_prop_id:
                entity['values'].append({
                    "property": cid_prop_id,
                    "value": cid
                })
                stats['properties_added'] += 1
                stats['cids_written'] += 1

            # Add properties using resolved Schema IDs
            props_added_for_entity = 0
            for prop_name, prop_dict in property_data.items():
                prop_value = prop_dict.get(cid)
                if prop_value:
                    target_prop_id = schema_ids.get(prop_name)
                    
                    if target_prop_id:
                        entity['values'].append({
                            "property": target_prop_id,
                            "value": prop_value
                        })
                        stats['properties_added'] += 1
                        props_added_for_entity += 1
            
            # Track if we matched CID but found no properties in PubChem data
            if props_added_for_entity == 0:
                misses.append({
                    'rxcui': entity_rxcui,
                    'name': entity_name,
                    'cid': cid,
                    'reason': 'cid_found_but_no_properties'
                })

            f_out.write(json.dumps(entity) + '\n')

            if stats['total_entities'] % 10000 == 0:
                print(f"  Processed {stats['total_entities']:,} entities, {stats['properties_added']:,} props added...")

    print(f"\n{'='*70}")
    print(f"STREAMING COMPLETE")
    print(f"{'='*70}")
    print(f"Total Entities:           {stats['total_entities']:,}")
    print(f"Entities with RxCUI:      {stats['entities_with_rxcui']:,}")
    print(f"Matched to CID:           {stats['entities_matched_cid']:,}")
    print(f"No CID Match:             {stats['entities_no_cid_match']:,}")
    print(f"CIDs Written:             {stats['cids_written']:,}")
    print(f"Properties Added:         {stats['properties_added']:,}")
    print(f"{'='*70}")
    
    # Write misses report
    if misses_file:
        print(f"\nWriting misses report to {os.path.basename(misses_file)}...")
        
        # Summarize by reason
        reasons = {}
        for m in misses:
            r = m.get('reason', 'unknown')
            reasons[r] = reasons.get(r, 0) + 1
        
        report = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_misses': len(misses),
            'breakdown_by_reason': reasons,
            'misses': misses
        }
        
        with open(misses_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        print(f"  {len(misses)} total misses logged.")
        print(f"\n  Miss breakdown by reason:")
        for r, count in reasons.items():
            print(f"    {r}: {count}")
    
    return stats

def main():
    print("=" * 70)
    print("PUBCHEM PROPERTY FETCHER v21 (INCLUDES CID)")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    parser = argparse.ArgumentParser(description="Stream and enrich entities with PubChem properties.")
    parser.add_argument(
        '--properties', 
        nargs='+', 
        default=DEFAULT_PROPERTIES,
        help=f"Space-separated list of properties. Options: {', '.join(AVAILABLE_PROPERTIES.keys())}."
    )
    args = parser.parse_args()

    properties_to_fetch = [p for p in args.properties if p in AVAILABLE_PROPERTIES]
    
    print(f"Target Properties: {', '.join(properties_to_fetch)}")

    # 0. Initialize Schema and Resolve IDs (for OUTPUT only)
    schema = PharmaSchema()
    
    # Include pubchem_cid in schema resolution (it's not in AVAILABLE_PROPERTIES but we need the ID)
    props_to_resolve = properties_to_fetch + ['pubchem_cid']
    schema_ids = resolve_schema_ids(schema, props_to_resolve)
    
    if not schema_ids:
        print("ERROR: Could not find output property IDs in schema. Check your schema.")
        return

    # 1. Load CID mapping
    rxcui_to_cid = load_cid_to_in_mapping(OUTPUT_DIR)
    if not rxcui_to_cid:
        print("ERROR: No RxCUI -> CID mapping found. Exiting.")
        return

    # 2. Paths
    input_entities_file = os.path.join(OUTPUT_DIR, "rxnorm_entities.jsonl")
    output_entities_file = os.path.join(OUTPUT_DIR, "rxnorm_entities_enriched.jsonl")
    misses_file = os.path.join(OUTPUT_DIR, "pubchem_misses_report.json")
    
    if not os.path.exists(input_entities_file):
        print(f"ERROR: {input_entities_file} not found.")
        return

    # 3. Load properties
    property_data = load_properties(PUBCHEM_DIR, properties_to_fetch)
    if not property_data:
        print("ERROR: No property data loaded. Exiting.")
        return

    # 4. Stream update with misses reporting
    update_entities_stream(
        input_entities_file, 
        output_entities_file, 
        rxcui_to_cid, 
        property_data, 
        schema_ids,
        misses_file
    )

    print("\nSUCCESS: Enrichment complete.")

if __name__ == "__main__":
    main()
