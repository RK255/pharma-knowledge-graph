#!/usr/bin/env python3
"""
Merge NADAC and CostPlus pricing data for v21.1 extractor
===========================================================
Combines: nadac_pricing_report.json + costplus_pricing_report.json
Output:   pricing_for_your_ndcs.json (in format expected by extractor)
"""
import json
from pathlib import Path

# Input files
NADAC_FILE = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/pricing/data/US/nadac_pricing_report.json")
COSTPLUS_FILE = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/pricing/data/US/costplus_pricing_report.json")

# Output file (where v21 expects it)
OUTPUT_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/pricing/analysis")
OUTPUT_FILE = OUTPUT_DIR / "pricing_for_your_ndcs.json"


def load_pricing_file(filepath, price_key, has_price_key):
    """Load a pricing file and return dict keyed by NDC11"""
    pricing_by_ndc = {}
    
    if not filepath.exists():
        print(f"⚠️  File not found: {filepath}")
        return pricing_by_ndc
    
    print(f"Loading {filepath.name}...")
    
    with open(filepath) as f:
        data = json.load(f)
    
    # Handle different possible structures
    entries = data if isinstance(data, list) else data.get('pricing', [])
    
    for entry in entries:
        # Try to find NDC11 in various possible fields
        ndc = entry.get('ndc11') or entry.get('ndc') or entry.get('NDC11') or entry.get('NDC')
        if not ndc:
            continue
        
        # Normalize to 11 digits
        ndc_clean = str(ndc).replace('-', '').strip().zfill(11)
        
        # Extract price - try various field names
        price = None
        for key in ['unit_price', 'unit_billing_price', 'price', 'nadac_unit_price', 'costplus_unit_price']:
            if key in entry and entry[key] is not None:
                try:
                    price = float(entry[key])
                    break
                except (ValueError, TypeError):
                    continue
        
        if price is not None:
            if ndc_clean not in pricing_by_ndc:
                pricing_by_ndc[ndc_clean] = {}
            pricing_by_ndc[ndc_clean][price_key] = price
            pricing_by_ndc[ndc_clean][has_price_key] = True
    
    print(f"  ✓ Loaded {len(pricing_by_ndc)} priced NDCs")
    return pricing_by_ndc


def merge_pricing():
    """Merge NADAC and CostPlus pricing data"""
    print("=" * 60)
    print("MERGING PRICING DATA")
    print("=" * 60)
    
    # Create output directory if needed
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load both pricing files
    nadac_data = load_pricing_file(NADAC_FILE, 'nadac_unit_price', 'has_nadac')
    costplus_data = load_pricing_file(COSTPLUS_FILE, 'costplus_unit_billing_price', 'has_costplus')
    
    # Merge by NDC11
    all_ndcs = set(nadac_data.keys()) | set(costplus_data.keys())
    print(f"\nTotal unique NDCs: {len(all_ndcs):,}")
    
    merged = []
    for ndc in all_ndcs:
        entry = {'ndc11': ndc}
        
        # Add NADAC if present
        if ndc in nadac_data:
            entry['has_nadac'] = True
            entry['nadac_unit_price'] = nadac_data[ndc]['nadac_unit_price']
        else:
            entry['has_nadac'] = False
        
        # Add CostPlus if present
        if ndc in costplus_data:
            entry['has_costplus'] = True
            entry['costplus_unit_billing_price'] = costplus_data[ndc]['costplus_unit_billing_price']
            # v21 expects this field name:
            entry['costplus_unit_price'] = costplus_data[ndc]['costplus_unit_billing_price']
        else:
            entry['has_costplus'] = False
        
        merged.append(entry)
    
    # Write output
    output = {'pricing': merged}
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n{'=' * 60}")
    print("MERGE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Total NDCs: {len(merged):,}")
    print(f"  With NADAC: {sum(1 for e in merged if e['has_nadac']):,}")
    print(f"  With CostPlus: {sum(1 for e in merged if e['has_costplus']):,}")
    print(f"  With both: {sum(1 for e in merged if e['has_nadac'] and e['has_costplus']):,}")
    print("=" * 60)


if __name__ == "__main__":
    merge_pricing()
