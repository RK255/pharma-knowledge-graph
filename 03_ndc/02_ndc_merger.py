#!/usr/bin/env python3
"""
NDC Merger v1.0
================
Merges RXNORM and MTHSPL NDC entries into single entries per physical NDC.

Input: ndc_to_rxcui.json (with rxcui_to_ndc_entries)
Output: ndc_merged.json (clean, one entry per physical NDC)

Merge key: Physical NDC (strip leading zeros from all segments)
  e.g., 59050-0268-00 (RXNORM) + 59050-268-00 (MTHSPL) = same product
"""

import json
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
BASE_DIR = str(config.BASE_DIR)
INPUT_FILE = Path(f"{BASE_DIR}/data/raw_data/ndc_to_rxcui.json")
OUTPUT_FILE = Path(f"{BASE_DIR}/data/raw_data/ndc_merged.json")


def normalize_physical_ndc(ndc_str: str) -> str:
    """
    Normalize to physical NDC key by stripping leading zeros from all segments.
    59050-0268-00 → 59050-268-0
    59050-268-00 → 59050-268-0 (same!)
    """
    if not ndc_str or '-' not in ndc_str:
        return ndc_str
    
    parts = ndc_str.split('-')
    # Strip leading zeros from each part, but keep at least one digit
    normalized = [part.lstrip('0') or '0' for part in parts]
    return '-'.join(normalized)


def main():
    print("=" * 60)
    print("NDC MERGER v1.0")
    print("=" * 60)
    
    # Load extraction output
    print(f"\n[1/3] Loading {INPUT_FILE.name}...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
    
    rxcui_to_entries = data.get('rxcui_to_ndc_entries', {})
    source_date = data.get('source_date', 'unknown')
    
    print(f"  Loaded {len(rxcui_to_entries)} RxCUIs")
    total_entries = sum(len(entries) for entries in rxcui_to_entries.values())
    print(f"  Total entries (before merge): {total_entries:,}")
    
    # Merge entries
    print("\n[2/3] Merging by physical NDC...")
    
    # Structure: rxcui -> {physical_ndc -> merged_entry}
    merged_by_rxcui = defaultdict(dict)
    
    for rxcui, entries in rxcui_to_entries.items():
        for entry in entries:
            ndc11 = entry['ndc11_hyphens']
            physical_key = normalize_physical_ndc(ndc11)
            
            if physical_key not in merged_by_rxcui[rxcui]:
                # First entry for this physical NDC
                merged_by_rxcui[rxcui][physical_key] = {
                    'ndc': ndc11,  # Use first encountered as main
                    'ndc_formats': {
                        'ndc11_hyphens': ndc11,
                        'ndc11_no_hyphens': entry.get('ndc11_no_hyphens'),
                        'ndc10_hyphens': entry.get('ndc10_hyphens'),
                    },
                    'sources': set(entry.get('sources', [])),
                    'rxcui': rxcui,
                }
            else:
                # Merge additional formats
                existing = merged_by_rxcui[rxcui][physical_key]
                
                # Keep NDC11 without hyphens if available
                if entry.get('ndc11_no_hyphens'):
                    existing['ndc_formats']['ndc11_no_hyphens'] = entry['ndc11_no_hyphens']
                
                # Keep NDC10 if available
                if entry.get('ndc10_hyphens'):
                    existing['ndc_formats']['ndc10_hyphens'] = entry['ndc10_hyphens']
                
                # Merge sources
                existing['sources'].update(entry.get('sources', []))
    
    # Convert sets to lists for JSON serialization
    output_entries = []
    total_merged = 0
    multi_format = 0
    
    for rxcui, physical_entries in merged_by_rxcui.items():
        for physical_key, entry in physical_entries.items():
            # Convert sets to lists
            entry['sources'] = list(entry['sources'])
            
            # Count formats
            format_count = sum(1 for v in entry['ndc_formats'].values() if v)
            if format_count > 1:
                multi_format += 1
            
            output_entries.append(entry)
            total_merged += 1
    
    print(f"  Merged entries: {total_merged:,}")
    print(f"  With multiple formats: {multi_format:,}")
    
    # Calculate reduction
    reduction = total_entries - total_merged
    print(f"  Reduced by: {reduction:,} ({100*reduction/total_entries:.1f}%)")
    
    # Save output
    print(f"\n[3/3] Saving to {OUTPUT_FILE.name}...")
    
    output = {
        'ndc_entries': output_entries,
        'stats': {
            'total_entries': total_merged,
            'multi_format_entries': multi_format,
            'rxcui_count': len(merged_by_rxcui),
            'source_date': source_date,
        },
        'format_version': '1.0',
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Saved {len(output_entries):,} merged entries")
    print(f"  File size: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Show sample
    print("\nSample merged entries:")
    for entry in output_entries[:3]:
        print(f"\n  {entry['ndc']}:")
        for fmt, val in entry['ndc_formats'].items():
            if val:
                print(f"    {fmt}: {val}")
        print(f"    sources: {entry['sources']}")
        print(f"    rxcui: {entry['rxcui']}")


if __name__ == "__main__":
    main()
