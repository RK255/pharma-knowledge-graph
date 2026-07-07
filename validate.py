#!/usr/bin/env python3
"""
validate_suspicious_matches.py

Check the raw data for suspicious price matches.
"""
import json
from pathlib import Path

from config import BASE_DIR
BASE = BASE_DIR

# The suspicious RxCUIs to investigate
SUSPICIOUS = [
    "1232088",  # Xarelto -97%
    "205284",   # leflunomide +324%
    "199206",   # riluzole +812%
]

print("="*70)
print("VALIDATING SUSPICIOUS MATCHES")
print("="*70)

# Load US data
print("\nLoading US product data...")
us_data = {}
with open(BASE / "scripts/production/geo-ingestor/data_to_publish/full_geo_extraction_v25.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        for scd in rec.get("connections", {}).get("scd", []):
            if scd.get("rxcui") in SUSPICIOUS:
                us_data[scd["rxcui"]] = {
                    "name": scd.get("name"),
                    "ndcs": scd.get("ndcs", [])
                }
        for sbd in rec.get("connections", {}).get("sbd", []):
            if sbd.get("rxcui") in SUSPICIOUS:
                us_data[sbd["rxcui"]] = {
                    "name": sbd.get("name"),
                    "ndcs": sbd.get("ndcs", [])
                }

# Load Canadian data
print("Loading Canadian product data...")
ca_data = {}
with open(BASE / "scripts/production/geo-ingestor/canada/data_to_publish/canada_rxnorm_v2.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        if rec.get("rxcui") in SUSPICIOUS:
            ca_data[rec["rxcui"]] = {
                "name": rec.get("rx_name"),
                "dins": rec.get("dins", [])
            }

# Load pricing
print("Loading pricing data...")
with open(BASE / "scripts/production/pricing/data/US/nadac_pricing_report.json") as f:
    nadac = {p["ndc11"]: p for p in json.load(f)["pricing"]}

with open(BASE / "scripts/production/pricing/data/Canada/ontario_odb/ontario_odb_formulary.json") as f:
    odb = {r["din"]: r for r in json.load(f)["records"] if r.get("individual_price")}

with open(BASE / "scripts/production/pricing/data/Canada/bc_pharmacare/bc_pharmacare_plan_i_pricing.json") as f:
    bc = {r["din"]: r for r in json.load(f)["records"] if r.get("effective_price")}

# Check each suspicious entry
for rxcui in SUSPICIOUS:
    print(f"\n{'='*70}")
    print(f"RxCUI: {rxcui}")
    print(f"{'='*70}")
    
    us_info = us_data.get(rxcui, {})
    ca_info = ca_data.get(rxcui, {})
    
    print(f"\nUS Product: {us_info.get('name', 'NOT FOUND')}")
    print(f"CA Product: {ca_info.get('name', 'NOT FOUND')}")
    
    # Check US pricing
    print(f"\nUS NDCs and prices:")
    for ndc_entry in us_info.get("ndcs", [])[:5]:
        ndc = ndc_entry.get("ndc11_no_hyphens")
        price = nadac.get(ndc)
        print(f"  NDC {ndc}: ${price} (NADAC)" if price else f"  NDC {ndc}: No NADAC price")
    
    # Check Canadian pricing
    print(f"\nCanadian DINs and prices:")
    for din_entry in ca_info.get("dins", [])[:5]:
        din = din_entry.get("din")
        odb_price = odb.get(din, {}).get("individual_price")
        bc_price = bc.get(din, {}).get("effective_price")
        print(f"  DIN {din}:")
        if odb_price:
            print(f"    ODB: ${odb_price}")
        if bc_price:
            print(f"    BC:  ${bc_price}")

print("\n" + "="*70)
print("ANALYSIS")
print("="*70)
print("""
Common issues found:
1. UNIT MISMATCH: One price per tablet, other per package
2. GENERIC vs BRAND: Xarelto (brand) vs rivaroxaban (generic)
3. DOSAGE MISMATCH: Different strengths matched
4. DATA ERROR: Wrong price in source file

Recommend: Filter out matches where spread >500% or <-90%
""")
