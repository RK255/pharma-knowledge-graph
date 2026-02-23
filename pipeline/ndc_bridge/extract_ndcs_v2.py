#!/usr/bin/env python3
"""
NDC Extractor v2
================
Extract NDCs from RXNSAT.RRF with proper format normalization.
Handles: 11-digit, 5-4-2, 5-3-2, 4-4-2 formats
"""

import os
from collections import defaultdict

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RXNSAT_FILE = f"{BASE_DIR}/data/raw_data/extracted_rrf/RxNorm02022026_extracted/rrf/RXNSAT.RRF"
OUTPUT_FILE = f"{BASE_DIR}/data/raw_data/ndc_normalized_v2.txt"

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

def main():
    print("=" * 70)
    print("NDC EXTRACTOR v2 - Proper Format Normalization")
    print("=" * 70)
    
    # Stats
    stats = defaultdict(int)
    ndc_data = defaultdict(lambda: {"sources": set(), "rxcuis": set(), "ttys": set()})
    
    print(f"\nProcessing: {RXNSAT_FILE}")
    
    with open(RXNSAT_FILE, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 500000 == 0:
                print(f"  Processed {line_num:,} lines...")
            
            parts = line.strip().split('|')
            if len(parts) < 12:
                continue
            
            # Check for NDC attribute
            attr_type = parts[8] if len(parts) > 8 else ""
            if attr_type != "NDC":
                continue
            
            source = parts[9] if len(parts) > 9 else ""
            ndc_raw = parts[10] if len(parts) > 10 else ""
            
            if not ndc_raw:
                continue
            
            stats[f"source_{source}"] += 1
            
            # Normalize NDC
            ndc_normalized = normalize_ndc_to_542(ndc_raw)
            
            if ndc_normalized:
                stats["normalized"] += 1
                ndc_data[ndc_normalized]["sources"].add(source)
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
    
    # Count by source combination
    rxnorm_only = sum(1 for d in ndc_data.values() if d["sources"] == {"RXNORM"})
    mthspl_only = sum(1 for d in ndc_data.values() if d["sources"] == {"MTHSPL"})
    both = sum(1 for d in ndc_data.values() if d["sources"] == {"RXNORM", "MTHSPL"})
    
    print(f"\nNDC Coverage:")
    print(f"  RXNORM only: {rxnorm_only:,}")
    print(f"  MTHSPL only: {mthspl_only:,}")
    print(f"  Both sources: {both:,}")
    
    # Write normalized NDCs
    print(f"\nWriting to: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w') as f:
        for ndc in sorted(ndc_data.keys()):
            sources = ",".join(sorted(ndc_data[ndc]["sources"]))
            f.write(f"{ndc}\t{sources}\n")
    
    print(f"✅ Wrote {len(ndc_data):,} normalized NDCs")
    
    # Show sample
    print(f"\nSample NDCs:")
    for i, (ndc, data) in enumerate(sorted(ndc_data.items())[:10]):
        sources = ",".join(sorted(data["sources"]))
        print(f"  {ndc} [{sources}]")

if __name__ == "__main__":
    main()
