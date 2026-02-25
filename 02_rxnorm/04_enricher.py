#!/usr/bin/env python3
"""RxNorm Enricher v5 - Uses node IDs for O(1) lookup"""
import os
from collections import defaultdict
from neo4j import GraphDatabase

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RRF_DIR = f"{BASE_DIR}/data/raw_data/extracted_rrf/RxNorm12012025_extracted/rrf"

RELATIONSHIPS = {
    'has_tradename': 'HAS_TRADENAME',
    'has_ingredient': 'HAS_INGREDIENT_RXNORM',
    'has_part': 'HAS_PART',
    'has_precise_ingredient': 'HAS_PRECISE_INGREDIENT',
    'has_form': 'HAS_FORM',
    'has_boss': 'HAS_BOSS',
    'isa': 'IS_A',
    'has_ingredients': 'HAS_INGREDIENTS',
    'constitutes': 'CONSTITUTES',
    'contains': 'CONTAINS',
    'has_doseformgroup': 'HAS_DOSE_FORM_GROUP',
}

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "Nani*48301"))

print("RxNorm Enricher v5 - Node ID Lookup")
print("=" * 50)

# Step 1: Build rxcui -> node_id mapping (this is the key!)
print("\n[1/4] Building rxcui -> node_id map...")
rxcui_to_id = {}
with driver.session() as s:
    # Get all nodes with their internal IDs
    result = s.run("MATCH (n) WHERE n.rxcui IS NOT NULL RETURN n.rxcui as rxcui, id(n) as node_id")
    for r in result:
        rxcui = str(r["rxcui"]).strip()
        node_id = r["node_id"]
        # Store all node IDs for this rxcui (there may be multiple)
        if rxcui not in rxcui_to_id:
            rxcui_to_id[rxcui] = []
        rxcui_to_id[rxcui].append(node_id)
print(f"  {len(rxcui_to_id):,} unique RxCUIs mapped")

# Step 2: Parse RRF
print("\n[2/4] Parsing RXNREL.RRF...")
rel_file = os.path.join(RRF_DIR, "RXNREL.RRF")
raw_rels = defaultdict(list)
with open(rel_file, 'r', encoding='utf-8', errors='ignore') as f:
    for i, line in enumerate(f):
        parts = line.strip().split('|')
        if len(parts) >= 8:
            src, tgt, rel = parts[0].strip(), parts[4].strip(), parts[7].strip()
            if rel in RELATIONSHIPS:
                raw_rels[RELATIONSHIPS[rel]].append((src, tgt))
        if i % 500000 == 0 and i > 0:
            print(f"  {i:,} lines...", end='\r')
print(f"  Parsed {sum(len(v) for v in raw_rels.values()):,} raw relationships")

# Step 3: Convert rxcui pairs to node_id pairs
print("\n[3/4] Converting to node ID pairs...")
id_pairs = {}
for rel_type, pairs in raw_rels.items():
    id_list = []
    for src_rxcui, tgt_rxcui in pairs:
        if src_rxcui in rxcui_to_id and tgt_rxcui in rxcui_to_id:
            # Get first node ID for each (or could create multiple relationships)
            src_id = rxcui_to_id[src_rxcui][0]
            tgt_id = rxcui_to_id[tgt_rxcui][0]
            id_list.append((src_id, tgt_id))
    id_pairs[rel_type] = id_list
    print(f"  {rel_type}: {len(id_list):,}")

# Step 4: Import using node IDs (MUCH faster!)
print("\n[4/4] Importing...")
total_imported = 0

with driver.session() as session:
    for rel_type, pairs in id_pairs.items():
        if not pairs:
            continue
        
        print(f"\n  {rel_type}: {len(pairs):,}")
        
        batch_size = 5000
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i+batch_size]
            
            # Use START/END with node IDs - bypasses property lookup entirely
            query = f"""
            UNWIND $pairs AS pair
            MATCH (s) WHERE id(s) = pair[0]
            MATCH (t) WHERE id(t) = pair[1]
            CREATE (s)-[r:{rel_type} {{source: 'rxnorm_v5'}}]->(t)
            """
            
            session.run(query, pairs=batch).consume()
            
            total_imported += len(batch)
            done = min(i + batch_size, len(pairs))
            print(f"    {done:,}/{len(pairs):,}", end='\r')
        
        print(f"    ✅ Done")

# Report
print("\n" + "=" * 50)
with driver.session() as s:
    result = s.run("MATCH ()-[r]->() RETURN type(r) as t, count(*) as c ORDER BY c DESC")
    total = 0
    for r in result:
        print(f"  {r['t']}: {r['c']:,}")
        total += r['c']
    print(f"\nTotal: {total:,}")

driver.close()
print("\n✅ COMPLETE!")
