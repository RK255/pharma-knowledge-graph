#!/usr/bin/env python3
"""
Step 12: IN Code Connectivity Report
=====================================
Generates a JSON report for specified IN (Ingredient) codes showing all
connected entities via proper RxNorm relationship paths, plus PubChem properties.

Paths:
- BN:   IN --has_tradename--> BN
- SCDG: IN --ingredient_of--> SCDG (direct)
- SCD:  IN --ingredient_of--> SCDC --constitutes--> SCD
- SBD:  IN --has_tradename--> BN --ingredient_of--> SBDC --constitutes--> SBD
        IN --has_tradename--> BN --ingredient_of--> SBD (direct)
- PIN:  Found by name matching (no direct relation to IN)
- MIN:  Found by name matching (no direct relation to IN)
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Set, Optional

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

# PubChem property IDs
PUBCHEM_PROPS = {
    "pubchem_cid": "bdd863e095365bbea65deae8ebf1e81b",
    "smiles": "56e99a1b93b2573689e2f6a6c662df10",
    "inchikey": "6b432fc791ad5358b1f17fdc6abcfacc",
    "iupac_name": "5fbf742a110d508abc9af6a1cd1e49e7",
    "molecular_formula": "142b832ceb175b31a9becc432f8fb568",
    "molecular_weight": "20aba01a611d57e1bb02ca665dd61acd",
    "pubchem_date": "71641beff75757c896e1e0f276c59dc8",
}

# Relation type IDs
REL = {
    "has_ingredient": "d085f236da3c51fca583c72e7058973b",
    "ingredient_of": "708910ff645b507ab5616dbd680b5802",
    "has_tradename": "a42836a8c04757e1a995531b8ff3200b",
    "tradename_of": "dbc766b554f0579da4c7b7c29924d6a3",
    "constitutes": "f5e289c3d13a5aaaa38b22448f7e38ab",
    "consists_of": "88c43b5be4eb5fe78b09872e9a9c3c70",
    "has_precise_ingredient": "307907247a3c5be682ed242bb61a2947",
    "precise_ingredient_of": "9147c85a51ea5a2481824d2aefe5956d",
    "has_ingredients": "73f2d9bc321054dc80888064f36282fb",
    "ingredients_of": "f44019f93b2258119d1022c4f39b9da5",
}

RXNORM_REL_IDS = set(REL.values())


def get_value(entity: dict, prop_id: str) -> Optional[str]:
    for v in entity.get("values", []):
        if v.get("property") == prop_id:
            return v.get("value")
    return None


def get_all_values(entity: dict, prop_id: str) -> List[str]:
    """Get all values for a property (some may have multiple)."""
    values = []
    for v in entity.get("values", []):
        if v.get("property") == prop_id:
            val = v.get("value")
            if val:
                values.append(val)
    return values


def get_pubchem_data(entity: dict) -> dict:
    """Extract PubChem properties from an entity."""
    data = {}
    for prop_name, prop_id in PUBCHEM_PROPS.items():
        value = get_value(entity, prop_id)
        if value:
            data[prop_name] = value
    return data


def load_entities() -> Dict[str, dict]:
    entities = {}
    entities_file = DATA_DIR / "grc20_merged_entities.jsonl"
    print(f"Loading entities from {entities_file}...")
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
    print(f"Loading relations from {relations_file}...")
    with open(relations_file, 'r') as f:
        for line in f:
            r = json.loads(line)
            if r.get("type") in RXNORM_REL_IDS:
                from_id = r.get("from")
                to_id = r.get("to")
                rel_type = r.get("type")
                outgoing[from_id].append((to_id, rel_type))
                incoming[to_id].append((from_id, rel_type))
    print(f"  Loaded RxNorm relations (outgoing + incoming)")
    return outgoing, incoming


def find_in_entity(name: str, entities: dict) -> Optional[str]:
    name_lower = name.lower()
    for eid, e in entities.items():
        if get_value(e, TTY_PROP) == "IN":
            entity_name = get_value(e, NAME_PROP)
            if entity_name and entity_name.lower() == name_lower:
                return eid
    return None


def find_pin_min_by_name(in_name: str, entities: dict) -> tuple:
    """Find PIN and MIN entities whose name contains the IN name."""
    in_lower = in_name.lower()
    pins = []
    mins = []
    
    for eid, e in entities.items():
        tty = get_value(e, TTY_PROP)
        name = get_value(e, NAME_PROP)
        rxcui = get_value(e, RXCUI_PROP)
        
        if not name:
            continue
            
        name_lower = name.lower()
        
        # For PIN/MIN, the IN name should be at the start of the name
        if tty == "PIN" and name_lower.startswith(in_lower):
            item = {"id": eid, "name": name}
            if rxcui:
                item["rxcui"] = rxcui
            pins.append(item)
        elif tty == "MIN" and in_lower in name_lower:
            item = {"id": eid, "name": name}
            if rxcui:
                item["rxcui"] = rxcui
            mins.append(item)
    
    return sorted(pins, key=lambda x: x["name"]), sorted(mins, key=lambda x: x["name"])


def get_neighbors_out(entity_id: str, rel_type: str, outgoing: dict) -> Set[str]:
    """Get neighbors connected by outgoing relation."""
    result = set()
    for target_id, rt in outgoing.get(entity_id, []):
        if rt == rel_type:
            result.add(target_id)
    return result


def generate_report(ingredients: List[str], entities: dict, outgoing: dict, incoming: dict) -> dict:
    report = {
        "generated_at": datetime.now().isoformat(),
        "ingredients": {}
    }
    
    for in_name in ingredients:
        print(f"\nProcessing: {in_name}")
        
        # Find IN entity
        in_id = find_in_entity(in_name, entities)
        if not in_id:
            print(f"  ⚠️  Not found")
            report["ingredients"][in_name] = {"error": "Not found"}
            continue
        
        in_entity = entities[in_id]
        in_display = get_value(in_entity, NAME_PROP)
        rxcui = get_value(in_entity, RXCUI_PROP)
        print(f"  Found: {in_display} (RxCUI: {rxcui})")
        
        # Get PubChem data
        pubchem_data = get_pubchem_data(in_entity)
        if pubchem_data:
            print(f"  PubChem: CID={pubchem_data.get('pubchem_cid', 'N/A')}")
        
        # Initialize result
        result = {
            "id": in_id,
            "name": in_display,
            "rxcui": rxcui,
            "tty": "IN",
            "pubchem": pubchem_data if pubchem_data else None,
            "connected": {
                "BN": [],
                "PIN": [],
                "MIN": [],
                "SCDC": [],
                "SCDF": [],
                "SCDG": [],
                "SCD": [],
                "SBDC": [],
                "SBDF": [],
                "SBDG": [],
                "SBD": [],
            },
            "counts": {}
        }
        
        # Helper to collect entities by TTY
        def collect(entity_ids: Set[str], tty_list: List[str]):
            collected = defaultdict(list)
            for eid in entity_ids:
                e = entities.get(eid, {})
                tty = get_value(e, TTY_PROP)
                name = get_value(e, NAME_PROP)
                rxcui = get_value(e, RXCUI_PROP)
                if tty in tty_list and name:
                    item = {"id": eid, "name": name}
                    if rxcui:
                        item["rxcui"] = rxcui
                    collected[tty].append(item)
            return collected
        
        # === PATH 1: BN ===
        bn_ids = get_neighbors_out(in_id, REL["has_tradename"], outgoing)
        bn_entities = collect(bn_ids, ["BN"])
        result["connected"]["BN"] = bn_entities.get("BN", [])
        
        # === PATH 2: SCDC, SCDF, SCDG (direct from IN via ingredient_of) ===
        ingredient_targets = get_neighbors_out(in_id, REL["ingredient_of"], outgoing)
        ingredient_entities = collect(ingredient_targets, ["SCDC", "SCDF", "SCDG"])
        for tty in ["SCDC", "SCDF", "SCDG"]:
            result["connected"][tty] = ingredient_entities.get(tty, [])
        
        # === PATH 3: SCD ===
        scdc_ids = {e["id"] for e in result["connected"]["SCDC"]}
        for scdc_id in scdc_ids:
            targets = get_neighbors_out(scdc_id, REL["constitutes"], outgoing)
            for tid in targets:
                e = entities.get(tid, {})
                if get_value(e, TTY_PROP) == "SCD":
                    name = get_value(e, NAME_PROP)
                    if name:
                        result["connected"]["SCD"].append({"id": tid, "name": name})
        
        # Remove duplicates from SCD
        seen = set()
        unique = []
        for item in result["connected"]["SCD"]:
            if item["id"] not in seen:
                seen.add(item["id"])
                unique.append(item)
        result["connected"]["SCD"] = sorted(unique, key=lambda x: x["name"])
        
        # === PATH 4: SBDC, SBDF, SBD ===
        sbdc_ids = set()
        for bn in result["connected"]["BN"]:
            bn_id = bn["id"]
            targets = get_neighbors_out(bn_id, REL["ingredient_of"], outgoing)
            for tid in targets:
                e = entities.get(tid, {})
                tty = get_value(e, TTY_PROP)
                name = get_value(e, NAME_PROP)
                if name:
                    rxcui = get_value(e, RXCUI_PROP)
                    item = {"id": tid, "name": name}
                    if rxcui:
                        item["rxcui"] = rxcui
                    if tty == "SBDC":
                        sbdc_ids.add(tid)
                        result["connected"]["SBDC"].append(item)
                    elif tty == "SBDF":
                        result["connected"]["SBDF"].append(item)
                    elif tty == "SBD":
                        result["connected"]["SBD"].append(item)
        
        # SBDC --constitutes--> SBD
        sbd_ids = {e["id"] for e in result["connected"]["SBD"]}
        for sbdc_id in sbdc_ids:
            targets = get_neighbors_out(sbdc_id, REL["constitutes"], outgoing)
            for tid in targets:
                e = entities.get(tid, {})
                if get_value(e, TTY_PROP) == "SBD":
                    name = get_value(e, NAME_PROP)
                    if name and tid not in sbd_ids:
                        result["connected"]["SBD"].append({"id": tid, "name": name})
        
        # Remove duplicates from SBD, SBDC, SBDF
        for tty in ["SBD", "SBDC", "SBDF"]:
            seen = set()
            unique = []
            for item in result["connected"][tty]:
                if item["id"] not in seen:
                    seen.add(item["id"])
                    unique.append(item)
            result["connected"][tty] = sorted(unique, key=lambda x: x["name"])
        
        # === PATH 5: PIN, MIN (by name matching) ===
        pins, mins = find_pin_min_by_name(in_name, entities)
        result["connected"]["PIN"] = pins
        result["connected"]["MIN"] = mins
        
        # Calculate counts
        for tty, items in result["connected"].items():
            result["counts"][tty] = len(items)
        
        report["ingredients"][in_name] = result
        
        # Print summary
        print(f"    BN:   {result['counts']['BN']}")
        print(f"    SCDG: {result['counts']['SCDG']}")
        print(f"    SCD:  {result['counts']['SCD']}")
        print(f"    SBD:  {result['counts']['SBD']}")
        print(f"    PIN:  {result['counts']['PIN']}")
        print(f"    MIN:  {result['counts']['MIN']}")
    
    return report


def main():
    print("=" * 60)
    print("Step 12: IN Code Connectivity Report")
    print("=" * 60)
    
    entities = load_entities()
    outgoing, incoming = load_relations()
    report = generate_report(TARGET_INGREDIENTS, entities, outgoing, incoming)
    
    # Save JSON report
    output_file = DATA_DIR / "in_code_connectivity_report.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n✅ Report saved to {output_file}")
    
    # Print summary table
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Ingredient':<15} {'RxCUI':>8} {'PubChem':>8} {'BN':>5} {'SCDG':>5} {'SCD':>5} {'SBD':>5} {'PIN':>5} {'MIN':>5}")
    print("-" * 85)
    for in_name, data in report["ingredients"].items():
        if "error" not in data:
            counts = data["counts"]
            rxcui = data.get("rxcui", "N/A")
            has_pubchem = "Yes" if data.get("pubchem") else "No"
            print(f"{in_name:<15} {rxcui:>8} {has_pubchem:>8} {counts.get('BN', 0):>5} {counts.get('SCDG', 0):>5} {counts.get('SCD', 0):>5} {counts.get('SBD', 0):>5} {counts.get('PIN', 0):>5} {counts.get('MIN', 0):>5}")


if __name__ == "__main__":
    main()
