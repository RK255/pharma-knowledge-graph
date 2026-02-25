#!/usr/bin/env python3
"""
Clean Sequential Relationship Loader
====================================

No deadlocks. Just works.

CREATED: 2026-02-22
"""

import json
import time
from collections import defaultdict
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"
DATA_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs"

REL_ATTRS = {
    "HasNdc12345678901234UV": "HAS_NDC",
    "EquivalentTo12345678YZ": "EQUIVALENT_TO",
    "MapsToRxcui12345678WX": "MAPS_TO_RXCUI",
    "HasIngredient123456MN": "HAS_INGREDIENT",
    "HasDoseForm12345678OP": "HAS_DOSE_FORM",
    "HasBrand1234567890QR": "HAS_BRAND",
    "IsA1234567890123456AB": "ISA",
    "InverseIsa12345678CD": "INVERSE_ISA",
    "constitutes": "CONSTITUTES",
    "consists_of": "CONSISTS_OF",
    "has_tradename": "HAS_TRADENAME",
    "tradename_of": "TRADENAME_OF",
    "ingredient_of": "INGREDIENT_OF",
}


def main():
    print("=" * 70)
    print("SEQUENTIAL RELATIONSHIP LOADER")
    print("=" * 70)
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    total_start = time.time()
    
    try:
        # Check current state
        print("\n[1/5] Current state:")
        with driver.session() as s:
            nodes = list(s.run("MATCH (n) RETURN count(n) as c"))[0]['c']
            rels = list(s.run("MATCH ()-[r]->() RETURN count(r) as c"))[0]['c']
            print(f"  Nodes: {nodes:,}")
            print(f"  Relationships: {rels:,}")
        
        # Build entity_id -> internal_id mapping
        print("\n[2/5] Building ID mapping...")
        start = time.time()
        entity_map = {}
        with driver.session() as s:
            result = s.run("MATCH (n) WHERE n.entity_id IS NOT NULL RETURN n.entity_id AS eid, id(n) AS nid")
            for r in result:
                entity_map[r['eid']] = r['nid']
        print(f"  {len(entity_map):,} entities mapped in {time.time()-start:.1f}s")
        
        # Build RxCUI -> entity_id mapping for cross-links
        print("\n[3/5] Building RxCUI mapping...")
        start = time.time()
        rxcui_to_entity = {}
        with driver.session() as s:
            result = s.run("MATCH (n:RxNormConcept) WHERE n.rxcui IS NOT NULL RETURN n.rxcui AS rxcui, n.entity_id AS eid")
            for r in result:
                rxcui_to_entity[r['rxcui']] = r['eid']
        print(f"  {len(rxcui_to_entity):,} RxCUIs mapped in {time.time()-start:.1f}s")
        
        # Parse all relationships from GRC-20 files
        print("\n[4/5] Parsing relationships from files...")
        start = time.time()
        all_rels = []
        ndc_rxcui_pairs = []  # For cross-links
        
        for fname in ["grc20_rxnorm_data.json", "grc20_ndc_tether_data.json"]:
            fpath = f"{DATA_DIR}/{fname}"
            print(f"  Parsing {fname}...")
            
            with open(fpath) as f:
                data = json.load(f)
            
            file_rels = 0
            for entity in data.get("entities", []):
                eid = entity["entity"]
                is_ndc = False
                rxcui = None
                
                for triple in entity.get("triples", []):
                    attr = triple.get("attribute", "")
                    val = triple.get("value", {}).get("value", "")
                    
                    # Check for relationship
                    rel_type = REL_ATTRS.get(attr)
                    if rel_type and val:
                        all_rels.append({"from": eid, "to": val, "type": rel_type})
                        file_rels += 1
                    
                    # Track NDC entities with RxCUI for cross-links
                    if attr == "Jfmby78N4BCseZinBmdVov8" and val == "92foNtgvw8o7s6GRgk8kCQ":
                        is_ndc = True
                    if attr == "RxCui12345678901234IJ":
                        rxcui = val
                
                if is_ndc and rxcui:
                    ndc_rxcui_pairs.append((eid, rxcui))
            
            print(f"    {file_rels:,} relationships")
        
        print(f"  Total relationships: {len(all_rels):,}")
        print(f"  NDC-RxCUI pairs for cross-links: {len(ndc_rxcui_pairs):,}")
        print(f"  Parse time: {time.time()-start:.1f}s")
        
        # Load relationships sequentially
        print("\n[5/5] Loading relationships...")
        start = time.time()
        
        # Filter valid relationships
        valid_rels = []
        for r in all_rels:
            from_id = entity_map.get(r["from"])
            to_id = entity_map.get(r["to"])
            if from_id is not None and to_id is not None:
                valid_rels.append({
                    "from_id": from_id,
                    "to_id": to_id,
                    "type": r["type"]
                })
        
        print(f"  Valid relationships: {len(valid_rels):,}")
        
        # Group by type
        by_type = defaultdict(list)
        for r in valid_rels:
            by_type[r["type"]].append(r)
        
        print(f"  Relationship types: {len(by_type)}")
        for t, rels in sorted(by_type.items(), key=lambda x: -len(x[1])):
            print(f"    {t}: {len(rels):,}")
        
        # Load each type sequentially
        total_created = 0
        with driver.session() as s:
            for rel_type in sorted(by_type.keys()):
                rels = by_type[rel_type]
                safe_type = rel_type.upper().replace("-", "_")
                
                print(f"\n  Loading {rel_type}...")
                type_start = time.time()
                
                for i in range(0, len(rels), 5000):
                    batch = rels[i:i+5000]
                    query = f"""
                    UNWIND $batch AS rel
                    MATCH (from) WHERE id(from) = rel.from_id
                    MATCH (to) WHERE id(to) = rel.to_id
                    MERGE (from)-[r:{safe_type}]->(to)
                    """
                    s.run(query, batch=batch).consume()
                    total_created += len(batch)
                
                type_elapsed = time.time() - type_start
                print(f"    {len(rels):,} in {type_elapsed:.1f}s ({len(rels)/type_elapsed:.0f}/sec)")
        
        rel_time = time.time() - start
        print(f"\n  Relationships loaded: {total_created:,} in {rel_time:.1f}s")
        
        # Load cross-links (NDC → RxNormConcept)
        print("\n  Loading NDC → RxNormConcept cross-links...")
        cross_start = time.time()
        
        cross_links = []
        for ndc_eid, rxcui in ndc_rxcui_pairs:
            rxnorm_eid = rxcui_to_entity.get(rxcui)
            if rxnorm_eid:
                ndc_internal = entity_map.get(ndc_eid)
                rxnorm_internal = entity_map.get(rxnorm_eid)
                if ndc_internal is not None and rxnorm_internal is not None:
                    cross_links.append({"from_id": ndc_internal, "to_id": rxnorm_internal})
        
        print(f"    Valid cross-links: {len(cross_links):,}")
        
        cross_created = 0
        with driver.session() as s:
            for i in range(0, len(cross_links), 5000):
                batch = cross_links[i:i+5000]
                query = """
                UNWIND $batch AS rel
                MATCH (from) WHERE id(from) = rel.from_id
                MATCH (to) WHERE id(to) = rel.to_id
                MERGE (from)-[:MAPS_TO_RXCUI]->(to)
                """
                s.run(query, batch=batch).consume()
                cross_created += len(batch)
        
        cross_time = time.time() - cross_start
        print(f"    {cross_created:,} cross-links in {cross_time:.1f}s ({cross_created/cross_time:.0f}/sec)")
        
        # Final verification
        print("\n" + "=" * 70)
        print("FINAL VERIFICATION")
        print("=" * 70)
        
        with driver.session() as s:
            print("\nNodes by label:")
            result = s.run("MATCH (n) RETURN labels(n)[0] as l, count(n) as c ORDER BY c DESC")
            for r in result:
                print(f"  {r['l']}: {r['c']:,}")
            
            print("\nRelationships by type:")
            result = s.run("MATCH ()-[r]->() RETURN type(r) as t, count(r) as c ORDER BY c DESC")
            total_rels = 0
            for r in result:
                print(f"  {r['t']}: {r['c']:,}")
                total_rels += r['c']
            
            print("\nSample queries:")
            
            # Tamsulosin
            result = s.run("""
                MATCH (r:RxNormConcept) WHERE r.name CONTAINS 'Tamsulosin'
                OPTIONAL MATCH (r)-[rel]-(other)
                RETURN r.name as name, r.rxcui as rxcui, labels(r) as labels, 
                       count(DISTINCT rel) as connections LIMIT 1
            """)
            for r in result:
                print(f"  Tamsulosin: {r['name']} (RxCUI: {r['rxcui']}, connections: {r['connections']})")
            
            # NDC → RxNorm link
            result = s.run("""
                MATCH (n:NDC)-[:MAPS_TO_RXCUI]->(r:RxNormConcept)
                RETURN n.ndc_code as ndc, r.name as drug, r.rxcui as rxcui LIMIT 3
            """)
            print("  NDC → RxNorm links:")
            for r in result:
                print(f"    {r['ndc']} → {r['drug']} (RxCUI: {r['rxcui']})")
            
            # PackageInsert → NDC
            result = s.run("""
                MATCH (p:PackageInsert)-[:HAS_NDC]->(n:NDC)
                RETURN p.name as name, n.ndc_code as ndc LIMIT 3
            """)
            print("  PackageInsert → NDC:")
            for r in result:
                name = (r['name'][:50] + '...') if r['name'] and len(r['name']) > 50 else r['name']
                print(f"    {name} → {r['ndc']}")
        
        total_elapsed = time.time() - total_start
        print("\n" + "=" * 70)
        print(f"COMPLETE in {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
        print(f"Total relationships: {total_rels:,}")
        print("=" * 70)
        
    finally:
        driver.close()


if __name__ == "__main__":
    main()
