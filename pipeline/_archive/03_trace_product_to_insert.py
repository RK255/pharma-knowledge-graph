#!/usr/bin/env python3
"""
Trace drug products (SCD/SBD) to their NDCs and PackageInserts.

Shows the complete chain: IN → SCD/SBD → NDCs → PackageInserts
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"

# Property IDs
NAME_PROP = "a126ca530c8e48d5b88882c734c38935"
TTY_PROP = "fd0c76eae47c55bbac4cca96203752c1"
RXCUI_PROP = "c6f36f8a8e22546ea7618ac008d2f91e"
NDC_PROP = "694ec99a6c8e555caba8d8bb72f302c8"  # NDC code property
FDA_SET_ID_PROP = "78d0af3db973513e8be08b8b5c9e94a1"  # fda_set_id

# Relation type IDs
REL = {
    "has_ingredient": "d085f236da3c51fca583c72e7058973b",
    "ingredient_of": "708910ff645b507ab5616dbd680b5802",
    "has_tradename": "a42836a8c04757e1a995531b8ff3200b",
    "constitutes": "f5e289c3d13a5aaaa38b22448f7e38ab",
    "maps_to_rxcui": "4e096f6ad94b5fff833908d03cbf6a9d",
}

def get_value(entity: dict, prop_id: str) -> str:
    for v in entity.get("values", []):
        if v.get("property") == prop_id:
            return v.get("value", "")
    return ""

def load_entities() -> dict:
    entities = {}
    entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
    print(f"Loading entities...")
    with open(entities_file, 'r') as f:
        for line in f:
            e = json.loads(line)
            entities[e["id"]] = e
    print(f"  Loaded {len(entities):,} entities")
    return entities

def load_relations() -> tuple:
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    relations_file = DATA_DIR / "grc20_merged_relations.jsonl"
    print(f"Loading relations...")
    with open(relations_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            from_id = r.get("from")
            to_id = r.get("to")
            rel_type = r.get("type")
            outgoing[from_id].append((to_id, rel_type))
            incoming[to_id].append((from_id, rel_type))
    return outgoing, incoming

def load_ndc_bridge() -> dict:
    """Load NDC → drug mappings."""
    ndc_to_drugs = defaultdict(list)
    drug_to_ndcs = defaultdict(list)
    
    ndc_file = DATA_DIR / "ndc_bridge_relations.jsonl"
    print(f"Loading NDC bridge...")
    with open(ndc_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            ndc_id = r.get("from")
            drug_id = r.get("to")
            if ndc_id and drug_id:
                ndc_to_drugs[ndc_id].append(drug_id)
                drug_to_ndcs[drug_id].append(ndc_id)
    
    print(f"  {len(ndc_to_drugs):,} NDCs linked to {len(drug_to_ndcs):,} drugs")
    return ndc_to_drugs, drug_to_ndcs

def load_pi_links() -> tuple:
    """Load PackageInsert → drug mappings."""
    pi_to_drugs = defaultdict(list)
    drug_to_pis = defaultdict(list)
    
    links_file = DATA_DIR / "dailymed_rxnorm_links_relations.jsonl"
    print(f"Loading PI links...")
    with open(links_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            pi_id = r.get("from")
            drug_id = r.get("to")
            if pi_id and drug_id:
                pi_to_drugs[pi_id].append(drug_id)
                drug_to_pis[drug_id].append(pi_id)
    
    print(f"  {len(pi_to_drugs):,} PIs linked to {len(drug_to_pis):,} drugs")
    return pi_to_drugs, drug_to_pis

def get_neighbors(entity_id: str, rel_type: str, graph: dict) -> set:
    result = set()
    for target_id, rt in graph.get(entity_id, []):
        if rt == rel_type:
            result.add(target_id)
    return result

def find_in_entity(name: str, entities: dict) -> str:
    name_lower = name.lower()
    for eid, e in entities.items():
        if get_value(e, TTY_PROP) == "IN":
            entity_name = get_value(e, NAME_PROP)
            if entity_name and entity_name.lower() == name_lower:
                return eid
    return None

def trace_product_chain(in_name: str, entities: dict, outgoing: dict, incoming: dict, 
                        drug_to_ndcs: dict, drug_to_pis: dict, ndc_entities: dict) -> dict:
    """Trace from IN to SCD/SBD to NDCs to PackageInserts."""
    result = {
        "ingredient": in_name,
        "products": [],
        "stats": {}
    }
    
    # Find IN entity
    in_id = find_in_entity(in_name, entities)
    if not in_id:
        result["error"] = "IN not found"
        return result
    
    in_entity = entities[in_id]
    result["in_id"] = in_id
    result["in_rxcui"] = get_value(in_entity, RXCUI_PROP)
    result["in_name"] = get_value(in_entity, NAME_PROP)
    
    # Get BNs
    bn_ids = get_neighbors(in_id, REL["has_tradename"], outgoing)
    
    # Get SCDC/SCDF/SCDG from ingredient_of
    ingredient_targets = get_neighbors(in_id, REL["ingredient_of"], outgoing)
    scdc_ids = set()
    for tid in ingredient_targets:
        e = entities.get(tid, {})
        if get_value(e, TTY_PROP) == "SCDC":
            scdc_ids.add(tid)
    
    # Get SCDs from SCDCs
    scd_ids = set()
    for scdc_id in scdc_ids:
        targets = get_neighbors(scdc_id, REL["constitutes"], outgoing)
        for tid in targets:
            e = entities.get(tid, {})
            if get_value(e, TTY_PROP) == "SCD":
                scd_ids.add(tid)
    
    # Get SBDCs/SBDs from BNs
    sbdc_ids = set()
    sbd_ids = set()
    for bn_id in bn_ids:
        targets = get_neighbors(bn_id, REL["ingredient_of"], outgoing)
        for tid in targets:
            e = entities.get(tid, {})
            tty = get_value(e, TTY_PROP)
            if tty == "SBDC":
                sbdc_ids.add(tid)
            elif tty == "SBD":
                sbd_ids.add(tid)
    
    # Get SBDs from SBDCs
    for sbdc_id in sbdc_ids:
        targets = get_neighbors(sbdc_id, REL["constitutes"], outgoing)
        for tid in targets:
            e = entities.get(tid, {})
            if get_value(e, TTY_PROP) == "SBD":
                sbd_ids.add(tid)
    
    # Collect all products (SCDs and SBDs)
    all_products = []
    
    # Process SBDs (branded products)
    for sbd_id in sbd_ids:
        e = entities.get(sbd_id, {})
        product = {
            "id": sbd_id,
            "name": get_value(e, NAME_PROP),
            "rxcui": get_value(e, RXCUI_PROP),
            "tty": "SBD",
            "ndcs": [],
            "package_inserts": []
        }
        
        # Get NDCs for this SBD
        ndc_ids = drug_to_ndcs.get(sbd_id, [])
        for ndc_id in ndc_ids:
            ndc_e = entities.get(ndc_id, {})
            ndc_code = get_value(ndc_e, NAME_PROP)  # NDC code is stored as name
            product["ndcs"].append({
                "id": ndc_id,
                "ndc_code": ndc_code
            })
        
        # Get PackageInserts for this SBD
        pi_ids = drug_to_pis.get(sbd_id, [])
        for pi_id in pi_ids:
            pi_e = entities.get(pi_id, {})
            fda_set_id = get_value(pi_e, FDA_SET_ID_PROP)
            product["package_inserts"].append({
                "id": pi_id,
                "name": get_value(pi_e, NAME_PROP),
                "fda_set_id": fda_set_id
            })
        
        all_products.append(product)
    
    # Process SCDs (clinical drugs) - only if no SBDs
    # Actually, let's include all SCDs too
    for scd_id in scd_ids:
        e = entities.get(scd_id, {})
        product = {
            "id": scd_id,
            "name": get_value(e, NAME_PROP),
            "rxcui": get_value(e, RXCUI_PROP),
            "tty": "SCD",
            "ndcs": [],
            "package_inserts": []
        }
        
        # Get NDCs
        ndc_ids = drug_to_ndcs.get(scd_id, [])
        for ndc_id in ndc_ids:
            ndc_e = entities.get(ndc_id, {})
            ndc_code = get_value(ndc_e, NAME_PROP)
            product["ndcs"].append({
                "id": ndc_id,
                "ndc_code": ndc_code
            })
        
        # Get PackageInserts
        pi_ids = drug_to_pis.get(scd_id, [])
        for pi_id in pi_ids:
            pi_e = entities.get(pi_id, {})
            fda_set_id = get_value(pi_e, FDA_SET_ID_PROP)
            product["package_inserts"].append({
                "id": pi_id,
                "name": get_value(pi_e, NAME_PROP),
                "fda_set_id": fda_set_id
            })
        
        all_products.append(product)
    
    # Sort products: SBDs first, then by number of NDCs/PIs
    all_products.sort(key=lambda x: (
        0 if x["tty"] == "SBD" else 1,
        -(len(x["ndcs"]) + len(x["package_inserts"]))
    ))
    
    # Limit output
    result["products"] = all_products[:50]
    
    # Stats
    total_ndcs = sum(len(p["ndcs"]) for p in all_products)
    total_pis = sum(len(p["package_inserts"]) for p in all_products)
    products_with_ndcs = sum(1 for p in all_products if p["ndcs"])
    products_with_pis = sum(1 for p in all_products if p["package_inserts"])
    
    result["stats"] = {
        "total_scds": len(scd_ids),
        "total_sbds": len(sbd_ids),
        "total_products": len(all_products),
        "products_with_ndcs": products_with_ndcs,
        "products_with_pis": products_with_pis,
        "total_ndcs": total_ndcs,
        "total_package_inserts": total_pis,
    }
    
    return result

def main():
    print("=" * 70)
    print("Trace Product → NDC → PackageInsert")
    print("=" * 70)
    
    entities = load_entities()
    outgoing, incoming = load_relations()
    ndc_to_drugs, drug_to_ndcs = load_ndc_bridge()
    pi_to_drugs, drug_to_pis = load_pi_links()
    
    # Sample ingredients to trace
    ingredients = [
        "cetirizine",
        "ibuprofen",
        "gabapentin",
        "metformin",
        "semaglutide",
    ]
    
    results = {}
    for in_name in ingredients:
        print(f"\nTracing: {in_name}")
        result = trace_product_chain(in_name, entities, outgoing, incoming, 
                                     drug_to_ndcs, drug_to_pis, entities)
        results[in_name] = result
        
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            stats = result.get("stats", {})
            print(f"  SCDs: {stats.get('total_scds', 0)}, SBDs: {stats.get('total_sbds', 0)}")
            print(f"  Products with NDCs: {stats.get('products_with_ndcs', 0)}")
            print(f"  Products with PIs: {stats.get('products_with_pis', 0)}")
            print(f"  Total NDCs: {stats.get('total_ndcs', 0)}")
            print(f"  Total PackageInserts: {stats.get('total_package_inserts', 0)}")
            
            # Show sample products
            for p in result["products"][:3]:
                print(f"    {p['tty']}: {p['name'][:50]}...")
                print(f"      NDCs: {len(p['ndcs'])}, PIs: {len(p['package_inserts'])}")
                if p['ndcs']:
                    print(f"      Sample NDC: {p['ndcs'][0]['ndc_code']}")
                if p['package_inserts']:
                    print(f"      Sample PI: {p['package_inserts'][0]['name'][:40]}...")
    
    # Save results
    output_file = DATA_DIR / "product_to_insert_trace.json"
    with open(output_file, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "results": results
        }, f, indent=2, default=str)
    print(f"\n✅ Results saved to {output_file}")

if __name__ == "__main__":
    main()
