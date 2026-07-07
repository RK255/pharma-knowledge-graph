#!/usr/bin/env python3
"""Build ingredient crosswalk: Canadian DPD → RxNorm IN"""

import json
import pandas as pd
from pathlib import Path
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR, PRICING_DIR
BASE_DIR = PRICING_DIR
GEO_DIR = BASE_DIR.parent / "geo-ingestor"

# Salt removal for matching
SALTS = [
    'SULFATE', 'SULPHATE', 'HYDROCHLORIDE', 'HCL', 'MALEATE', 'SODIUM', 
    'POTASSIUM', 'ACETATE', 'BITARTRATE', 'MESYLATE', 'FUMARATE', 
    'SUCCINATE', 'TARTRATE', 'PHOSPHATE', 'CITRATE', 'BESYLATE', 'CALCIUM',
    'DIMESYLATE', 'MEDOXOMIL', 'PROPIONATE', 'FUROATE', 'VALERATE',
    'HEMIHYDRATE', 'MONOHYDRATE', 'DIHYDRATE', 'SODIUM PHOSPHATE',
    'HYDROBROMIDE', 'NITRATE', 'BENZOATE', 'SUSPENSION', 'INJECTION',
    'TABLET', 'CAPSULE', 'ORAL', 'TOPICAL'
]

# Canadian → US synonyms (same drug, different name)
CANADA_TO_US_SYNONYMS = {
    'SALBUTAMOL': 'ALBUTEROL',
    'SALBUTAMOL SULFATE': 'ALBUTEROL SULFATE',
    'ACETYLSALICYLIC ACID': 'ASPIRIN',
    'PARACETAMOL': 'ACETAMINOPHEN',
    'CLOMIFENE': 'CLOMIPHENE',
    'ETHINYLESTRADIOL': 'ETHINYL ESTRADIOL',
    'NORETHISTERONE': 'NORETHINDRONE',
    'BECLOMETASONE': 'BECLOMETHASONE',
    'VITAMIN D2': 'ERGOCALCIFEROL',
    'VITAMIN D3': 'CHOLECALCIFEROL',
}

def normalize_ingredient(name):
    """Normalize for matching"""
    if not name or pd.isna(name):
        return ""
    name = str(name).upper().strip()
    if '(' in name:
        name = name.split('(')[0].strip()
    for salt in SALTS:
        name = re.sub(rf'\s+{salt}\b', '', name, flags=re.IGNORECASE)
    return name.strip()

# Load RxNorm ingredients from master file
print("Loading RxNorm ingredients from master file...")
rxnorm_ingredients = {}  # normalized_name -> {rxcui, original_name, ...}
rxnorm_by_rxcui = {}  # rxcui -> full record

master_file = GEO_DIR / "data_to_publish/full_geo_extraction_v21.jsonl"
with open(master_file, 'r') as f:
    for line in f:
        record = json.loads(line.strip())
        rxcui = record['rxcui']
        name = record['name']
        norm = normalize_ingredient(name)
        
        if norm and norm not in rxnorm_ingredients:
            rxnorm_ingredients[norm] = {
                'rxcui': rxcui,
                'name': name,
                'normalized': norm
            }
        rxnorm_by_rxcui[rxcui] = record

print(f"Loaded {len(rxnorm_ingredients)} unique RxNorm ingredients")

# Load Canadian crosswalk
print("\nLoading Canadian DPD crosswalk...")
canada_path = BASE_DIR / "crosswalk_reports/canadian_dpd_crosswalk_fresh.csv"
canada_df = pd.read_csv(canada_path, dtype=str)

# Extract unique Canadian ingredients
canada_ingredients = set()
for ing_str in canada_df['ingredient_name'].dropna():
    for ing in str(ing_str).split('|'):
        norm = normalize_ingredient(ing)
        if norm:
            canada_ingredients.add((norm, ing.strip()))

print(f"Found {len(canada_ingredients)} unique Canadian ingredients")

# Match Canadian ingredients to RxNorm
print("\n" + "="*70)
print("MATCHING CANADIAN INGREDIENTS TO RXNORM")
print("="*70)

