#!/usr/bin/env python3
"""
NDC Extractor v3
================
Extract NDCs from RXNSAT.RRF with proper format normalization.
Outputs:
  - ndc_normalized_v2.txt (NDCs with sources)
  - ndc_to_rxcui.json (NDC → RxCUI mapping for GRC-20 bridge)

Handles: 11-digit, 5-4-2, 5-3-2, 4-4-2 formats
"""

import argparse
import os
import argparse
import json
from datetime import datetime
from collections import defaultdict

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
EXTRACTED_DIR = f"{RAW_DATA_DIR}/extracted_rrf"
OUTPUT_DIR = f"{BASE_DIR}/data/raw_data"

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


def find_rxnsat_file(source_date=None):
    """Find the most recent RXNSAT.RRF file."""
    extracted_dirs = []
    if os.path.exists(EXTRACTED_DIR):
        for subdir in sorted(os.listdir(EXTRACTED_DIR), reverse=True):
            full_path = os.path.join(EXTRACTED_DIR, subdir, "rrf", "RXNSAT.RRF")
            if os.path.exists(full_path):
                extracted_dirs.append((subdir, full_path))
    
    if not extracted_dirs:
        raise FileNotFoundError("No RXNSAT.RRF found")
    
    # Auto-select if source_date provided
    if source_date:
        # Handle both YYYY-MM-DD and MMDDYYYY formats
        # source_date like "2026-02-02" should match "RxNorm02022026" (MMDDYYYY)
        date_parts = source_date.split("-")
        if len(date_parts) == 3:
            y, m, d = date_parts
            mmddyyyy = f"{m}{d}{y}"  # 02022026
            yyyymmdd = f"{y}{m}{d}"  # 20260202
        else:
            mmddyyyy = source_date
            yyyymmdd = source_date
        
        for name, path in extracted_dirs:
            if mmddyyyy in name or yyyymmdd in name:
                print(f"\nAuto-selected: {name} (matched source_date: {source_date})")
                return path
        print(f"\nWarning: No match for source_date {source_date}, using most recent")
        return extracted_dirs[0][1]
    
    print("\nAvailable RXNSAT.RRF files:")
    for i, (name, path) in enumerate(extracted_dirs, 1):
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"  [{i}] {name} ({size_mb:.1f} MB)")
    
    if len(extracted_dirs) == 1:
        print(f"\nUsing: {extracted_dirs[0][0]}")
        return extracted_dirs[0][1]
    
    try:
        choice = int(input(f"\nSelect [1-{len(extracted_dirs)}]: ") or "1")
        return extracted_dirs[choice - 1][1]
    except (ValueError, IndexError):
        return extracted_dirs[0][1]


