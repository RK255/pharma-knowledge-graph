#!/usr/bin/env python3
"""
Analyze which RxCUI TTY levels have Set IDs

We need to understand at which RxNorm concept level (TTY) the SPL Set IDs 
are attached so we can properly link NDCs to Set IDs.

NDCs in RxNorm are typically at these TTY levels:
- BPCK (Brand Pack)
- GPCK (Generic Pack)
- SBD (Semantic Branded Drug)
- SCD (Semantic Clinical Drug)
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"
EXTRACTED_DIR = RAW_DATA_DIR / "extracted_rrf"

def analyze_setid_tty_levels():
    """Analyze which TTY levels have Set IDs"""
    print("=" * 80)
    print("ANALYZING WHICH RxCUI TTY LEVELS HAVE SET IDs")
    print("=" * 80)
    
    # Load the RxCUI to Set ID mapping
    mapping_file = RAW_DATA_DIR / "rxnorm_rxcui_to_setid.json"
    
    if not mapping_file.exists():
        print(f"❌ Mapping file not found: {mapping_file}")
        return
    
    with open(mapping_file, 'r') as f:
        rxcui_to_setids = json.load(f)
    
    print(f"\nLoaded {len(rxcui_to_setids):,} RxCUIs with Set IDs")
    
    # Now we need to find the TTY for each RxCui
    # We'll need to parse RXNCONSO.RRF to get RxCUI → TTY mapping
    
    # Find the most recent RXNCONSO.RRF file
    conso_file = None
    conso_files = [
        EXTRACTED_DIR / "RxNorm03022026_extracted/rrf/RXNCONSO.RRF",
        EXTRACTED_DIR / "RxNorm02022026_extracted/rrf/RXNCONSO.RRF",
        EXTRACTED_DIR / "RxNorm01052026_extracted/rrf/RXNCONSO.RRF",
    ]
    
    for file in conso_files:
        if file.exists():
            conso_file = file
            print(f"\nUsing RXNCONSO.RRF: {file}")
            break
    
    if not conso_file:
        print("❌ RXNCONSO.RRF file not found")
        return
    
    # Parse RXNCONSO.RRF to get RxCUI → TTY mapping
    print("Parsing RXNCONSO.RRF to get RxCUI → TTY mapping...")
    
    rxcui_to_tty = {}
    total_lines = 0
    
    with open(conso_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            total_lines += 1
            
            fields = line.strip().split('|')
            if len(fields) < 19:
                continue
            
            rxcui = fields[0]  # RxCUI
            tty = fields[12]   # TTY (Term Type)
            
            # Only keep RXNORM source entries
            if fields[11] != 'RXNORM':
                continue
            
            # Store the TTY for this RxCUI
            rxcui_to_tty[rxcui] = tty
            
            if total_lines % 1000000 == 0:
                print(f"  Processed {total_lines:,} lines...")
    
    print(f"✅ Loaded {len(rxcui_to_tty):,} RxCUI → TTY mappings")
    
    # Now analyze which TTYs have Set IDs
    tty_setid_counts = defaultdict(int)
    tty_rxcui_counts = defaultdict(int)
    tty_with_setids = set()
    
    for rxcui, setids in rxcui_to_setids.items():
        tty = rxcui_to_tty.get(rxcui, "UNKNOWN")
        tty_setid_counts[tty] += len(setids)
        tty_rxcui_counts[tty] += 1
        tty_with_setids.add(tty)
    
    print(f"\nTTYs with Set IDs:")
    for tty in sorted(tty_with_setids):
        rxcui_count = tty_rxcui_counts[tty]
        setid_count = tty_setid_counts[tty]
        avg_setids = setid_count / rxcui_count if rxcui_count > 0 else 0
        print(f"  {tty}: {rxcui_count:,} RxCUIs, {setid_count:,} Set ID entries (avg {avg_setids:.2f} per RxCUI)")
    
    # Load NDC data to see what TTYs NDCs are at
    ndc_file = RAW_DATA_DIR / "ndc_to_rxcui.json"
    if ndc_file.exists():
        print(f"\nLoading NDC data from {ndc_file}...")
        with open(ndc_file, 'r') as f:
            ndc_data = json.load(f)
        
        ndc_tty_counts = defaultdict(int)
        for ndc, rxcui in ndc_data["ndc_to_rxcui"].items():
            tty = rxcui_to_tty.get(str(rxcui), "UNKNOWN")
            ndc_tty_counts[tty] += 1
        
        print(f"NDCs by TTY level:")
        for tty in sorted(ndc_tty_counts.keys()):
            print(f"  {tty}: {ndc_tty_counts[tty]:,} NDCs")
    
    print(f"\n✅ Analysis complete!")

if __name__ == "__main__":
    analyze_setid_tty_levels()