results = []
matched = []
unmatched = []
aliases_needed = []

for norm_can, orig_can in sorted(canada_ingredients):
    # Check direct match
    if norm_can in rxnorm_ingredients:
        match = rxnorm_ingredients[norm_can]
        results.append({
            'canadian_name': orig_can,
            'normalized': norm_can,
            'matched': True,
            'rxcui': match['rxcui'],
            'rxnorm_name': match['name'],
            'alias_needed': norm_can != normalize_ingredient(match['name'])
        })
        matched.append((norm_can, match['rxcui']))
        continue
    
    # Check synonym mapping
    us_equiv = CANADA_TO_US_SYNONYMS.get(norm_can)
    if us_equiv:
        us_norm = normalize_ingredient(us_equiv)
        if us_norm in rxnorm_ingredients:
            match = rxnorm_ingredients[us_norm]
            results.append({
                'canadian_name': orig_can,
                'normalized': norm_can,
                'matched': True,
                'rxcui': match['rxcui'],
                'rxnorm_name': match['name'],
                'alias_needed': True  # Always need alias for synonyms
            })
            matched.append((norm_can, match['rxcui']))
            aliases_needed.append((orig_can, match['rxcui']))
            continue
    
    # No match found
    results.append({
        'canadian_name': orig_can,
        'normalized': norm_can,
        'matched': False,
        'rxcui': None,
        'rxnorm_name': None,
        'alias_needed': False
    })
    unmatched.append((norm_can, orig_can))

# Summary
print(f"\nMatching Summary:")
print(f"  Matched to RxNorm: {len(matched)}")
print(f"  Unmatched (Canada-only): {len(unmatched)}")
print(f"  Aliases needed: {len(aliases_needed)}")

# Show sample matches
print("\n" + "="*70)
print("SAMPLE MATCHES (first 15)")
print("="*70)
for r in results[:15]:
    if r['matched']:
        alias_note = " [ALIAS NEEDED]" if r['alias_needed'] else ""
        print(f"  ✓ {r['canadian_name']} → RxCUI {r['rxcui']} ({r['rxnorm_name']}){alias_note}")

print("\n" + "="*70)
print("SAMPLE UNMATCHED (first 30)")
print("="*70)
for r in results:
    if not r['matched']:
        print(f"  ✗ {r['canadian_name']}")

# Save crosswalk
results_df = pd.DataFrame(results)
output_path = BASE_DIR / "crosswalk_reports/canada_to_rxnorm_ingredient_crosswalk.csv"
results_df.to_csv(output_path, index=False)
print(f"\nSaved crosswalk to: {output_path}")

# Show unmatched that might have partial matches
print("\n" + "="*70)
print("UNMATCHED - Checking for partial matches in RxNorm")
print("="*70)
partial_found = []
for norm_can, orig_can in unmatched[:50]:
    # Look for partial matches
    words = norm_can.split()
    for word in words:
        if len(word) > 4:  # Skip short words
            partial = [n for n in rxnorm_ingredients.keys() if word in n]
            if partial:
                partial_found.append((orig_can, word, partial[:3]))
                break

if partial_found:
    print("Partial matches found:")
    for orig, word, matches in partial_found[:20]:
        print(f"  {orig} ← '{word}' → {matches}")
else:
    print("No obvious partial matches found")

# Save aliases file for later
print("\n" + "="*70)
print("ALIASES TO ADD TO INGREDIENTS")
print("="*70)
alias_records = []
for orig_can, rxcui in aliases_needed[:20]:
    rxnorm_record = rxnorm_by_rxcui.get(rxcui, {})
    alias_records.append({
        'rxcui': rxcui,
        'rxnorm_name': rxnorm_record.get('name', ''),
        'canadian_alias': orig_can
    })
    print(f"  RxCUI {rxcui}: Add alias '{orig_can}' to '{rxnorm_record.get('name', '')}'")

aliases_df = pd.DataFrame(alias_records)
aliases_path = BASE_DIR / "crosswalk_reports/canada_aliases_to_add.csv"
aliases_df.to_csv(aliases_path, index=False)
print(f"\nSaved aliases to: {aliases_path}")
