#!/usr/bin/env python3
"""
GRC-20 NDC Tether Export - SMART EQUIVALENCE
=============================================
Creates GRC-20 compliant data with intelligent equivalence relationships.

EQUIVALENCE STRATEGY:
- RxNorm NDCs are "hubs" (authoritative)
- Non-RxNorm NDCs link TO the nearest RxNorm hub
- This prevents relationship explosion while maintaining queryability

CREATED: 2026-02-22
"""

import json
import os
import uuid
import base58
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Optional

# =============================================================================
# GRC-20 SPECIFICATION
# =============================================================================

GRC20_SPEC = {
    "value_types": {"TEXT": 1, "NUMBER": 2, "CHECKBOX": 3, "URL": 4, "TIME": 5, "POINT": 6},
    "standard_attributes": {
        "name": "LuBWqZAu6pz54eiJS5mLv8",
        "type": "Jfmby78N4BCseZinBmdVov",
        "description": "LA1DqP5v6QAdsgLPXGF3YA",
    },
    "standard_types": {"type": "Jfmby78N4BCseZinBmdVov"}
}

ATTRIBUTES = {
    "name": "LuBWqZAu6pz54eiJS5mLv8",
    "type": "Jfmby78N4BCseZinBmdVov", 
    "description": "LA1DqP5v6QAdsgLPXGF3YA",
    "fda_set_id": "CzNrWVPayq5EB1HXncQFD5",
    "ndc_code": "NdcCode1234567890AB",
    "manufacturer": "Manufacturer12345678EF",
    "is_rxnorm": "IsRxNorm1234567890GH",
    "rxcui": "RxCui12345678901234IJ",
    "equivalence_key": "EquivKey1234567890OP",
    "has_ndc": "HasNdc12345678901234UV",
    "equivalent_to": "EquivalentTo12345678YZ",
    "linked_via": "LinkedVia1234567890MN",
}

ENTITY_TYPES = {}

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
OUTPUT_DIR = f"{BASE_DIR}/scripts/development/output"
DATA_DIR = f"{BASE_DIR}/data/raw_data"


def generate_grc20_id() -> str:
    return base58.b58encode(uuid.uuid4().bytes).decode()[:22].ljust(22, '1')[:22]


def create_triple(entity_id: str, attr_name: str, value: Any, value_type: str = "TEXT") -> dict:
    attr_id = ATTRIBUTES.get(attr_name, generate_grc20_id())
    if isinstance(value, bool):
        value_type = "CHECKBOX"
        value = str(value).lower()
    elif isinstance(value, list):
        value = json.dumps(value)
    return {"entity": entity_id, "attribute": attr_id, "value": {"type": GRC20_SPEC["value_types"].get(value_type, 1), "value": str(value)}}


def create_relation(entity_id: str, attr_name: str, target_id: str) -> dict:
    return {"entity": entity_id, "attribute": ATTRIBUTES.get(attr_name, generate_grc20_id()), "value": {"type": 1, "value": target_id}}


def normalize_ndc(ndc: str) -> Optional[str]:
    if not ndc:
        return None
    clean = ndc.replace('-', '').replace(' ', '')
    if len(clean) == 11:
        return clean
    elif len(clean) == 10:
        return clean + '0'
    elif len(clean) < 10:
        return clean.zfill(11)
    return clean[:11]


def print_progress(current: int, total: int, msg: str = "Processing"):
    pct = float(current) * 100 / total if total > 0 else 0
    bar_len = 50
    filled = int(pct / 100 * bar_len)
    sys.stdout.write(f'\r{msg}: [{"█" * filled}{"░" * (bar_len - filled)}] {pct:.1f}% ({current:,}/{total:,})')
    sys.stdout.flush()


