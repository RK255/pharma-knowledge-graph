#!/usr/bin/env python3
"""
NDC Extractor v4
================
Extract NDCs from RXNSAT.RRF with proper format normalization.
Outputs:
  - ndc_to_rxcui.json (NDC → RxCUI mapping for GRC-20 bridge)

Handles: 11-digit, 5-4-2, 5-3-2, 4-4-2 formats

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
        # Handle both YYYY-MM-DD and MMDDYYYY formats
        date_parts = source_date.split("-")
        if len(date_parts) == 3:
            y, m, d = date_parts
            mmddyyyy = f"{m}{d}{y}"
        else:
            mmddyyyy = source_date
        
        for name, path in extracted_dirs:
            if mmddyyyy in name:
                print(f"\nAuto-selected: {name} (matched source_date: {source_date})")
                return path, name
    
    if auto or len(extracted_dirs) == 1:
        print(f"\nAuto-selected: {extracted_dirs[0][0]}")
        return extracted_dirs[0][1], extracted_dirs[0][0]
    
    print("\nAvailable RXNSAT.RRF files:")
    for i, (name, path) in enumerate(extracted_dirs, 1):
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"  [{i}] {name} ({size_mb:.1f} MB)")
    
    try:
        choice = int(input(f"\nSelect [1-{len(extracted_dirs)}] (default: 1): ") or "1")
        idx = max(1, min(choice, len(extracted_dirs))) - 1
    except (ValueError, EOFError):
        idx = 0
    
    return extracted_dirs[idx][1], extracted_dirs[idx][0]


def extract_date_from_filename(filename: str) -> str:
    """Extract date from RxNorm filename like RxNorm02022026_extracted -> 2026-02-02."""
    import re
    match = re.search(r'RxNorm(\d{8})', filename)
    if match:
        date_str = match.group(1)
        return f"{date_str[4:8]}-{date_str[:2]}-{date_str[2:4]}"
    return None


def main(source_date=None, auto=False, rxnorm_dir=None):
	print("=" * 70)
	print("NDC EXTRACTOR v4 - NDC + RxCUI Mapping")
	print("=" * 70)
	print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	
	# Find RXNSAT file
	# If a specific source directory is provided, use it directly
	if rxnorm_dir:
		# Construct the path to RXNSAT.RRF
		rxnsat_path = os.path.join(rxnorm_dir, "rrf", "RXNSAT.RRF")
		if os.path.exists(rxnsat_path):
			rxnsat_file = rxnsat_path
			# Extract source name from the directory path
			source_name = os.path.basename(rxnorm_dir.rstrip('/'))
			print(f"  [INFO] Using specified RxNorm directory: {source_name}")
		else:
			# Try without 'rrf' subdirectory
			rxnsat_path = os.path.join(rxnorm_dir, "RXNSAT.RRF")
			if os.path.exists(rxnsat_path):
				rxnsat_file = rxnsat_path
				source_name = os.path.basename(rxnorm_dir.rstrip('/'))
				print(f"  [INFO] Using specified RxNorm directory: {source_name}")
			else:
				print(f"  [ERROR] RXNSAT.RRF not found in specified directory: {rxnorm_dir}")
				sys.exit(1)
	else:
		# Fall back to existing file selection logic
		rxnsat_file, source_name = find_rxnsat_file(source_date=source_date, auto=auto)
	
	actual_source_date = extract_date_from_filename(source_name)
	
	# Save source selection for bridge step
	save_source_selection("RxNorm_RXNSAT", rxnsat_file, {
		"source_name": source_name,
		"source_date": actual_source_date
	})
	
	# Stats
	stats = defaultdict(int)
	ndc_data = defaultdict(lambda: {"sources": set(), "rxcuis": set()})
	rxcui_to_ndcs = defaultdict(set)
	
	print(f"\n[1/2] Processing: {rxnsat_file}")
	
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
	
	# Stats output
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
	
	# Output: ndc_to_rxcui.json
	output_json = f"{OUTPUT_DIR}/ndc_to_rxcui.json"
	print(f"\n[2/2] Writing: {output_json}")
	
	# Build mappings
	ndc_to_rxcui = {}
	for ndc, data in ndc_data.items():
		rxcuis = sorted(data["rxcuis"])
		# Store as single string if only one RxCUI, else list
		ndc_to_rxcui[ndc] = rxcuis[0] if len(rxcuis) == 1 else rxcuis
	
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
		"source": source_name,
		"source_date": actual_source_date,
		"created": datetime.now().isoformat()
	}
	
	with open(output_json, 'w') as f:
		json.dump(output_data, f, indent=2)
	
	size_mb = os.path.getsize(output_json) / 1024 / 1024
	print(f"  ✅ Wrote {size_mb:.1f} MB ({len(ndc_data):,} NDCs)")
	
	# Show sample
	print(f"\nSample NDC → RxCUI:")
	for i, (ndc, data) in enumerate(sorted(ndc_data.items())[:5]):
		sources = ",".join(sorted(data["sources"]))
		rxcuis = ",".join(sorted(data["rxcuis"])[:3])
		if len(data["rxcuis"]) > 3:
			rxcuis += "..."
		print(f"  {ndc} [{sources}] → {rxcuis}")
	
	print(f"\n{'='*70}")
	print("EXTRACTION COMPLETE")
	print(f"{'='*70}")
	return output_json

def parse_args():
    parser = argparse.ArgumentParser(description="Extract NDC codes from RxNorm RXNSAT.RRF")
    parser.add_argument("--auto", action="store_true", help="Use most recent source (no prompts)")
    parser.add_argument("--source-date", help="Auto-select source with this date (YYYY-MM-DD)")
    parser.add_argument("--rxnorm-dir", help="Direct path to RxNorm extracted directory")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(source_date=args.source_date, auto=args.auto, rxnorm_dir=args.rxnorm_dir)
