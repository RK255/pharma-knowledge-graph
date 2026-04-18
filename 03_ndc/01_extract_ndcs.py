#!/usr/bin/env python3
"""
NDC and Set ID Extractor v5
===========================
Extract NDCs and SPL Set IDs from RXNSAT.RRF with proper format normalization.

Outputs:
  - ndc_to_rxcui.json (NDC → RxCUI mapping)
  - rxcui_to_setid.json (RxCUI → Set ID mapping for PI linking)

Handles: 11-digit, 5-4-2, 5-3-2, 4-4-2 NDC formats

Usage:
    python 01_extract_ndcs.py              # Interactive selection
    python 01_extract_ndcs.py --auto       # Use most recent
    python 01_extract_ndcs.py --source-date 2026-02-02  # Match specific date
"""

import argparse
import json
import os
import sys
from datetime import datetime
from collections import defaultdict

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
EXTRACTED_DIR = f"{RAW_DATA_DIR}/extracted_rrf"
OUTPUT_DIR = f"{BASE_DIR}/data/raw_data"

# Add shared_state for source tracking
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from shared_state import load_source_selection, save_source_selection


def normalize_ndc_to_542(ndc_str: str) -> str:
    """
    Normalize ANY NDC format to 5-4-2 hyphenated.
    
    Handles:
    - 11-digit: 59050026800 → 59050-0268-00
    - 5-4-2: 59050-0268-00 → 59050-0268-00
    - 5-3-2: 59050-268-00 → 59050-0268-00 (pad middle to 4)
    - 4-4-2: 0869-0871-18 → 08690-0871-18 (pad first to 5)
    - 5-3-1: 59050-268-0 → 59050-0268-00
    """
    if not ndc_str:
        return ""
    
    # Remove hyphens and spaces
    clean = ndc_str.strip().replace("-", "").replace(" ", "")
    
    # Handle 11-digit (RXNORM format)
    if len(clean) == 11:
        return f"{clean[:5]}-{clean[5:9]}-{clean[9:]}"
    
    # Handle 10-digit (need to determine format)
    if len(clean) == 10:
        # Parse original format to determine padding
        parts = ndc_str.strip().split('-')
        if len(parts) == 3:
            p1, p2, p3 = parts
            # 5-3-2: pad middle
            if len(p1) == 5 and len(p2) == 3:
                return f"{p1}-{p2.zfill(4)}-{p3}"
            # 4-4-2: pad first
            elif len(p1) == 4 and len(p2) == 4:
                return f"{p1.zfill(5)}-{p2}-{p3}"
            # 5-4-1: pad last
            elif len(p1) == 5 and len(p2) == 4 and len(p3) == 1:
                return f"{p1}-{p2}-{p3.zfill(2)}"
    
    # Already 5-4-2 format
    if len(clean) == 11:
        return f"{clean[:5]}-{clean[5:9]}-{clean[9:]}"
    
    # Fallback: return as-is with warning
    return ndc_str.strip()


