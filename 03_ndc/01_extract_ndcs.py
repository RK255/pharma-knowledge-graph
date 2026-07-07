#!/usr/bin/env python3
"""
NDC and Set ID Extractor v6.1
=============================
Fixed: Properly format middle segment to 4 digits (5-4-2)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
import config
BASE_DIR = str(config.BASE_DIR)
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
EXTRACTED_DIR = f"{RAW_DATA_DIR}/extracted_rrf"
OUTPUT_DIR = f"{BASE_DIR}/data/raw_data"
from shared_state import load_source_selection, save_source_selection


def normalize_ndc_to_542(ndc_str: str) -> str:
    """Normalize to 5-4-2 hyphenated (NDC11)"""
    if not ndc_str:
        return ""
    
    clean = ndc_str.strip().replace("-", "").replace(" ", "")
    
    if len(clean) == 11:
        return f"{clean[:5]}-{clean[5:9]}-{clean[9:]}"
    
    if len(clean) == 10:
        parts = ndc_str.strip().split('-')
        if len(parts) == 3:
            p1, p2, p3 = parts
            if len(p1) == 5 and len(p2) == 3:
                # 5-3-2 format → 5-4-2 (pad middle segment)
                return f"{p1}-{p2.zfill(4)}-{p3}"  # ← FIX: Added .zfill(4)
            elif len(p1) == 4 and len(p2) == 4:
                return f"{p1.zfill(5)}-{p2}-{p3}"
    
    return ndc_str.strip()


def parse_rxnsat_enhanced(rxnsat_file: str):
    """Parse RXNSAT.RRF to extract NDCs in MULTIPLE FORMATS."""
    print(f"\nParsing RXNSAT.RRF (enhanced with multiple formats)...")
    print(f"  File: {rxnsat_file}")
    
    rxcui_ndc_entries = defaultdict(dict)
    ndc_to_rxcui = {}
    rxcui_to_ndcs = defaultdict(list)
    
    stats = {
        'total_lines': 0,
        'ndc_entries': 0,
        'ndc10_from_mthspl': 0,
        'ndc11_from_rxnorm': 0,
    }
    
    with open(rxnsat_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            stats['total_lines'] += 1
            
            fields = line.strip().split('|')
            if len(fields) < 12:
                continue
            
            rxcui = fields[0]
            atn = fields[8]
            sab = fields[9]
            atv = fields[10]
            suppress = fields[11] if len(fields) > 11 else ""
            
            if atn != 'NDC' or not atv or suppress == "Y":
                continue
            
            if sab == 'RXNORM':
                ndc11_no_hyphens = atv.strip()
                ndc11_hyphens = normalize_ndc_to_542(ndc11_no_hyphens)
                
                if ndc11_hyphens:
                    if ndc11_hyphens not in rxcui_ndc_entries[rxcui]:
                        rxcui_ndc_entries[rxcui][ndc11_hyphens] = {
                            "ndc11_hyphens": ndc11_hyphens,
                            "ndc11_no_hyphens": None,
                            "ndc10_hyphens": None,
                            "sources": []
                        }
                    
                    rxcui_ndc_entries[rxcui][ndc11_hyphens]["ndc11_no_hyphens"] = ndc11_no_hyphens
                    if "RXNORM" not in rxcui_ndc_entries[rxcui][ndc11_hyphens]["sources"]:
                        rxcui_ndc_entries[rxcui][ndc11_hyphens]["sources"].append("RXNORM")
                    
                    stats['ndc11_from_rxnorm'] += 1
            
            elif sab == 'MTHSPL':
                ndc10_hyphens = atv.strip()
                parts = ndc10_hyphens.split('-')
                
                if len(parts) == 3:
                    # FIX: Ensure proper 5-4-2 format (pad both first AND middle segments)
                    parts[0] = parts[0].zfill(5)      # First: 5 digits
                    parts[1] = parts[1].zfill(4)      # ← FIX: Middle: 4 digits (was missing!)
                    ndc11_hyphens = '-'.join(parts)
                    
                    if ndc11_hyphens:
                        if ndc11_hyphens not in rxcui_ndc_entries[rxcui]:
                            rxcui_ndc_entries[rxcui][ndc11_hyphens] = {
                                "ndc11_hyphens": ndc11_hyphens,
                                "ndc11_no_hyphens": None,
                                "ndc10_hyphens": None,
                                "sources": []
                            }
                        
                        rxcui_ndc_entries[rxcui][ndc11_hyphens]["ndc10_hyphens"] = ndc10_hyphens
                        if "MTHSPL" not in rxcui_ndc_entries[rxcui][ndc11_hyphens]["sources"]:
                            rxcui_ndc_entries[rxcui][ndc11_hyphens]["sources"].append("MTHSPL")
                        
                        stats['ndc10_from_mthspl'] += 1
            
            for ndc11_h in rxcui_ndc_entries[rxcui]:
                ndc_to_rxcui[ndc11_h] = rxcui
                if ndc11_h not in rxcui_to_ndcs[rxcui]:
                    rxcui_to_ndcs[rxcui].append(ndc11_h)
    
    rxcui_to_ndc_entries = {}
    for rxcui, entries_dict in rxcui_ndc_entries.items():
        rxcui_to_ndc_entries[rxcui] = list(entries_dict.values())
        stats['ndc_entries'] += len(entries_dict)
    
    print(f"\n  Processed {stats['total_lines']:,} lines")
    print(f"  Total NDC entries: {stats['ndc_entries']:,}")
    print(f"    With NDC11 (RXNORM): {stats['ndc11_from_rxnorm']:,}")
    print(f"    With NDC10 (MTHSPL): {stats['ndc10_from_mthspl']:,}")
    
    return ndc_to_rxcui, dict(rxcui_to_ndcs), dict(rxcui_to_ndc_entries)


def main():
    parser = argparse.ArgumentParser(description='Extract NDCs with multiple formats')
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--source-date", help='Match specific source date')
    args = parser.parse_args()
    
    print("=" * 80)
    print("NDC EXTRACTOR v6.1 - Fixed 5-4-2 formatting")
    print("=" * 80)
    
    rxnsat_files = []
    for subdir in sorted(os.listdir(EXTRACTED_DIR), reverse=True):
        path = os.path.join(EXTRACTED_DIR, subdir, "rrf", "RXNSAT.RRF")
        if os.path.exists(path):
            rxnsat_files.append((subdir, path))
    
    if not rxnsat_files:
        print("ERROR: No RXNSAT.RRF found")
        sys.exit(1)
    
    if args.source_date:
        rxnsat_file = next((p for d, p in rxnsat_files if args.source_date in d), rxnsat_files[0][1])
    elif args.auto:
        rxnsat_file = rxnsat_files[0][1]
    else:
        print("\nAvailable:")
        for i, (d, p) in enumerate(rxnsat_files, 1):
            print(f"  [{i}] {d}")
        choice = input("\nSelect: ").strip()
        rxnsat_file = rxnsat_files[int(choice)-1][1] if choice.isdigit() else rxnsat_files[0][1]
    
    ndc_to_rxcui, rxcui_to_ndcs, rxcui_to_ndc_entries = parse_rxnsat_enhanced(rxnsat_file)
    
    source_date = None
    for part in rxnsat_file.split('/'):
        if 'RxNorm' in part:
            source_date = part.replace('RxNorm', '').replace('_extracted', '')
            break
    
    output = {
        'ndc_to_rxcui': ndc_to_rxcui,
        'rxcui_to_ndcs': rxcui_to_ndcs,
        'rxcui_to_ndc_entries': rxcui_to_ndc_entries,
        'stats': {
            'ndc_count': len(ndc_to_rxcui),
            'rxcui_count': len(rxcui_to_ndcs),
            'entries_with_multiple_formats': sum(
                1 for entries in rxcui_to_ndc_entries.values()
                for e in entries
                if e.get('ndc10_hyphens') and e.get('ndc11_no_hyphens')
            ),
        },
        'source': 'RXNSAT.RRF',
        'source_date': source_date,
        'created': datetime.now().isoformat(),
    }
    
    output_file = os.path.join(OUTPUT_DIR, "ndc_to_rxcui.json")
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Saved to {output_file}")
    print(f"  NDCs: {len(ndc_to_rxcui):,}")
    print(f"  RxCUIs: {len(rxcui_to_ndcs):,}")
    
    print("\nSample entries:")
    for rxcui, entries in list(rxcui_to_ndc_entries.items())[:3]:
        print(f"\n  RxCUI {rxcui}:")
        for entry in entries[:2]:
            print(f"    NDC11: {entry['ndc11_hyphens']}")
            if entry.get('ndc11_no_hyphens'):
                print(f"      └─ No hyphens: {entry['ndc11_no_hyphens']}")
            if entry.get('ndc10_hyphens'):
                print(f"      └─ NDC10: {entry['ndc10_hyphens']}")
            print(f"      └─ Sources: {entry['sources']}")


if __name__ == '__main__':
    main()
