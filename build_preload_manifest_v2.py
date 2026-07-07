#!/usr/bin/env python3
"""
build_preload_manifest_v2.py

Create JSON manifest for the 299 drugs with complete coverage (all 4 pricing sources).
Preload all static data; dashboard only queries API for manufacturer properties.
"""
import json
import csv
from pathlib import Path
from collections import defaultdict

from config import BASE_DIR
BASE = BASE_DIR

# Output paths
OUT_MANIFEST = BASE / "data/raw_data/dashboard_preload_manifest_v2.json"
OUT_CSV = BASE / "data/raw_data/complete_coverage_299.csv"

print("="*60)
print("Building preload manifest for 299 drugs with all 4 sources")
print("="*60)

# Step 1: Load the 299 matches we just found
print("\nLoading 299 matches...")
matches = []
with open(BASE / "data/raw_data/complete_coverage_drugs.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        matches.append({
            'rxcui': row['rxcui'],
            'drug_name': row['drug_name'],
            'tty': row['tty']
        })

print(f"Loaded {len(matches)} drugs")

# Step 2: Load US product details (SCD/SBD with NDCs)
print("\nLoading US product details...")
us_products = {}
with open(BASE / "scripts/production/geo-ingestor/data_to_publish/full_geo_extraction_v25.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        # Extract SCDs
        for scd in rec.get("connections", {}).get("scd", []):
            rxcui = scd.get("rxcui")
            if rxcui and rxcui in [m['rxcui'] for m in matches]:
                us_products[rxcui] = {
                    "name": scd.get("name"),
                    "tty": scd.get("tty"),
                    "ndcs": [ndc["ndc11_no_hyphens"] for ndc in scd.get("ndcs", []) if ndc.get("ndc11_no_hyphens")],
                    "ingredient_rxcui": rec.get("rxcui"),
                    "ingredient_name": rec.get("name")
                }
        # Extract SBDs
        for sbd in rec.get("connections", {}).get("sbd", []):
            rxcui = sbd.get("rxcui")
            if rxcui and rxcui in [m['rxcui'] for m in matches]:
                us_products[rxcui] = {
                    "name": sbd.get("name"),
                    "tty": sbd.get("tty"),
                    "ndcs": [ndc["ndc11_no_hyphens"] for ndc in sbd.get("ndcs", []) if ndc.get("ndc11_no_hyphens")],
                    "ingredient_rxcui": rec.get("rxcui"),
                    "ingredient_name": rec.get("name")
                }

print(f"Found US details for {len(us_products)} matches")

# Step 3: Load Canadian product details
print("\nLoading Canadian product details...")
ca_products = {}
with open(BASE / "scripts/production/geo-ingestor/canada/data_to_publish/canada_rxnorm_v2.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        rxcui = rec.get("rxcui")
        if rxcui and rxcui in [m['rxcui'] for m in matches]:
            ca_products[rxcui] = {
                "name": rec.get("rx_name"),
                "dins": [d["din"] for d in rec.get("dins", [])],
                "related_rxcui": rec.get("related_rxcui"),
                "atc": rec.get("atc_code", "")
            }

print(f"Found CA details for {len(ca_products)} matches")

# Step 4: Load pricing data
print("\nLoading pricing data...")
with open(BASE / "scripts/production/pricing/data/US/nadac_pricing_report.json") as f:
    nadac_by_ndc = {p["ndc11"]: p["unit_price"] for p in json.load(f)["pricing"]}

with open(BASE / "scripts/production/pricing/data/Canada/bc_pharmacare/bc_pharmacare_plan_i_pricing.json") as f:
    bc_by_din = {r["din"]: r["effective_price"] for r in json.load(f)["records"] if r.get("effective_price")}

with open(BASE / "scripts/production/pricing/data/Canada/nova_scotia_data/nova_scotia_pharmacare.json") as f:
    ns_by_din = {r["din"]: r["effective_price"] for r in json.load(f)["records"] if r.get("effective_price")}

with open(BASE / "scripts/production/pricing/data/Canada/ontario_odb/ontario_odb_formulary.json") as f:
    odb_by_din = {r["din"]: r["individual_price"] for r in json.load(f)["records"] if r.get("individual_price")}

# Step 5: Build comprehensive manifest
print("\nBuilding manifest...")
manifest = {
    "version": "2026-06-07-v2",
    "total_drugs": len(matches),
    "description": "Drugs with pricing from all 4 sources: NADAC, BC, NS, ODB",
    "drugs": [],
    "metadata": {
        "nadac_source": "Medicaid NADAC",
        "bc_source": "BC PharmaCare Plan I",
        "ns_source": "Nova Scotia Pharmacare",
        "odb_source": "Ontario Drug Benefit",
        "cad_to_usd_rate": 0.73
    }
}

complete_records = []

for i, match in enumerate(matches, 1):
    rxcui = match['rxcui']
    
    us_info = us_products.get(rxcui, {})
    ca_info = ca_products.get(rxcui, {})
    
    if not us_info or not ca_info:
        continue
    
    # Calculate best prices
    us_prices = [nadac_by_ndc.get(ndc) for ndc in us_info.get("ndcs", []) if ndc in nadac_by_ndc]
    ca_bc = [bc_by_din.get(din) for din in ca_info.get("dins", []) if din in bc_by_din]
    ca_ns = [ns_by_din.get(din) for din in ca_info.get("dins", []) if din in ns_by_din]
    ca_odb = [odb_by_din.get(din) for din in ca_info.get("dins", []) if din in odb_by_din]
    
    if not us_prices or not ca_bc or not ca_ns or not ca_odb:
        continue
    
    us_best = min(us_prices)
    ca_best = min(min(ca_bc), min(ca_ns), min(ca_odb))
    ca_best_usd = ca_best * 0.73
    spread = ((ca_best_usd - us_best) / us_best) * 100
    
    drug_entry = {
        "rank": i,
        "rxcui": rxcui,
        "name": match['drug_name'],
        "tty": match['tty'],
        "us": {
            "product_name": us_info.get("name"),
            "ndcs": us_info.get("ndcs", [])[:10],  # Limit to first 10
            "ingredient_rxcui": us_info.get("ingredient_rxcui"),
            "ingredient_name": us_info.get("ingredient_name"),
            "nadac_price": round(us_best, 4)
        },
        "ca": {
            "product_name": ca_info.get("name"),
            "dins": ca_info.get("dins", [])[:10],
            "related_rxcui": ca_info.get("related_rxcui"),
            "atc": ca_info.get("atc", ""),
            "best_price_cad": round(ca_best, 4),
            "best_price_usd": round(ca_best_usd, 4),
            "bc_price": round(min(ca_bc), 4),
            "ns_price": round(min(ca_ns), 4),
            "odb_price": round(min(ca_odb), 4)
        },
        "spread_percent": round(spread, 1),
        "ca_cheaper": ca_best_usd < us_best
    }
    
    manifest["drugs"].append(drug_entry)
    
    complete_records.append({
        'rank': i,
        'rxcui': rxcui,
        'drug_name': match['drug_name'],
        'us_price': us_best,
        'ca_price_cad': ca_best,
        'ca_price_usd': ca_best_usd,
        'spread_pct': spread
    })

# Save manifest
with open(OUT_MANIFEST, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"\n✅ Manifest saved: {OUT_MANIFEST}")
print(f"   Total drugs: {len(manifest['drugs'])}")

# Save CSV for easy reference
if complete_records:
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=['rank', 'rxcui', 'drug_name', 'us_price', 'ca_price_cad', 'ca_price_usd', 'spread_pct'])
        writer.writeheader()
        writer.writerows(complete_records)
    print(f"   CSV saved: {OUT_CSV}")

# Summary stats
ca_cheaper = sum(1 for d in manifest["drugs"] if d["ca_cheaper"])
print(f"\nSummary:")
print(f"  Canada cheaper: {ca_cheaper}/{len(manifest['drugs'])} ({ca_cheaper/len(manifest['drugs'])*100:.1f}%)")
print(f"  US cheaper: {len(manifest['drugs'])-ca_cheaper}/{len(manifest['drugs'])} ({(len(manifest['drugs'])-ca_cheaper)/len(manifest['drugs'])*100:.1f}%)")

print("\n" + "="*60)
print("Sample entries from manifest:")
print("="*60)
for drug in manifest["drugs"][:3]:
    print(f"\n{drug['rank']}. {drug['name']}")
    print(f"   RxCUI: {drug['rxcui']}")
    print(f"   US: ${drug['us']['nadac_price']} (NADAC)")
    print(f"   CA: ${drug['ca']['best_price_usd']} USD / ${drug['ca']['best_price_cad']} CAD (best of BC/NS/ODB)")
    print(f"   Spread: {drug['spread_percent']:+.1f}%")
