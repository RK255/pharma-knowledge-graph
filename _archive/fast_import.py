#!/usr/bin/env python3
import json
import csv
import os
from pathlib import Path

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent 
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
JSON_FILE = DATA_DIR / "grc20_with_relations.json"
OUTPUT_DIR = DATA_DIR / "neo4j_import"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Reading {JSON_FILE}...")
if not JSON_FILE.exists():
    print(f"ERROR: File not found at {JSON_FILE}")
    exit(1)

with open(JSON_FILE, 'r') as f:
    data = json.load(f)

if isinstance(data, list):
    entities = data
else:
    entities = data.get("entities", [])

print(f"Found {len(entities)} entities.")

# --- 1. NODES CSV ---
nodes_file = OUTPUT_DIR / "nodes.csv"
nodes_out = open(nodes_file, 'w', newline='')
nodes_writer = csv.writer(nodes_out)
nodes_writer.writerow(["id:ID", "name", "type", "provenance"])

print("Writing Nodes...")
node_count = 0
NAME_ID = "LuBWqZAu6pz54eiJS5mLv8"
PROV_ID = "LA1DqP5v6QAdsgLPXGF3YA"
TYPE_ID = "Jfmby78N4BCseZinBmdVov"
RELATION_SYS_ID = "QtC4Ay8HNLwSd1kSARgcDE"

for ent in entities:
    eid = ent.get("entity")
    triples = ent.get("triples", [])
    
    name = ""
    p_type = ""
    prov = ""
    
    for t in triples:
        attr = t.get("attribute")
        val = t.get("value", {}).get("value", "")
        
        if attr == NAME_ID: name = str(val)
        if attr == PROV_ID: prov = str(val)
        # Capture the specific Type ID to verify it exists
        if attr == TYPE_ID: p_type = str(val)
    
    # Write every entity as a node
    nodes_writer.writerow([eid, name, p_type, prov])
    node_count += 1
    if node_count % 100000 == 0:
        print(f"  Processed {node_count} nodes...")

nodes_out.close()
print(f"✅ Nodes written: {node_count}")

# --- 2. RELATIONSHIPS CSV ---
rels_file = OUTPUT_DIR / "relationships.csv"
rels_out = open(rels_file, 'w', newline='')
rels_writer = csv.writer(rels_out)
rels_writer.writerow([":START_ID", ":END_ID", ":TYPE"])

print("Writing Relationships...")
rel_count = 0

FROM_ID = "RERshk4JoYoMC17r1qAo9J"
TO_ID = "Qx8dASiTNsxxP3rJbd4Lzd"

for ent in entities:
    from_id = None
    to_id = None
    rel_type_id = None
    
    for t in ent.get("triples", []):
        attr = t.get("attribute")
        val = t.get("value", {}).get("value")
        
        if attr == TYPE_ID and val != RELATION_SYS_ID:
            rel_type_id = str(val)
        
        if attr == FROM_ID: from_id = str(val)
        if attr == TO_ID: to_id = str(val)
    
    # Write any entity that has a FROM and TO as a relationship
    if from_id and to_id:
        label = rel_type_id or "RELATED_TO"
        rels_writer.writerow([from_id, to_id, label])
        rel_count += 1
        if rel_count % 100000 == 0:
            print(f"  Processed {rel_count} relations...")

rels_out.close()
print(f"✅ Relationships written: {rel_count}")
print(f"\nCSVs ready in: {OUTPUT_DIR}")
