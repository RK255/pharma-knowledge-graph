#!/usr/bin/env python3
"""
populate_canadian_dins.py

Post-processing script that populates the `canadianDins` field in an existing
product-ndc-index.json WITHOUT re-scanning the GraphQL API.

Linkage chain:
  canadianProducts[productId].relatedRxcui
    → matches_v13.2.csv (rxcui → [dins])
    → canadian_enriched.csv (din → {name, type, brand, ...})

Output format for canadianDins:
  {
    "02040786": {
      "name": "clomipramine 10 mg Tablet 100",
      "type": "CGD",
      "relatedRxcui": "12345"
    },
    ...
  }

Also adds a `din` field to each canadianProducts entry so the DIN is available
alongside the hash key (as recommended in the audit report).
"""

import csv
import json
import sys
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

# ── Paths ────────────────────────────────────────────────────────────────────
from config import BASE_DIR
BASE = BASE_DIR / "scripts" / "production"
CANADA_DIR = BASE / "pricing/data/Canada"
INDEX_PATH = BASE / "pricing/frontend/geo_pharma_app/public/product-ndc-index.json"
ENRICHED_CSV = CANADA_DIR / "canadian_enriched.csv"
MATCHES_CSV = CANADA_DIR / "matches_v13.2.csv"


def load_enriched(path: Path) -> dict:
    """Load canadian_enriched.csv → {din: {name, type, brand, ...}}"""
    enriched = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            din = (row.get("din") or "").strip()
            if not din:
                continue
            enriched[din] = {
                "name": (row.get("canonical") or "").strip(),
                "type": (row.get("type") or "").strip(),
                "brand": (row.get("brand_name") or "").strip(),
                "company": (row.get("company") or "").strip(),
                "strength": (row.get("strength") or "").strip(),
                "dosage_form": (row.get("dosage_form") or "").strip(),
            }
    print(f"  Loaded {len(enriched):,} DINs from canadian_enriched.csv")
    return enriched


def load_matches(path: Path) -> tuple[dict, dict]:
    """Load matches_v13.2.csv → {rxcui: [din, din, ...]}"""
    rxcui_to_dins = defaultdict(list)
    din_to_rxcui = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            din = (row.get("din") or "").strip()
            rxcui = (row.get("rxcui") or "").strip()
            if not din or not rxcui:
                continue
            rxcui_to_dins[rxcui].append(din)
            if din not in din_to_rxcui:
                din_to_rxcui[din] = rxcui
    print(f"  Loaded {len(rxcui_to_dins):,} rxcui→DIN mappings from matches_v13.2.csv")
    print(f"  Loaded {len(din_to_rxcui):,} DIN→rxcui direct mappings")
    return dict(rxcui_to_dins), din_to_rxcui


