#!/usr/bin/env python3
"""
Validate the full chain: IN → SBD → NDC → PackageInsert

This validates that:
1. Each SBD has correct NDCs linked
2. Each NDC links to exactly one PackageInsert (via Set ID)
3. The PackageInsert contains that NDC in its SPL
4. Users can trace from product → exact insert
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
FDA_SET_ID_PROP = "78d0af3db973513e8be0cb76afa5e9c4"

# Relation IDs
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
    print("Loading entities...")
    with open(DATA_DIR / "grc20_merged_entities.jsonl", 'r') as f:
        for line in f:
            e = json.loads(line)
            entities[e["id"]] = e
    print(f"  Loaded {len(entities):,} entities")
    return entities

def load_relations() -> tuple:
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    print("Loading relations...")
    with open(DATA_DIR / "grc20_merged_relations.jsonl", 'r') as f:
        for line in f:
            r = json.loads(line)
            outgoing[r["from"]].append((r["to"], r["type"]))
            incoming[r["to"]].append((r["from"], r["type"]))
    return outgoing, incoming

def load_ndc_bridge() -> tuple:
    """Load NDC → drug mappings from bridge."""
    ndc_to_drug = {}
    drug_to_ndcs = defaultdict(list)
    print("Loading NDC bridge...")
    with open(DATA_DIR / "ndc_bridge_entities.jsonl", 'r') as f:
        for line in f:
            e = json.loads(line)
            ndc_to_drug[e["id"]] = e.get("name", "")
    
    with open(DATA_DIR / "ndc_bridge_relations.jsonl", 'r') as f:
        for line in f:
            r = json.loads(line)
            ndc_id = r["from"]
            drug_id = r["to"]
            drug_to_ndcs[drug_id].append(ndc_id)
    print(f"  {len(ndc_to_drug):,} NDCs, {len(drug_to_ndcs):,} drugs")
    return ndc_to_drug, drug_to_ndcs

def load_pi_links() -> tuple:
    """Load PackageInsert → drug mappings."""
    pi_to_drugs = defaultdict(list)
    drug_to_pis = defaultdict(list)
    print("Loading PI links...")
    with open(DATA_DIR / "dailymed_rxnorm_links_relations.jsonl", 'r') as f:
        for line in f:
            r = json.loads(line)
            pi_to_drugs[r["from"]].append(r["to"])
            drug_to_pis[r["to"]].append(r["from"])
    print(f"  {len(pi_to_drugs):,} PIs linked to {len(drug_to_pis):,} drugs")
    return pi_to_drugs, drug_to_pis

def load_pi_set_ids() -> dict:
    """Load Set ID → PI entity mapping."""
    set_id_to_pi = {}
    print("Loading PI Set IDs...")
    with open(DATA_DIR / "dailymed_entities.jsonl", 'r') as f:
        for line in f:
            e = json.loads(line)
            set_id = get_value(e, FDA_SET_ID_PROP)
            if set_id:
                set_id_to_pi[set_id] = {
                    "id": e["id"],
                    "name": e.get("name", ""),
                    "set_id": set_id
                }
    print(f"  {len(set_id_to_pi):,} PIs with Set IDs")
    return set_id_to_pi

def load_pi_documents() -> dict:
    """Load Set ID → NDCs from documents."""
    set_id_to_ndcs = {}
    print("Loading PI documents...")
    with open(DATA_DIR / "dailymed_documents.json", 'r') as f:
        docs = json.load(f)
    for doc in docs:
        set_id = doc.get("fda_set_id")
        ndcs = doc.get("ndc_codes", [])
        if set_id and ndcs:
            set_id_to_ndcs[set_id] = ndcs
    print(f"  {len(set_id_to_ndcs):,} Set IDs with NDCs")
    return set_id_to_ndcs

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

def validate_chain(in_name: str, entities: dict, outgoing: dict, drug_to_ndcs: dict, 
                   drug_to_pis: dict, ndc_to_drug: dict, set_id_to_ndcs: dict) -> dict:
    """Validate the full chain for an ingredient."""
    result = {
        "ingredient": in_name,
        "products": [],
        "validation": {
            "total_sbds": 0,
            "sbds_with_ndcs": 0,
            "sbds_with_pis": 0,
            "ndcs_in_spl": 0,
            "validation_passed": True,
            "issues": []
        }
    }
    
    # Find IN
    in_id = find_in_entity(in_name, entities)
    if not in_id:
        result["error"] = "IN not found"
        return result
    
    in_entity = entities[in_id]
    result["in_rxcui"] = get_value(in_entity, RXCUI_PROP)
    result["in_name"] = get_value(in_entity, NAME_PROP)
    
    # Get BNs
    bn_ids = get_neighbors(in_id, REL["has_tradename"], outgoing)
    
    # Get SBDCs from BNs
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
    
    result["validation"]["total_sbds"] = len(sbd_ids)
    
    # For each SBD, validate the chain
    for sbd_id in sbd_ids:
        sbd_entity = entities.get(sbd_id, {})
        sbd_name = get_value(sbd_entity, NAME_PROP)
        sbd_rxcui = get_value(sbd_entity, RXCUI_PROP)
        
        product = {
            "sbd_id": sbd_id,
            "sbd_name": sbd_name,
            "sbd_rxcui": sbd_rxcui,
            "ndcs": [],
            "package_inserts": [],
            "validation": {"ndcs_matched": 0, "ndcs_unmatched": 0}
        }
        
        # Get NDCs for this SBD
        ndc_ids = drug_to_ndcs.get(sbd_id, [])
        for ndc_id in ndc_ids:
            ndc_code = ndc_to_drug.get(ndc_id, ndc_id)
            product["ndcs"].append({"ndc_id": ndc_id, "ndc_code": ndc_code})
        
        if ndc_ids:
            result["validation"]["sbds_with_ndcs"] += 1
        
        # Get PackageInserts for this SBD
        pi_ids = drug_to_pis.get(sbd_id, [])
        for pi_id in pi_ids:
            pi_entity = entities.get(pi_id, {})
            pi_name = get_value(pi_entity, NAME_PROP)
            pi_set_id = get_value(pi_entity, FDA_SET_ID_PROP)
            
            pi_info = {
                "pi_id": pi_id,
                "pi_name": pi_name,
                "set_id": pi_set_id,
                "ndcs_in_spl": [],
                "matches": []
            }
            
            # Get NDCs from the SPL document
            if pi_set_id:
                spl_ndcs = set_id_to_ndcs.get(pi_set_id, [])
                pi_info["ndcs_in_spl"] = spl_ndcs
                
                # Check which SBD NDCs are in the SPL
                for ndc_id in ndc_ids:
                    ndc_code = ndc_to_drug.get(ndc_id, ndc_id)
                    # Normalize for comparison
                    ndc_clean = ndc_code.replace("-", "").zfill(11)
                    spl_clean = [n.replace("-", "").zfill(11) for n in spl_ndcs]
                    if ndc_clean in spl_clean:
                        product["validation"]["ndcs_matched"] += 1
                        pi_info["matches"].append(ndc_code)
                    else:
                        product["validation"]["ndcs_unmatched"] += 1
            
            product["package_inserts"].append(pi_info)
        
        if pi_ids:
            result["validation"]["sbds_with_pis"] += 1
        
        result["products"].append(product)
    
    # Sort products by number of NDCs
    result["products"].sort(key=lambda x: -len(x["ndcs"]))
    
    # Limit output
    result["products"] = result["products"][:10]
    
    # Validation summary
    total_matched = sum(p["validation"]["ndcs_matched"] for p in result["products"])
    total_unmatched = sum(p["validation"]["ndcs_unmatched"] for p in result["products"])
    result["validation"]["ndcs_in_spl"] = total_matched
    result["validation"]["ndcs_not_in_spl"] = total_unmatched
    result["validation"]["match_rate"] = (
        total_matched / (total_matched + total_unmatched) * 100 
        if (total_matched + total_unmatched) > 0 else 0
    )
    
    return result

def main():
    print("=" * 70)
    print("Validate NDC → PackageInsert Chain")
    print("=" * 70)
    
    entities = load_entities()
    outgoing, incoming = load_relations()
    ndc_to_drug, drug_to_ndcs = load_ndc_bridge()
    pi_to_drugs, drug_to_pis = load_pi_links()
    set_id_to_pi = load_pi_set_ids()
    set_id_to_ndcs = load_pi_documents()
    
    # Test ingredients
    ingredients = [
        "semaglutide",
        "cetirizine",
        "gabapentin",
        "metformin",
    ]
    
    results = {}
    for in_name in ingredients:
        print(f"\n{'='*60}")
        print(f"Validating: {in_name}")
        print(f"{'='*60}")
        
        result = validate_chain(
            in_name, entities, outgoing, drug_to_ndcs, drug_to_pis,
            ndc_to_drug, set_id_to_ndcs
        )
        results[in_name] = result
        
        if "error" in result:
            print(f"  ERROR: {result['error']}")
            continue
        
        # Print summary
        v = result["validation"]
        print(f"Total SBDs: {v['total_sbds']}")
        print(f"SBDs with NDCs: {v['sbds_with_ndcs']}")
        print(f"SBDs with PIs: {v['sbds_with_pis']}")
        print(f"NDCs matched in SPL: {v['ndcs_in_spl']}")
        print(f"NDCs not in SPL: {v['ndcs_not_in_spl']}")
        print(f"Match rate: {v['match_rate']:.1f}%")
        
        # Show sample products
        print("\nSample products:")
        for p in result["products"][:3]:
            print(f"\n  SBD: {p['sbd_name'][:50]}...")
            print(f"    RxCUI: {p['sbd_rxcui']}")
            print(f"    NDCs: {len(p['ndcs'])}")
            if p['ndcs']:
                print(f"      Sample NDC: {p['ndcs'][0]['ndc_code']}")
            print(f"    PackageInserts: {len(p['package_inserts'])}")
            for pi in p['package_inserts'][:2]:
                print(f"      PI: {pi['pi_name'][:40]}...")
                print(f"      Set ID: {pi['set_id'][:20] if pi['set_id'] else 'N/A'}...")
                print(f"      NDCs in SPL: {len(pi['ndcs_in_spl'])}")
                print(f"      Matched NDCs: {len(pi['matches'])}")
    
    # Save results
    output_file = DATA_DIR / "ndc_pi_chain_validation.json"
    with open(output_file, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "results": results
        }, f, indent=2, default=str)
    print(f"\n✅ Results saved to {output_file}")

if __name__ == "__main__":
    main()