def main(source_date=None):
    print("=" * 70)
    print("NDC EXTRACTOR v3 - NDC + RxCUI Mapping")
    print("=" * 70)
    
    # Find RXNSAT file
    rxnsat_file = find_rxnsat_file(source_date=source_date)
    
    # Stats
    stats = defaultdict(int)
    ndc_data = defaultdict(lambda: {"sources": set(), "rxcuis": set()})
    
    # Also build reverse mapping for stats
    rxcui_to_ndcs = defaultdict(set)
    
    print(f"\nProcessing: {rxnsat_file}")
    
    with open(rxnsat_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 500000 == 0:
                print(f"  Processed {line_num:,} lines...")
            
            parts = line.strip().split('|')
            if len(parts) < 11:
                continue
            
            # Check for NDC attribute
            attr_type = parts[8] if len(parts) > 8 else ""
            if attr_type != "NDC":
                continue
            
            rxcui = parts[0].strip() if len(parts) > 0 else ""
            source = parts[9] if len(parts) > 9 else ""
            ndc_raw = parts[10] if len(parts) > 10 else ""
            
            if not ndc_raw or not rxcui:
                continue
            
            stats[f"source_{source}"] += 1
            
            # Normalize NDC
            ndc_normalized = normalize_ndc_to_542(ndc_raw)
            
            if ndc_normalized:
                stats["normalized"] += 1
                ndc_data[ndc_normalized]["sources"].add(source)
                ndc_data[ndc_normalized]["rxcuis"].add(rxcui)
                rxcui_to_ndcs[rxcui].add(ndc_normalized)
            else:
                stats["failed_normalize"] += 1
    
    print(f"\n{'='*70}")
    print("STATISTICS")
    print(f"{'='*70}")
    print(f"RXNORM source NDCs: {stats['source_RXNORM']:,}")
    print(f"MTHSPL source NDCs: {stats['source_MTHSPL']:,}")
    print(f"Normalized: {stats['normalized']:,}")
    print(f"Failed to normalize: {stats.get('failed_normalize', 0):,}")
    print(f"Unique NDCs: {len(ndc_data):,}")
    print(f"Unique RxCUIs: {len(rxcui_to_ndcs):,}")
    
    # Count by source combination
    rxnorm_only = sum(1 for d in ndc_data.values() if d["sources"] == {"RXNORM"})
    mthspl_only = sum(1 for d in ndc_data.values() if d["sources"] == {"MTHSPL"})
    both = sum(1 for d in ndc_data.values() if d["sources"] == {"RXNORM", "MTHSPL"})
    
    print(f"\nNDC Coverage:")
    print(f"  RXNORM only: {rxnorm_only:,}")
    print(f"  MTHSPL only: {mthspl_only:,}")
    print(f"  Both sources: {both:,}")
    
    # Output 1: ndc_normalized_v2.txt (NDCs with sources)
    output_txt = f"{OUTPUT_DIR}/ndc_normalized_v2.txt"
    print(f"\nWriting: {output_txt}")
    with open(output_txt, 'w') as f:
        for ndc in sorted(ndc_data.keys()):
            sources = ",".join(sorted(ndc_data[ndc]["sources"]))
            f.write(f"{ndc}\t{sources}\n")
    print(f"  ✅ Wrote {len(ndc_data):,} NDCs")
    
    # Output 2: ndc_to_rxcui.json (for GRC-20 bridge)
    output_json = f"{OUTPUT_DIR}/ndc_to_rxcui.json"
    print(f"\nWriting: {output_json}")
    
    # Build ndc_to_rxcui mapping (convert sets to lists, strings for compatibility)
    ndc_to_rxcui = {}
    for ndc, data in ndc_data.items():
        rxcuis = sorted(data["rxcuis"])
        # Store as single string if only one RxCUI, else list
        ndc_to_rxcui[ndc] = rxcuis[0] if len(rxcuis) == 1 else rxcuis
    
    # Build reverse mapping for stats
    rxcui_to_ndcs_list = {rxcui: sorted(ndcs) for rxcui, ndcs in rxcui_to_ndcs.items()}
    
    output_data = {
        "ndc_to_rxcui": ndc_to_rxcui,
        "rxcui_to_ndcs": rxcui_to_ndcs_list,
        "stats": {
            "total_ndcs": len(ndc_data),
            "total_rxcuis": len(rxcui_to_ndcs),
            "by_source": {
                "rxnorm_only": rxnorm_only,
                "mthspl_only": mthspl_only,
                "both": both
            }
        },
        "created": datetime.now().isoformat()
    }
    
    with open(output_json, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    size_mb = os.path.getsize(output_json) / 1024 / 1024
    print(f"  ✅ Wrote {size_mb:.1f} MB")
    
    # Show sample
    print(f"\nSample NDC → RxCUI:")
    for i, (ndc, data) in enumerate(sorted(ndc_data.items())[:5]):
        sources = ",".join(sorted(data["sources"]))
        rxcuis = ",".join(sorted(data["rxcuis"])[:3])
        if len(data["rxcuis"]) > 3:
            rxcuis += "..."
        print(f"  {ndc} [{sources}] → {rxcuis}")
    
    print(f"\n{'='*70}")
    print("DONE")
    print(f"{'='*70}")


def parse_args():
    parser = argparse.ArgumentParser(description="Extract NDC codes from RxNorm")
    parser.add_argument("--source-date", help="Auto-select source with this date (YYYY-MM-DD)")
    parser.add_argument("--auto", action="store_true", help="Use defaults")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    main(source_date=args.source_date)