def convert_to_grc20():
    print("=" * 80)
    print("GRC-20 NDC TETHER EXPORT")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # -------------------------------------------------------------------------
    # STEP 1: Load data
    # -------------------------------------------------------------------------
    print("\n[1/7] Loading data sources...")
    
    with open(f"{OUTPUT_DIR}/product_info_full.json", 'r') as f:
        products = json.load(f).get('products', [])
    print(f"  ✅ Loaded {len(products):,} products")
    
    with open(f"{DATA_DIR}/ndc_to_rxcui.json", 'r') as f:
        ndc_rxcui_raw = json.load(f)
    ndc_to_rxcui = {}
    for ndc, rxcui in ndc_rxcui_raw.get('ndc_to_rxcui', {}).items():
        normalized = normalize_ndc(ndc)
        if normalized:
            ndc_to_rxcui[normalized] = rxcui
    print(f"  ✅ Loaded {len(ndc_to_rxcui):,} NDC→RxCUI mappings")
    
    with open(f"{OUTPUT_DIR}/equivalence_links.json", 'r') as f:
        equivalence_groups = json.load(f).get('equivalence_links', [])
    print(f"  ✅ Loaded {len(equivalence_groups):,} equivalence groups")
    
    # -------------------------------------------------------------------------
    # STEP 2: Build equivalence index (SMART APPROACH)
    # -------------------------------------------------------------------------
    print("\n[2/7] Building equivalence index...")
    
    # For each equivalence group, find RxNorm NDCs to use as hubs
    equivalence_hubs = {}  # non_rxnorm_ndc -> rxnorm_ndc (hub)
    hub_stats = {'groups_with_hub': 0, 'groups_without_hub': 0, 'total_hubs': 0, 'total_spokes': 0}
    
    for group in equivalence_groups:
        all_ndcs = []
        for item in group.get('all_ndcs', []):
            if isinstance(item, dict):
                ndc = normalize_ndc(item.get('ndc', ''))
            else:
                ndc = normalize_ndc(str(item))
            if ndc:
                all_ndcs.append(ndc)
        
        # Find RxNorm NDCs in this group (these become hubs)
        rxnorm_ndcs = [ndc for ndc in all_ndcs if ndc in ndc_to_rxcui]
        non_rxnorm_ndcs = [ndc for ndc in all_ndcs if ndc not in ndc_to_rxcui]
        
        if rxnorm_ndcs:
            # Use the first RxNorm NDC as the hub
            hub = rxnorm_ndcs[0]
            hub_stats['groups_with_hub'] += 1
            hub_stats['total_hubs'] += 1
            
            # Link all non-RxNorm NDCs to this hub
            for ndc in non_rxnorm_ndcs:
                if ndc not in equivalence_hubs:
                    equivalence_hubs[ndc] = hub
                    hub_stats['total_spokes'] += 1
        else:
            hub_stats['groups_without_hub'] += 1
    
    print(f"  ✅ Equivalence hubs: {hub_stats['total_hubs']:,}")
    print(f"     Spokes linked to hubs: {hub_stats['total_spokes']:,}")
    print(f"     Groups with RxNorm hub: {hub_stats['groups_with_hub']:,}")
    print(f"     Groups without hub: {hub_stats['groups_without_hub']:,}")
    
    # -------------------------------------------------------------------------
    # STEP 3: Create type entities
    # -------------------------------------------------------------------------
    print("\n[3/7] Creating type entities...")
    
    entities = []
    entity_index = {}
    
    # PackageInsert type
    pi_type_id = generate_grc20_id()
    ENTITY_TYPES['package_insert'] = pi_type_id
    entities.append({"space": "pharmaceutical_ndc", "entity": pi_type_id, "triples": [
        create_triple(pi_type_id, "name", "PackageInsert"),
        create_triple(pi_type_id, "type", GRC20_SPEC["standard_types"]["type"]),
    ]})
    
    # NDC type
    ndc_type_id = generate_grc20_id()
    ENTITY_TYPES['ndc'] = ndc_type_id
    entities.append({"space": "pharmaceutical_ndc", "entity": ndc_type_id, "triples": [
        create_triple(ndc_type_id, "name", "NDC"),
        create_triple(ndc_type_id, "type", GRC20_SPEC["standard_types"]["type"]),
    ]})
    
    # Drug type
    drug_type_id = generate_grc20_id()
    ENTITY_TYPES['drug'] = drug_type_id
    entities.append({"space": "pharmaceutical_ndc", "entity": drug_type_id, "triples": [
        create_triple(drug_type_id, "name", "Drug"),
        create_triple(drug_type_id, "type", GRC20_SPEC["standard_types"]["type"]),
    ]})
    
    print(f"  ✅ Created 3 type entities")
    
    # -------------------------------------------------------------------------
    # STEP 4: Build NDC index
    # -------------------------------------------------------------------------
    print("\n[4/7] Building NDC index...")
    
    ndc_info = {}
    for product in products:
        manufacturer = product.get('manufacturer', '')
        for ndc in product.get('ndc_codes', []):
            normalized = normalize_ndc(ndc)
            if not normalized:
                continue
            if normalized not in ndc_info:
                ndc_info[normalized] = {
                    'is_rxnorm': normalized in ndc_to_rxcui,
                    'rxcui': ndc_to_rxcui.get(normalized),
                    'manufacturers': set(),
                    'equivalence_hub': equivalence_hubs.get(normalized),
                }
            ndc_info[normalized]['manufacturers'].add(manufacturer)
    
    rxnorm_count = sum(1 for n in ndc_info.values() if n['is_rxnorm'])
    spoke_count = sum(1 for n in ndc_info.values() if n.get('equivalence_hub'))
    print(f"  ✅ Indexed {len(ndc_info):,} unique NDCs")
    print(f"     RxNorm-linked: {rxnorm_count:,}")
    print(f"     Equivalence spokes: {spoke_count:,}")
    
    # -------------------------------------------------------------------------
    # STEP 5: Create entities
    # -------------------------------------------------------------------------
    print("\n[5/7] Creating GRC-20 entities...")
    
    ndc_to_entity = {}
    for i, (ndc, info) in enumerate(ndc_info.items()):
        entity_id = generate_grc20_id()
        ndc_to_entity[ndc] = entity_id
        entity_index[entity_id] = len(entities)
        
        triples = [
            create_triple(entity_id, "name", ndc),
            create_triple(entity_id, "type", ENTITY_TYPES['ndc']),
            create_triple(entity_id, "ndc_code", ndc),
            create_triple(entity_id, "is_rxnorm", info['is_rxnorm']),
        ]
        if info.get('rxcui'):
            triples.append(create_triple(entity_id, "rxcui", info['rxcui']))
        if info.get('manufacturers'):
            triples.append(create_triple(entity_id, "manufacturer", list(info['manufacturers'])[0]))
        
        entities.append({"space": "pharmaceutical_ndc", "entity": entity_id, "triples": triples})
        
        if (i + 1) % 50000 == 0:
            print_progress(i + 1, len(ndc_info), "  NDC entities")
    
    print_progress(len(ndc_info), len(ndc_info), "  NDC entities")
    print(f"\n  ✅ Created {len(ndc_info):,} NDC entities")
    
    # PackageInsert entities
    pi_to_entity = {}
    ndc_to_pi = {}
    
    for i, product in enumerate(products):
        set_id = product.get('set_id')
        if not set_id:
            continue
        
        entity_id = generate_grc20_id()
        pi_to_entity[set_id] = entity_id
        entity_index[entity_id] = len(entities)
        
        triples = [
            create_triple(entity_id, "name", product.get('product_name', 'Unknown')),
            create_triple(entity_id, "type", ENTITY_TYPES['package_insert']),
        ]
        if set_id:
            triples.append(create_triple(entity_id, "fda_set_id", set_id))
        if product.get('manufacturer'):
            triples.append(create_triple(entity_id, "manufacturer", product['manufacturer']))
        
        for ndc in product.get('ndc_codes', []):
            normalized = normalize_ndc(ndc)
            if normalized:
                ndc_to_pi[normalized] = set_id
        
        entities.append({"space": "pharmaceutical_ndc", "entity": entity_id, "triples": triples})
        
        if (i + 1) % 10000 == 0:
            print_progress(i + 1, len(products), "  PackageInsert entities")
    
    print_progress(len(products), len(products), "  PackageInsert entities")
    print(f"\n  ✅ Created {len(pi_to_entity):,} PackageInsert entities")
    
    # -------------------------------------------------------------------------
    # STEP 6: Create relationships
    # -------------------------------------------------------------------------
    print("\n[6/7] Creating relationships...")
    
    has_ndc_count = 0
    equiv_count = 0
    
    # has_ndc relationships
    print("  Creating has_ndc relationships...")
    for i, (ndc, set_id) in enumerate(ndc_to_pi.items()):
        if set_id in pi_to_entity and ndc in ndc_to_entity:
            pi_entity_id = pi_to_entity[set_id]
            rel = create_relation(pi_entity_id, "has_ndc", ndc_to_entity[ndc])
            idx = entity_index.get(pi_entity_id)
            if idx is not None:
                entities[idx]['triples'].append(rel)
                has_ndc_count += 1
        
        if (i + 1) % 50000 == 0:
            print_progress(i + 1, len(ndc_to_pi), "    has_ndc")
    
    print_progress(len(ndc_to_pi), len(ndc_to_pi), "    has_ndc")
    print(f"\n    ✅ Created {has_ndc_count:,} has_ndc relationships")
    
    # equivalent_to relationships (hub-spoke model)
    print("  Creating equivalent_to relationships (hub-spoke)...")
    for i, (spoke_ndc, hub_ndc) in enumerate(equivalence_hubs.items()):
        if spoke_ndc in ndc_to_entity and hub_ndc in ndc_to_entity:
            spoke_entity = ndc_to_entity[spoke_ndc]
            hub_entity = ndc_to_entity[hub_ndc]
            
            # Link spoke to hub
            rel = create_relation(spoke_entity, "equivalent_to", hub_entity)
            idx = entity_index.get(spoke_entity)
            if idx is not None:
                entities[idx]['triples'].append(rel)
                equiv_count += 1
        
        if (i + 1) % 10000 == 0:
            print_progress(i + 1, len(equivalence_hubs), "    equivalent_to")
    
    print_progress(len(equivalence_hubs), len(equivalence_hubs), "    equivalent_to")
    print(f"\n    ✅ Created {equiv_count:,} equivalent_to relationships")
    
    # -------------------------------------------------------------------------
    # STEP 7: Export
    # -------------------------------------------------------------------------
    print("\n[7/7] Exporting...")
    
    output = {
        "metadata": {
            "created": datetime.now().isoformat(),
            "source": "FDA SPL + RxNorm",
            "entity_types": ENTITY_TYPES,
            "equivalence_strategy": "hub-spoke",
            "stats": {
                "total_entities": len(entities),
                "ndc_entities": len(ndc_info),
                "package_insert_entities": len(pi_to_entity),
                "has_ndc_relationships": has_ndc_count,
                "equivalent_to_relationships": equiv_count,
                "rxnorm_coverage": rxnorm_count,
                "equivalence_hubs": hub_stats['total_hubs'],
                "equivalence_spokes": hub_stats['total_spokes'],
            }
        },
        "entities": entities
    }
    
    output_file = f"{OUTPUT_DIR}/grc20_ndc_tether_data.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"  📁 Saved to {output_file}")
    print(f"     Size: {os.path.getsize(output_file) / 1024 / 1024:.1f} MB")
    
    # Summary file
    summary_file = f"{OUTPUT_DIR}/grc20_ndc_tether_summary.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "created": datetime.now().isoformat(),
            "stats": output['metadata']['stats'],
            "entity_types": ENTITY_TYPES,
            "sample_ndc_entity": entities[3] if len(entities) > 3 else None,
            "sample_package_insert_entity": entities[-1] if entities else None,
        }, f, indent=2)
    print(f"  📁 Summary: {summary_file}")
    
    print("\n" + "=" * 80)
    print("CONVERSION COMPLETE")
    print("=" * 80)
    stats = output['metadata']['stats']
    print(f"Entities: {stats['total_entities']:,}")
    print(f"  • NDC: {stats['ndc_entities']:,}")
    print(f"  • PackageInsert: {stats['package_insert_entities']:,}")
    print(f"  • RxNorm-linked: {stats['rxnorm_coverage']:,}")
    print()
    print(f"Equivalence (Hub-Spoke Model):")
    print(f"  • Hubs (RxNorm NDCs): {stats['equivalence_hubs']:,}")
    print(f"  • Spokes linked to hubs: {stats['equivalence_spokes']:,}")
    print()
    print(f"Relationships:")
    print(f"  • has_ndc: {stats['has_ndc_relationships']:,}")
    print(f"  • equivalent_to: {stats['equivalent_to_relationships']:,}")
    print("=" * 80)
    
    return output


if __name__ == "__main__":
    convert_to_grc20()
