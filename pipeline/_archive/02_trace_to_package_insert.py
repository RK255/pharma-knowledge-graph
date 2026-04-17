#!/usr/bin/env python3
"""
Trace IN (Ingredient) codes to PackageInserts via NDC bridge.

Path: PackageInsert → (maps_to_rxcui) → SCD/SBD → IN
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"

# Target IN codes
TARGET_INGREDIENTS = [
    "cetirizine",
    "ibuprofen",
    "gabapentin",
    "amoxicillin",
    "metformin",
    "lisinopril",
    "atorvastatin",
    "omeprazole",
    "metoprolol",
    "losartan",
    "pseudoephedrine",
    "semaglutide",
]

# Property IDs
NAME_PROP = "a126ca530c8e48d5b88882c734c38935"
TTY_PROP = "fd0c76eae47c55bbac4cca96203752c1"
RXCUI_PROP = "c6f36f8a8e22546ea7618ac008d2f91e"

# Relation type IDs (from schema)
REL = {
    "has_ingredient": "d085f236da3c51fca583c72e7058973b",
    "ingredient_of": "708910ff645b507ab5616dbd680b5802",
    "has_tradename": "a42836a8c04757e1a995531b8ff3200b",
    "tradename_of": "dbc766b554f0579da4c7b7c29924d6a3",
    "constitutes": "f5e289c3d13a5aaaa38b22448f7e38ab",
    "consists_of": "88c43b5be4eb5fe78b09872e9a9c3c70",
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
    print(f"Loading entities from {entities_file.name}...")
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
    print(f"Loading relations from {relations_file.name}...")
    with open(relations_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            from_id = r.get("from")
            to_id = r.get("to")
            rel_type = r.get("type")
            outgoing[from_id].append((to_id, rel_type))
            incoming[to_id].append((from_id, rel_type))
    print(f"  Loaded relations")
    return outgoing, incoming

def load_pi_links() -> tuple:
    """Load PackageInsert -> SCD/SBD links."""
    pi_to_drugs = defaultdict(list)  # PI ID -> list of drug IDs
    drug_to_pis = defaultdict(list)  # Drug ID -> list of PI IDs
    
    links_file = DATA_DIR / "dailymed_rxnorm_links_relations.jsonl"
    print(f"Loading PI links from {links_file.name}...")
    with open(links_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            pi_id = r.get("from")
            drug_id = r.get("to")
            if pi_id and drug_id:
                pi_to_drugs[pi_id].append(drug_id)
                drug_to_pis[drug_id].append(pi_id)
    
    print(f"  Loaded {len(pi_to_drugs):,} PackageInserts linked to {len(drug_to_pis):,} drugs")
    return pi_to_drugs, drug_to_pis

def find_in_entity(name: str, entities: dict) -> str:
    name_lower = name.lower()
    for eid, e in entities.items():
        if get_value(e, TTY_PROP) == "IN":
            entity_name = get_value(e, NAME_PROP)
            if entity_name and entity_name.lower() == name_lower:
                return eid
    return None

def get_neighbors(entity_id: str, rel_type: str, graph: dict) -> set:
    result = set()
    for target_id, rt in graph.get(entity_id, []):
        if rt == rel_type:
            result.add(target_id)
    return result

def trace_ingredient(in_name: str, entities: dict, outgoing: dict, incoming: dict, drug_to_pis: dict) -> dict:
    """Trace from IN to all connected entities including PackageInserts."""
    result = {
        "ingredient": in_name,
        "connected": {},
        "package_inserts": [],
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
    
    # === PATH 1: BN (Brand Names) ===
    bn_ids = get_neighbors(in_id, REL["has_tradename"], outgoing)
    result["connected"]["BN"] = [
        {"id": bid, "name": get_value(entities.get(bid, {}), NAME_PROP), "rxcui": get_value(entities.get(bid, {}), RXCUI_PROP)}
        for bid in bn_ids
    ]
    
    # === PATH 2: SCDC, SCDF, SCDG (direct from IN via ingredient_of) ===
    ingredient_targets = get_neighbors(in_id, REL["ingredient_of"], outgoing)
    scdc_ids = set()
    scdf_ids = set()
    scdg_ids = set()
    
    for tid in ingredient_targets:
        e = entities.get(tid, {})
        tty = get_value(e, TTY_PROP)
        if tty == "SCDC":
            scdc_ids.add(tid)
        elif tty == "SCDF":
            scdf_ids.add(tid)
        elif tty == "SCDG":
            scdg_ids.add(tid)
    
    result["connected"]["SCDC"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in scdc_ids
    ]
    result["connected"]["SCDF"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in scdf_ids
    ]
    result["connected"]["SCDG"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in scdg_ids
    ]
    
    # === PATH 3: SCD (via SCDC --constitutes--> SCD) ===
    scd_ids = set()
    for scdc_id in scdc_ids:
        targets = get_neighbors(scdc_id, REL["constitutes"], outgoing)
        for tid in targets:
            e = entities.get(tid, {})
            if get_value(e, TTY_PROP) == "SCD":
                scd_ids.add(tid)
    result["connected"]["SCD"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in scd_ids
    ]
    
    # === PATH 4: SBDC, SBDF, SBD (via BN --ingredient_of--> SBDC/SBDF/SBD) ===
    sbdc_ids = set()
    sbdf_ids = set()
    sbd_ids = set()
    
    for bn_id in bn_ids:
        targets = get_neighbors(bn_id, REL["ingredient_of"], outgoing)
        for tid in targets:
            e = entities.get(tid, {})
            tty = get_value(e, TTY_PROP)
            if tty == "SBDC":
                sbdc_ids.add(tid)
            elif tty == "SBDF":
                sbdf_ids.add(tid)
            elif tty == "SBD":
                sbd_ids.add(tid)
    
    # SBDC --constitutes--> SBD
    for sbdc_id in sbdc_ids:
        targets = get_neighbors(sbdc_id, REL["constitutes"], outgoing)
        for tid in targets:
            e = entities.get(tid, {})
            if get_value(e, TTY_PROP) == "SBD":
                sbd_ids.add(tid)
    
    result["connected"]["SBDC"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in sbdc_ids
    ]
    result["connected"]["SBDF"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in sbdf_ids
    ]
    result["connected"]["SBD"] = [
        {"id": i, "name": get_value(entities.get(i, {}), NAME_PROP), "rxcui": get_value(entities.get(i, {}), RXCUI_PROP)}
        for i in sbd_ids
    ]
    
    # === PATH 5: Find PackageInserts via dailymed_rxnorm_links ===
    # Collect all SCD and SBD IDs
    all_drug_ids = scd_ids | sbd_ids
    
    # Look up PackageInserts that link to these drugs
    package_inserts = []
    seen_pi_ids = set()
    
    for drug_id in all_drug_ids:
        pi_ids = drug_to_pis.get(drug_id, [])
        for pi_id in pi_ids:
            if pi_id not in seen_pi_ids:
                seen_pi_ids.add(pi_id)
                pi_entity = entities.get(pi_id, {})
                pi_name = get_value(pi_entity, NAME_PROP)
                drug_name = get_value(entities.get(drug_id, {}), NAME_PROP)
                drug_rxcui = get_value(entities.get(drug_id, {}), RXCUI_PROP)
                
                # Get FDA Set ID if available
                fda_set_id = None
                for v in pi_entity.get("values", []):
                    if v.get("property") == "78d0af3db973513e8be08b8b5c9e94a1":  # fda_set_id
                        fda_set_id = v.get("value")
                        break
                
                package_inserts.append({
                    "id": pi_id,
                    "name": pi_name,
                    "fda_set_id": fda_set_id,
                    "linked_drug": {
                        "id": drug_id,
                        "name": drug_name,
                        "rxcui": drug_rxcui
                    }
                })
    
    result["package_inserts"] = package_inserts[:20]  # Limit for readability
    
    # Summary stats
    result["stats"] = {
        "BN": len(bn_ids),
        "SCDC": len(scdc_ids),
        "SCDF": len(scdf_ids),
        "SCDG": len(scdg_ids),
        "SCD": len(scd_ids),
        "SBDC": len(sbdc_ids),
        "SBDF": len(sbdf_ids),
        "SBD": len(sbd_ids),
        "PackageInserts": len(package_inserts),
    }
    
    return result

def main():
    print("=" * 70)
    print("Trace IN → PackageInsert")
    print("=" * 70)
    
    entities = load_entities()
    outgoing, incoming = load_relations()
    pi_to_drugs, drug_to_pis = load_pi_links()
    
    # Trace each ingredient
    results = {}
    for in_name in TARGET_INGREDIENTS:
        print(f"\nTracing: {in_name}")
        result = trace_ingredient(in_name, entities, outgoing, incoming, drug_to_pis)
        results[in_name] = result
        
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            stats = result.get("stats", {})
            print(f"  IN RxCUI: {result.get('in_rxcui')}")
            print(f"  BN: {stats.get('BN', 0)}, SCD: {stats.get('SCD', 0)}, SBD: {stats.get('SBD', 0)}")
            print(f"  PackageInserts: {stats.get('PackageInserts', 0)}")
    
    # Save results
    output_file = DATA_DIR / "in_to_package_insert_trace.json"
    with open(output_file, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "results": results
        }, f, indent=2, default=str)
    print(f"\n✅ Results saved to {output_file}")

if __name__ == "__main__":
    main()
