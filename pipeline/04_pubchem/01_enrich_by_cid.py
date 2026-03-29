#!/usr/bin/env python3
"""
PubChem CID Mapping Generator v5.3 (Auto-Cache Check)
Checks for existing 'pubchem_cid_mapping.json' before running API lookups.
If cache exists, it loads and exits immediately.
"""

import os
import sys
import json
import time
import requests

# Add schema path
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "pubchem_cid_mapping.json")

def resolve_rxnorm_to_cid_via_batch():
    """
    Collects all Ingredients (TTY=IN), groups them into batches,
    and queries PubChem PUG REST in bulk.
    """
    
    input_file = os.path.join(OUTPUT_DIR, "rxnorm_entities.jsonl")
    if not os.path.exists(input_file):
        print(f"ERROR: {input_file} not found.")
        return {}

    print(f"Scanning {input_file} for Ingredients...")
    
    # 1. Collect all Ingredients
    ingredients = []
    skipped_count = 0
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            
            try:
                entity = json.loads(line)
                name = entity.get('name')
                
                # HEURISTIC: Find TTY and RxCUI
                entity_tty = None
                rxcui = None
                
                for val in entity.get('values', []):
                    val_content = str(val.get('value', ''))
                    
                    if val_content in ['IN', 'PIN', 'MIN']:
                        entity_tty = val_content
                    
                    if val_content.isdigit() and 3 <= len(val_content) <= 8:
                        if not rxcui:
                            rxcui = val_content
                
                if entity_tty == 'IN' and name and rxcui:
                    ingredients.append({
                        "rxcui": rxcui,
                        "name": name
                    })
                else:
                    skipped_count += 1
                    
            except Exception as e:
                continue

    print(f"\n{'='*70}")
    print(f"SCAN COMPLETE")
    print(f"{'='*70}")
    print(f"Total Entities Scanned: {len(ingredients) + skipped_count}")
    print(f"Ingredients Found (TTY=IN): {len(ingredients)}")
    print(f"Non-Ingredients Skipped:   {skipped_count}")
    print(f"{'='*70}\n")
    
    if len(ingredients) == 0:
        print("ERROR: No Ingredients found.")
        return {}

    # 2. Batch Processing with Incremental Save
    print(f"Starting resolution in FAST SEQUENTIAL mode (Incremental Save)...")
    
    rxcui_to_cid = {}
    
    for i, item in enumerate(ingredients):
        name = item['name']
        rxcui = item['rxcui']
        
        try:
            safe_name = requests.utils.quote(name)
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{safe_name}/cids/JSON"
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                cid_list = data.get('IdentifierList', {}).get('CID', [])
                if cid_list:
                    rxcui_to_cid[str(rxcui)] = {
                        "name": name,
                        "cid": str(cid_list[0])
                    }
            
            # INCREMENTAL SAVE every 100 items
            if (i + 1) % 100 == 0:
                temp_output = {
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "in_progress",
                    "resolved_count": len(rxcui_to_cid),
                    "total_count": len(ingredients),
                    "cid_mapping": rxcui_to_cid
                }
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(temp_output, f, indent=4)
                print(f"  Resolved {len(rxcui_to_cid)} ingredients... (Saved)")
            
        except Exception as e:
            continue

    return rxcui_to_cid

def main():
    print("="*70)
    print("RXNORM -> CID MAPPING (AUTO-CACHE CHECK)")
    print("="*70)
    
    # --- CACHE CHECK START ---
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f:
                data = json.load(f)
            
            # Verify it's not empty and looks like valid data
            if data.get("cid_mapping") and len(data["cid_mapping"]) > 0:
                print(f"\n✅ FOUND CACHE FILE: {OUTPUT_FILE}")
                print(f"   Contains {len(data['cid_mapping']):,} mappings.")
                print(f"   Generated at: {data.get('generated_at', 'Unknown')}")
                print(f"\n🚀 SKIPPING API LOOKUP. USING CACHE.\n")
                return # Exit immediately
            else:
                print(f"⚠️  Cache file exists but is empty or invalid. Regenerating...")
        except Exception as e:
            print(f"⚠️  Error reading cache file: {e}. Regenerating...")
    # --- CACHE CHECK END ---

    # 1. Resolve using Names -> PubChem CID
    mapping_data = resolve_rxnorm_to_cid_via_batch()
    
    if not mapping_data:
        print("ERROR: No mappings generated.")
        return

    # 2. Final Save
    print(f"\nFinalizing output...")
    output_structure = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "RxNorm Ingredients -> PubChem PUG REST (Fast Sequential)",
        "total_mappings": len(mapping_data),
        "cid_mapping": mapping_data
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_structure, f, indent=4)
        
    print(f"Saved final mapping to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
