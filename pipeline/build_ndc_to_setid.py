#!/usr/bin/env python3
"""
Build NDC → Set ID mapping from RxNorm data
===========================================
Combines NDC → RxCUI mapping with RxCUI → Set ID mapping.

Input:
  - data/raw_data/ndc_to_rxcui.json (NDC → RxCUI)
  - data/raw_data/rxcui_to_setid.json (RxCUI → Set IDs)

Output:
  - data/raw_data/ndc_to_setid.json (NDC → Set ID)
"""

import json
from pathlib import Path

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

def load_ndc_to_rxcui():
    """Load NDC → RxCUI mapping."""
    with open(RAW_DATA_DIR / "ndc_to_rxcui.json", 'r') as f:
        data = json.load(f)
    
    return data.get('ndc_to_rxcui', {})

def load_rxcui_to_setid():
    """Load RxCUI → Set ID mapping."""
    with open(RAW_DATA_DIR / "rxcui_to_setid.json", 'r') as f:
        data = json.load(f)
    
    return data.get('rxcui_to_setids', {})

def main():
    print("=" * 80)
    print("BUILDING NDC → SET ID MAPPING")
    print("=" * 80)
    
    # Load mappings
    print("\nLoading NDC → RxCUI mapping...")
    ndc_to_rxcui = load_ndc_to_rxcui()
    print(f"  Loaded {len(ndc_to_rxcui):,} NDC → RxCUI mappings")
    
    print("\nLoading RxCUI → Set ID mapping...")
    rxcui_to_setid = load_rxcui_to_setid()
    print(f"  Loaded {len(rxcui_to_setid):,} RxCUI → Set ID mappings")
    
    # Build NDC → Set ID mapping
    print("\nBuilding NDC → Set ID mapping...")
    ndc_to_setid = {}
    
    for ndc, rxcui in ndc_to_rxcui.items():
        setids = rxcui_to_setid.get(rxcui, [])
        if setids:
            # Use the first Set ID (most NDCs have only one)
            ndc_to_setid[ndc] = setids[0]
    
    print(f"  Built {len(ndc_to_setid):,} NDC → Set ID mappings")
    
    # Save
    output_file = RAW_DATA_DIR / "ndc_to_setid.json"
    with open(output_file, 'w') as f:
        json.dump({'ndc_to_setid': ndc_to_setid}, f, indent=2)
    
    print(f"\nSaved to {output_file}")
    print("=" * 80)

if __name__ == '__main__':
    main()
