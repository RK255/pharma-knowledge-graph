#!/usr/bin/env python3
"""
Generate RxCUI to Set ID Mapping from RXNSAT.RRF

Extracts SPL Set IDs from RxNorm's RXNSAT.RRF file and creates
a mapping of RxCUIs to their associated Set IDs.

Uses the same parsing logic as NDC_enricher_v1.py to ensure consistency.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

def parse_rxnsat_rrf(rxnsat_file: Path) -> dict:
    """
    Parse RXNSAT.RRF file to extract RxCUI to Set ID mappings.
    
    RXNSAT.RRF Format (pipe-delimited):
    Field 1: RxCUI (RxNorm Concept Unique Identifier)
    Field 2: Empty
    Field 3: Empty
    Field 4: RXAUI (Atom Unique Identifier)
    Field 5: STYPE (Source Type)
    Field 6: CODE (Source asserted identifier)
    Field 7: Empty
    Field 8: Empty
    Field 9: ATN (Attribute Name) - we want "SPL_SET_ID"
    Field 10: SAB (Source Abbreviation) - "MTHSPL"
    Field 11: ATV (Attribute Value) - contains the Set ID
    Field 12: SUPPRESS (Suppress flag)
    Field 13: CVF (Content View Flag)
    Field 14: Empty
    """
    print(f"Parsing RXNSAT.RRF from {rxnsat_file}...")
    
    rxcui_to_setids = defaultdict(list)
    total_lines = 0
    set_id_lines = 0
    
    # SPL sources that contain Set IDs
    spl_sources = {'MTHSPL'}
    
    with open(rxnsat_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            total_lines += 1
            
            # RXNSAT.RRF fields are pipe-delimited
            fields = line.strip().split('|')
            
            if len(fields) < 12:
                continue
            
            # Extract fields (0-indexed) - SAME AS NDC_enricher_v1.py
            rxcui = fields[0]   # Field 1 - RxCUI (Correct!)
            atn = fields[8]    # Field 9 - Attribute Name
            sab = fields[9]    # Field 10 - Source
            atv = fields[10]   # Field 11 - Attribute Value (Set ID)
            suppress = fields[11] if len(fields) > 11 else ""
            
            # We only want SPL_SET_ID attributes
            if atn != 'SPL_SET_ID':
                continue
            
            # Skip if suppress is "Y" (only keep active Set IDs)
            if suppress == "Y":
                continue
            
            # Only process from known SPL sources
            if sab not in spl_sources:
                continue
            
            if atv:
                rxcui_to_setids[rxcui].append(atv)
                set_id_lines += 1
            
            # Show progress every 100k lines
            if total_lines % 100000 == 0:
                print(f"  Processed {total_lines:,} lines, found {set_id_lines:,} Set IDs")
    
    print(f"  Total lines processed: {total_lines:,}")
    print(f"  Set ID lines found: {set_id_lines:,}")
    print(f"  Unique RxCUIs with Set IDs: {len(rxcui_to_setids):,}")
    
    return dict(rxcui_to_setids)

def main():
    print("=" * 80)
    print("GENERATING RXCUI TO SET ID MAPPING FROM RXNSAT.RRF")
    print("=" * 80)
    
    # Use the most recent RXNSAT.RRF file
    rxnsat_files = [
        RAW_DATA_DIR / "extracted_rrf/RxNorm03022026_extracted/rrf/RXNSAT.RRF",
        RAW_DATA_DIR / "extracted_rrf/RxNorm02022026_extracted/rrf/RXNSAT.RRF",
        RAW_DATA_DIR / "extracted_rrf/RxNorm01052026_extracted/rrf/RXNSAT.RRF",
    ]
    
    rxnsat_file = None
    for file in rxnsat_files:
        if file.exists():
            rxnsat_file = file
            print(f"Using RxNorm file: {file}")
            break
    
    if not rxnsat_file:
        print("ERROR: No RXNSAT.RRF file found!")
        return
    
    # Parse RXNSAT.RRF
    rxcui_to_setids = parse_rxnsat_rrf(rxnsat_file)
    
    # Save the mapping
    output_file = RAW_DATA_DIR / "rxnorm_rxcui_to_setid.json"
    print(f"\nSaving mapping to {output_file}...")
    
    with open(output_file, 'w') as f:
        json.dump(rxcui_to_setids, f, indent=2)
    
    print(f"✅ Saved {len(rxcui_to_setids):,} RxCUI to Set ID mappings")
    
    # Print some statistics
    print("\nStatistics:")
    print(f"  Total RxCUIs with Set IDs: {len(rxcui_to_setids):,}")
    
    total_set_ids = sum(len(setids) for setids in rxcui_to_setids.values())
    print(f"  Total Set ID entries: {total_set_ids:,}")
    
    avg_set_ids = total_set_ids / len(rxcui_to_setids) if rxcui_to_setids else 0
    print(f"  Average Set IDs per RxCUI: {avg_set_ids:.2f}")
    
    # Show some examples with actual RxCUIs (numeric)
    print("\nSample RxCUIs with Set IDs:")
    count = 0
    for rxcui, setids in rxcui_to_setids.items():
        if count >= 10:
            break
        print(f"  RxCUI {rxcui}: {setids[:3]}{'...' if len(setids) > 3 else ''}")
        count += 1
    
    print(f"\n✅ Mapping generation complete!")

if __name__ == "__main__":
    main()