def main():
    print("=" * 60)
    print("populate_canadian_dins.py")
    print("=" * 60)

    # 1. Load source data
    print("\n① Loading source data...")
    enriched = load_enriched(ENRICHED_CSV)
    rxcui_to_dins, din_to_rxcui = load_matches(MATCHES_CSV)

    # 2. Load existing index
    print(f"\n② Loading existing index: {INDEX_PATH}")
    with open(INDEX_PATH, encoding="utf-8") as f:
        index = json.load(f)

    can_prods = index.get("canadianProducts", {})
    existing_dins = index.get("canadianDins", {})
    print(f"  canadianProducts: {len(can_prods):,} entries")
    print(f"  canadianDins (BEFORE): {len(existing_dins)} entries (BUG: empty)")

    # 3. Build canadianDins
    #    Strategy:
    #    a) For each canadianProduct with relatedRxcui, look up DINs via matches
    #    b) For each DIN, get metadata from canadian_enriched.csv
    #    c) Also add any DINs from matches that aren't linked to a GraphQL product
    print("\n③ Building canadianDins...")

    canadian_dins = {}
    din_source_counts = {"from_product_rxcui": 0, "from_direct_match": 0, "from_enriched_only": 0}

    # 3a. Link canadianProducts → rxcui → DINs
    products_with_din_link = 0
    for prod_id, entry in can_prods.items():
        rxcui = entry.get("relatedRxcui")
        if not rxcui or rxcui == "null":
            continue
        dins = rxcui_to_dins.get(rxcui)
        if not dins:
            continue
        products_with_din_link += 1
        product_type = "CBD" if entry.get("type") == "CBD" else "CGD"
        for din in dins:
            if din in canadian_dins:
                continue
            enriched_entry = enriched.get(din)
            canadian_dins[din] = {
                "name": enriched_entry["name"] if enriched_entry else entry.get("name", ""),
                "type": product_type,
                "relatedRxcui": rxcui,
            }
            din_source_counts["from_product_rxcui"] += 1

    print(f"  {products_with_din_link:,} canadianProducts linked to DINs via rxcui")

    # 3b. Add DINs from matches that have no GraphQL product but DO have enriched data
    for din, rxcui in din_to_rxcui.items():
        if din in canadian_dins:
            continue
        enriched_entry = enriched.get(din)
        if not enriched_entry:
            continue
        can_type = enriched_entry.get("type", "")
        product_type = "CBD" if can_type.startswith("cSBD") else "CGD"
        canadian_dins[din] = {
            "name": enriched_entry["name"],
            "type": product_type,
            "relatedRxcui": rxcui,
        }
        din_source_counts["from_direct_match"] += 1

    # 3c. Add remaining DINs from canadian_enriched.csv that have no rxcui match
    #     (these have no US equivalent but are still valid Canadian DINs)
    for din, enriched_entry in enriched.items():
        if din in canadian_dins:
            continue
        can_type = enriched_entry.get("type", "")
        product_type = "CBD" if can_type.startswith("cSBD") else "CGD"
        canadian_dins[din] = {
            "name": enriched_entry["name"],
            "type": product_type,
            "relatedRxcui": None,
        }
        din_source_counts["from_enriched_only"] += 1

    print(f"  canadianDins populated: {len(canadian_dins):,} total")
    print(f"    from product rxcui:   {din_source_counts['from_product_rxcui']:,}")
    print(f"    from direct match:    {din_source_counts['from_direct_match']:,}")
    print(f"    from enriched only:   {din_source_counts['from_enriched_only']:,}")

    # 4. Add `din` field to each canadianProducts entry
    #    (recommended in audit report so DIN is available alongside hash key)
    print("\n④ Adding 'din' field to canadianProducts entries...")
    products_updated = 0
    for prod_id, entry in can_prods.items():
        rxcui = entry.get("relatedRxcui")
        if not rxcui or rxcui == "null":
            continue
        dins = rxcui_to_dins.get(rxcui)
        if dins:
            entry["dins"] = dins
            products_updated += 1
    print(f"  {products_updated:,} canadianProducts entries updated with 'dins' field")

    # 5. Update index
    index["canadianDins"] = canadian_dins
    index["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # 6. Backup original and write new index
    backup_path = INDEX_PATH.with_suffix(".json.bak")
    if not backup_path.exists():
        shutil.copy2(INDEX_PATH, backup_path)
        print(f"\n⑤ Backed up original to: {backup_path}")
    else:
        print(f"\n⑤ Backup already exists: {backup_path}")

    print(f"   Writing updated index to: {INDEX_PATH}")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    file_size_mb = INDEX_PATH.stat().st_size / (1024 * 1024)
    print(f"   File size: {file_size_mb:.2f} MB")

    # 7. Verification
    print("\n⑥ Verification:")
    with open(INDEX_PATH, encoding="utf-8") as f:
        verify = json.load(f)

    vd = verify.get("canadianDins", {})
    vp = verify.get("canadianProducts", {})
    print(f"  canadianDins count: {len(vd):,}")
    print(f"  canadianProducts count: {len(vp):,}")
    print(f"  productsWithDIN (declared): {verify.get('productsWithDIN'):,}")

    # Check that DINs are properly linked
    sample_dins = list(vd.keys())[:3]
    for din in sample_dins:
        entry = vd[din]
        print(f"  Sample DIN {din}: name='{entry['name'][:40]}', type={entry['type']}, rxcui={entry.get('relatedRxcui')}")

    # Cross-check: how many canadianProducts now have dins field
    with_dins_field = sum(1 for v in vp.values() if v.get("dins"))
    print(f"  canadianProducts with 'dins' field: {with_dins_field:,}")

    print("\n" + "=" * 60)
    print("✅ Done — canadianDins populated successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
