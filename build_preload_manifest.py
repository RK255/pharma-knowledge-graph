#!/usr/bin/env python3
"""
build_preload_manifest.py

Create a JSON manifest for the frontend dashboard.
"""
import json, csv
from pathlib import Path
from collections import defaultdict

from config import BASE_DIR
BASE = BASE_DIR / "data" / "raw_data"
PAIRS = BASE / "best_100_balanced.csv"
COVERAGE = BASE / "atc_pricing_coverage.csv"  # Has parent_rxcui
CA_PRODUCTS = BASE / "atc_ca_products.csv"
OUT = BASE / "dashboard_preload_manifest.json"

# Load parent_rxcui lookup from coverage
print("Loading parent_rxcui mappings...")
parent_lookup = {}
with open(COVERAGE) as f:
    for row in csv.DictReader(f):
        parent_lookup[row["us_rxcui"]] = {
            "parent_rxcui": row["parent_rxcui"],
            "parent_name": row["parent_name"]
        }

# Load CA product details
print("Loading CA product mappings...")
ca_products = {}
with open(CA_PRODUCTS) as f:
    for row in csv.DictReader(f):
        prxcui = row["product_rxcui"]
        if prxcui not in ca_products:
            ca_products[prxcui] = {
                "parent_rxcui": row["parent_rxcui"],
                "product_name": row["product_name"],
                "product_tty": row["product_tty"],
                "dins": [],
                "atc": {
                    "l1": row["atc_l1"],
                    "l2": row["atc_l2"],
                    "l2_name": row["atc_l2_name"],
                    "full": row["atc_full"]
                }
            }
        ca_products[prxcui]["dins"].append(row["din"])

# Build manifest
print("Building preload manifest...")
manifest = {
    "version": "2026-06-07",
    "total_pairs": 0,
    "pairs": [],
    "index_by_atc_l2": defaultdict(list)
}

with open(PAIRS) as f:
    reader = csv.DictReader(f)
    for row in reader:
        us_rxcui = row["us_rxcui"]
        
        # Get parent_rxcui from lookup
        lookup = parent_lookup.get(us_rxcui, {})
        parent_rxcui = lookup.get("parent_rxcui", "")
        
        if not parent_rxcui:
            print(f"  Warning: no parent_rxcui for {us_rxcui}")
            continue
            
        # Find CA products by parent_rxcui
        ca_matches = [
            {"ca_rxcui": k, **v} 
            for k, v in ca_products.items() 
            if v["parent_rxcui"] == parent_rxcui
        ]
        
        if not ca_matches:
            print(f"  Warning: no CA matches for parent {parent_rxcui}")
            continue
            
        pair_entry = {
            "rank": int(row["rank"]),
            "us": {
                "rxcui": us_rxcui,
                "name": row["us_product_name"],
                "parent_rxcui": parent_rxcui,
                "parent_name": row["parent_name"],
                "atc_full": row["atc_full"],
                "atc_l2": row["atc_l2"]
            },
            "ca": {
                "products": ca_matches,
                "dins_all": list(set(d for m in ca_matches for d in m["dins"]))
            },
            "pricing": {
                "us_min": float(row["us_price_min"]) if row["us_price_min"] else None,
                "us_max": float(row["us_price_max"]) if row["us_price_max"] else None,
                "ca_min": float(row["ca_price_min"]) if row["ca_price_min"] else None,
                "ca_max": float(row["ca_price_max"]) if row["ca_price_max"] else None,
                "sources": row["sources"]
            }
        }
        
        manifest["pairs"].append(pair_entry)
        manifest["index_by_atc_l2"][row["atc_l2"]].append(us_rxcui)
        manifest["total_pairs"] += 1

manifest["index_by_atc_l2"] = dict(manifest["index_by_atc_l2"])

with open(OUT, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"\nOutput: {OUT}")
print(f"Total pairs: {manifest['total_pairs']}")
print(f"ATC L2 categories: {len(manifest['index_by_atc_l2'])}")
