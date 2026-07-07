#!/usr/bin/env python3
"""Rebuild pricing file with both NADAC and CostPlus"""
import sys
import json
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR
PIPELINE_FILE = BASE_DIR / "data" / "pricing" / "reports" / "pricing_for_pipeline.jsonl"
NADAC_FILE = BASE_DIR / "data" / "pricing" / "nadac_current.csv"
OUTPUT_FILE = BASE_DIR / "data" / "pricing" / "analysis" / "pricing_for_your_ndcs.json"

# Load all pricing by NDC
pricing_by_ndc = {}

# 1. Load CostPlus from pipeline (has unit_billing_price)
print("Loading CostPlus from pipeline...")
with open(PIPELINE_FILE) as f:
    for line in f:
        entry = json.loads(line.strip())
        ndc11 = entry.get('ndc11')
        if not ndc11:
            continue
        metadata = entry.get('metadata', {})
        
        pricing_by_ndc[ndc11] = {
            'ndc11': ndc11,
            'has_nadac': False,  # Will be updated if NADAC found
            'has_costplus': True,
            'costplus_unit_price': entry.get('value'),  # Box price
            'costplus_unit_billing_price': metadata.get('unit_billing_price'),
            'costplus_currency': entry.get('currency', 'USD'),
            'pack_size': metadata.get('pack_size'),
            'pack_size_units': metadata.get('pack_size_units'),
            'medication_name': metadata.get('medication_name'),
            'brand_name': metadata.get('brand_name'),
            'form': metadata.get('form'),
            'strength': metadata.get('strength')
        }

# 2. Load NADAC and merge
print("Loading NADAC...")
nadac_count = 0
with open(NADAC_FILE) as f:
    reader = csv.DictReader(f)
    for row in reader:
        # NADAC NDCs are in format like 0002-1433-80, need to normalize to 11 digits
        ndc_raw = row.get('NDC', '').strip()
        if not ndc_raw:
            continue
        
        # Normalize NDC
        clean = ndc_raw.replace('-', '').replace(' ', '')
        if len(clean) == 10:
            ndc11 = clean.zfill(11)
        elif len(clean) == 11:
            ndc11 = clean
        else:
            continue
            
        # Get NADAC price
        try:
            nadac_price = float(row.get('NADAC_Per_Unit', '0').replace('$', '').replace(',', ''))
        except:
            continue
            
        if nadac_price <= 0:
            continue
        
        if ndc11 in pricing_by_ndc:
            # Merge with existing CostPlus entry
            pricing_by_ndc[ndc11]['has_nadac'] = True
            pricing_by_ndc[ndc11]['nadac_unit_price'] = nadac_price
            pricing_by_ndc[ndc11]['nadac_currency'] = 'USD'
        else:
            # New NADAC-only entry
            pricing_by_ndc[ndc11] = {
                'ndc11': ndc11,
                'has_nadac': True,
                'has_costplus': False,
                'nadac_unit_price': nadac_price,
                'nadac_currency': 'USD',
                'medication_name': row.get('Drug_Name', ''),
                'form': row.get('Dosage_Form', ''),
                'strength': row.get('Strength', '')
            }
        nadac_count += 1

# Write output
print(f"Writing {len(pricing_by_ndc):,} entries...")
with open(OUTPUT_FILE, 'w') as f:
    json.dump({'pricing': list(pricing_by_ndc.values())}, f, indent=2)

print(f"Done! Total: {len(pricing_by_ndc):,}")
print(f"  CostPlus only: {sum(1 for p in pricing_by_ndc.values() if p['has_costplus'] and not p['has_nadac'])}")
print(f"  NADAC only: {sum(1 for p in pricing_by_ndc.values() if p['has_nadac'] and not p['has_costplus'])}")
print(f"  Both: {sum(1 for p in pricing_by_ndc.values() if p['has_nadac'] and p['has_costplus'])}")