def find_rxnsat_file(source_date=None, auto=False):
    """Find the RXNSAT.RRF file."""
    extracted_dirs = []
    if os.path.exists(EXTRACTED_DIR):
        for subdir in sorted(os.listdir(EXTRACTED_DIR), reverse=True):
            full_path = os.path.join(EXTRACTED_DIR, subdir, "rrf", "RXNSAT.RRF")
            if os.path.exists(full_path):
                extracted_dirs.append((subdir, full_path))
    
    if not extracted_dirs:
        raise FileNotFoundError("No RXNSAT.RRF found")
    
    # Check for saved source selection from RxNorm step
    saved = load_source_selection("RxNorm")
    if saved and not source_date:
        saved_date = saved.get("metadata", {}).get("source_date")
        if saved_date:
            source_date = saved_date
            print(f"Using source date from RxNorm step: {source_date}")
    
    # Auto-select if source_date provided
    if source_date:
        for subdir, path in extracted_dirs:
            if source_date in subdir:
                print(f"Using source date {source_date}: {subdir}")
                return path
    
    # Auto-select most recent if auto=True
    if auto:
        subdir, path = extracted_dirs[0]
        print(f"Auto-selected most recent: {subdir}")
        return path
    
    # Interactive selection
    print("\nAvailable RXNSAT.RRF files:")
    for i, (subdir, path) in enumerate(extracted_dirs, 1):
        print(f"  [{i}] {subdir}")
    
    choice = input("\nSelect source [1-{len(extracted_dirs)}]: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(extracted_dirs):
            return extracted_dirs[idx][1]
    except ValueError:
        pass
    
    print("Invalid selection, using most recent")
    return extracted_dirs[0][1]


def parse_rxnsat(rxnsat_file: str):
    """
    Parse RXNSAT.RRF to extract NDCs and Set IDs.
    
    RXNSAT.RRF Format (pipe-delimited):
    Field 1: RxCUI
    Field 4: RXAUI
    Field 9: ATN (Attribute Name) - NDC or SPL_SET_ID
    Field 10: SAB (Source)
    Field 11: ATV (Attribute Value) - the NDC code or Set ID
    
    Returns:
        tuple: (ndc_to_rxcui, rxcui_to_ndcs, rxcui_to_setids)
    """
    print(f"\nParsing RXNSAT.RRF...")
    print(f"  File: {rxnsat_file}")
    
    ndc_to_rxcui = {}
    rxcui_to_ndcs = defaultdict(list)
    rxcui_to_setids = defaultdict(list)
    
    stats = {
        'total_lines': 0,
        'ndc_entries': 0,
        'setid_entries': 0,
        'skipped_suppressed': 0,
    }
    
    # Sources for NDC and Set ID
    ndc_sources = {'RXNORM', 'MTHSPL'}
    setid_sources = {'MTHSPL'}
    
    with open(rxnsat_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            stats['total_lines'] += 1
            
            fields = line.strip().split('|')
            if len(fields) < 12:
                continue
            
            rxcui = fields[0]
            atn = fields[8]      # Attribute Name
            sab = fields[9]      # Source
            atv = fields[10]     # Attribute Value
            suppress = fields[11] if len(fields) > 11 else ""
            
            # Skip suppressed entries
            if suppress == "Y":
                stats['skipped_suppressed'] += 1
                continue
            
            # Extract NDC
            if atn == 'NDC' and sab in ndc_sources:
                normalized_ndc = normalize_ndc_to_542(atv)
                if normalized_ndc:
                    ndc_to_rxcui[normalized_ndc] = rxcui
                    rxcui_to_ndcs[rxcui].append(normalized_ndc)
                    stats['ndc_entries'] += 1
            
            # Extract SPL_SET_ID
            elif atn == 'SPL_SET_ID' and sab in setid_sources:
                if atv:
                    rxcui_to_setids[rxcui].append(atv)
                    stats['setid_entries'] += 1
    
    # Deduplicate set IDs per RxCUI
    for rxcui in rxcui_to_setids:
        rxcui_to_setids[rxcui] = list(set(rxcui_to_setids[rxcui]))
    
    print(f"\n  Processed {stats['total_lines']:,} lines")
    print(f"  NDC entries: {stats['ndc_entries']:,}")
    print(f"  Set ID entries: {stats['setid_entries']:,}")
    print(f"  Skipped (suppressed): {stats['skipped_suppressed']:,}")
    
    return ndc_to_rxcui, dict(rxcui_to_ndcs), dict(rxcui_to_setids)


def main():
    parser = argparse.ArgumentParser(description='Extract NDCs and Set IDs from RXNSAT.RRF')
    parser.add_argument("--auto", action="store_true", help="Auto-select most recent source")
    parser.add_argument("--rxnorm-dir", help="Path to extracted RxNorm directory")
    parser.add_argument('--source-date', help='Match specific source date (YYYY-MM-DD)')
    args = parser.parse_args()
    
    print("=" * 80)
    print("NDC AND SET ID EXTRACTOR")
    print("=" * 80)
    
    # Find RXNSAT file
    if args.rxnorm_dir:
        rxnsat_file = os.path.join(args.rxnorm_dir, "rrf", "RXNSAT.RRF")
        if not os.path.exists(rxnsat_file):
            print(f"ERROR: RXNSAT.RRF not found at {rxnsat_file}")
            sys.exit(1)
        print(f"Using RxNorm directory: {args.rxnorm_dir}")
    else:
        rxnsat_file = find_rxnsat_file(args.source_date, args.auto)
    
    # Parse and extract
    ndc_to_rxcui, rxcui_to_ndcs, rxcui_to_setids = parse_rxnsat(rxnsat_file)
    
    # Save outputs
    source_date = None
    for part in rxnsat_file.split('/'):
        if 'RxNorm' in part and '_' in part:
            source_date = part.replace('RxNorm', '').replace('_extracted', '')
            break
    
    # Save NDC mappings
    ndc_output = {
        'ndc_to_rxcui': ndc_to_rxcui,
        'rxcui_to_ndcs': rxcui_to_ndcs,
        'stats': {
            'ndc_count': len(ndc_to_rxcui),
            'rxcui_count': len(rxcui_to_ndcs),
        },
        'source': 'RXNSAT.RRF',
        'source_date': source_date,
        'created': datetime.now().isoformat(),
    }
    
    ndc_file = os.path.join(OUTPUT_DIR, "ndc_to_rxcui.json")
    with open(ndc_file, 'w') as f:
        json.dump(ndc_output, f)
    print(f"\n✓ Saved {len(ndc_to_rxcui):,} NDC → RxCUI mappings to {ndc_file}")
    
    # Save Set ID mappings
    setid_output = {
        'rxcui_to_setids': rxcui_to_setids,
        'stats': {
            'rxcui_count': len(rxcui_to_setids),
            'setid_count': sum(len(s) for s in rxcui_to_setids.values()),
        },
        'source': 'RXNSAT.RRF',
        'source_date': source_date,
        'created': datetime.now().isoformat(),
    }
    
    setid_file = os.path.join(OUTPUT_DIR, "rxcui_to_setid.json")
    with open(setid_file, 'w') as f:
        json.dump(setid_output, f)
    print(f"✓ Saved {len(rxcui_to_setids):,} RxCUI → Set ID mappings to {setid_file}")
    
    # Save source selection
    save_source_selection("NDC", {
        'file': rxnsat_file,
        'metadata': {'source_date': source_date},
    })
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
