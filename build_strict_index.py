#!/usr/bin/env python3
"""
build_strict_index.py

Include ONLY pairs with full 5/5 pricing coverage (US + Canada).
No partial coverage, no gaps.
"""
import csv
from pathlib import Path
from collections import defaultdict

from config import BASE_DIR
BASE = BASE_DIR / "data" / "raw_data"
COVERAGE = BASE / "atc_pricing_coverage.csv"
OUT = BASE / "best_100_strict.csv"

# Load only 5/5 coverage pairs
print("Loading pairs with full 5/5 coverage...")
all_pairs = list(csv.DictReader(open(COVERAGE)))

full_coverage = [p for p in all_pairs 
                 if p["has_nadac"] == "True" 
                 and p["has_costplus"] == "True"
                 and p["has_bc"] == "True" 
                 and p["has_ns"] == "True" 
                 and p["has_odb"] == "True"]

print(f"Found {len(full_coverage)} pairs with 5/5 coverage")

# Deduplicate by parent ingredient
print("Deduplicating by ingredient...")
selected = []
seen_parents = set()
l2_counts = defaultdict(int)

for p in sorted(full_coverage, key=lambda x: (x["atc_l2"], x["parent_name"])):
    parent = p["parent_rxcui"]
    l2 = p["atc_l2"]
    
    if parent in seen_parents:
        continue
        
    if l2_counts[l2] >= 5:
        continue
        
    selected.append(p)
    seen_parents.add(parent)
    l2_counts[l2] += 1

print(f"Selected {len(selected)} unique ingredients with full 5/5 coverage")
print(f"Across {len(l2_counts)} L2 categories")

# Write output
with open(OUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "rank", "atc_l1", "atc_l2", "atc_l2_name",
        "us_rxcui", "us_product_name", "parent_name", "atc_full",
        "nadac_usd", "costplus_usd", "bc_cad", "ns_cad", "odb_cad", "ca_dins"
    ])
    
    for i, p in enumerate(selected, 1):
        writer.writerow([
            i, p["atc_l1"], p["atc_l2"], p["atc_l2_name"],
            p["us_rxcui"], p["us_product_name"], p["parent_name"], p["atc_full"],
            p["nadac_unit_price_usd"], p["costplus_unit_price_usd"],
            p["bc_unit_price_cad"], p["ns_unit_price_cad"], p["odb_unit_price_cad"],
            p["ca_dins"],
        ])

# Display
print(f"\n{'='*80}")
print(f"STRICT 5/5 COVERAGE INDEX: {len(selected)} INGREDIENTS")
print(f"{'='*80}")
for i, p in enumerate(selected[:10], 1):
    print(f"{i:2}. {p['parent_name'][:30]:<30} | {p['atc_l2']} | NADAC:${float(p['nadac_unit_price_usd']):.2f} | BC:${float(p['bc_unit_price_cad']):.2f}")

print(f"\n... {len(selected)-10} more ingredients")
print(f"Output: {OUT}")
