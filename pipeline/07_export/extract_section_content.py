#!/usr/bin/env python3
"""
Extract Package Insert Section Content
==================================================================================

Extracts the full text content of all package insert sections from the 
GRC-20 graph and saves them to a separate JSON file indexed by set_id.
"""

import json
from pathlib import Path
from collections import defaultdict
import sys

# Paths
BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
SCHEMA_CACHE = BASE_DIR / "scripts" / "production" / "pipeline" / "00_schema" / "schema_cache.json"
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
OUTPUT_DIR = BASE_DIR / "scripts" / "production" / "geo-ingestor" / "data_to_publish"

# Input files
ENTITIES_FILE = DATA_DIR / "grc20_merged_entities.jsonl"
RELATIONS_FILE = DATA_DIR / "grc20_merged_relations.jsonl"

# Output file
OUTPUT_FILE = OUTPUT_DIR / "sections_content.json"

# Load Schema Cache
print("Loading Schema Cache...")
with open(SCHEMA_CACHE, 'r') as f:
    schema_data = json.load(f)

# Build Lookups from Lists
TYPE_LOOKUP = {item['name']: item['id'] for item in schema_data.get('types', [])}
PROP_LOOKUP = {item['name']: item['id'] for item in schema_data.get('properties', [])}
REL_LOOKUP = {item['name']: item['id'] for item in schema_data.get('relations', [])}

# Get Required IDs
TYPE_PACKAGEINSERT_ID = TYPE_LOOKUP.get('PackageInsert')
TYPE_SECTION_ID = TYPE_LOOKUP.get('Section')
PROP_FDA_SET_ID = PROP_LOOKUP.get('fda_set_id')
PROP_CONTENT = PROP_LOOKUP.get('content') # Schema uses 'content', not 'text'
PROP_TITLE = PROP_LOOKUP.get('name')     # Schema uses 'name' as the primary title

print(f"  PackageInsert ID: {TYPE_PACKAGEINSERT_ID}")
print(f"  Section ID: {TYPE_SECTION_ID}")
print(f"  fda_set_id Prop ID: {PROP_FDA_SET_ID}")
print(f"  content Prop ID: {PROP_CONTENT}")

if not TYPE_PACKAGEINSERT_ID or not TYPE_SECTION_ID:
    print("❌ ERROR: Critical Types missing from schema.")
    sys.exit(1)

def main():
    print("=" * 80)
    print("EXTRACT SECTION CONTENT")
    print("=" * 80)
    
    # 1. Load all PackageInsert entities to get their set_ids
    print("\nLoading PackageInsert entities...")
    package_insert_id_to_setid = {}
    
    with open(ENTITIES_FILE, 'r') as f:
        for line in f:
            if not line.strip(): continue
            ent = json.loads(line)
            
            # Check if this entity is a PackageInsert using the Hashed ID
            types = ent.get('types', [])
            if isinstance(types, list):
                is_pi = TYPE_PACKAGEINSERT_ID in types
            else:
                is_pi = types == TYPE_PACKAGEINSERT_ID
            
            if is_pi:
                pid = ent.get('id')
                set_id = None
                
                # Extract fda_set_id
                if ent.get('values'):
                    for v in ent['values']:
                        if v is None: continue # SAFETY CHECK
                        if v.get('property') == PROP_FDA_SET_ID:
                            val = v.get('value')
                            if isinstance(val, dict):
                                set_id = val.get('value')
                            else:
                                set_id = val
                            break
                
                if pid and set_id:
                    package_insert_id_to_setid[pid] = set_id
    
    print(f"  Found {len(package_insert_id_to_setid):,} PackageInserts with set_ids")
    
    if not package_insert_id_to_setid:
        print("⚠️  WARNING: No PackageInserts found. Check entity types and property IDs.")
    
    # 2. Load Relations to link Sections to PackageInserts
    # We look for relations where 'from' is PackageInsert and 'to' is Section
    print("\nLoading relations to link Sections to PackageInserts...")
    section_id_to_setid = {}
    
    with open(RELATIONS_FILE, 'r') as f:
        for line in f:
            if not line.strip(): continue
            rel = json.loads(line)
            
            from_id = rel.get('from')
            to_id = rel.get('to')
            
            # If we know the from_id is a PackageInsert, then to_id is likely a Section
            if from_id in package_insert_id_to_setid:
                section_id_to_setid[to_id] = package_insert_id_to_setid[from_id]
            # Or vice versa, depending on schema direction (usually FROM -> TO)
            elif to_id in package_insert_id_to_setid:
                section_id_to_setid[from_id] = package_insert_id_to_setid[to_id]
                
    print(f"  Linked {len(section_id_to_setid):,} Sections to set_ids")
    
    # 3. Load Sections and extract content
    print("\nExtracting content from Sections...")
    sections_by_setid = defaultdict(list)
    
    section_count = 0
    missing_content = 0
    
    with open(ENTITIES_FILE, 'r') as f:
        for line in f:
            if not line.strip(): continue
            ent = json.loads(line)
            
            # Check if this entity is a Section using the Hashed ID
            types = ent.get('types', [])
            if isinstance(types, list):
                is_section = TYPE_SECTION_ID in types
            else:
                is_section = types == TYPE_SECTION_ID
            
            if is_section:
                section_id = ent.get('id')
                set_id = section_id_to_setid.get(section_id)
                
                if set_id:
                    title = None
                    content = None
                    
                    # Extract Title and Content
                    if ent.get('values'):
                        for v in ent['values']:
                            if v is None: continue # SAFETY CHECK
                            
                            prop_id = v.get('property')
                            val = v.get('value')
                            
                            # Extract actual value if it's nested
                            if isinstance(val, dict):
                                actual_val = val.get('value')
                            else:
                                actual_val = val
                            
                            if prop_id == PROP_TITLE:
                                title = actual_val
                            elif prop_id == PROP_CONTENT:
                                content = actual_val
                    
                    if not title and not content:
                        missing_content += 1
                        continue
                    
                    sections_by_setid[set_id].append({
                        'title': title,
                        'content': content
                    })
                    section_count += 1
    
    print(f"  Extracted {section_count:,} sections across {len(sections_by_setid):,} set_ids")
    if missing_content > 0:
        print(f"  ⚠️  Skipped {missing_content:,} sections with missing title/content")
    
    # 4. Save to JSON
    print(f"\nSaving to: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(sections_by_setid, f, indent=2)
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Total Set IDs with Content: {len(sections_by_setid):,}")
    print(f"Total Sections: {section_count:,}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 80)
    
    # Sample output
    if sections_by_setid:
        sample_set_id = next(iter(sections_by_setid))
        print(f"\n--- Sample Content for Set ID: {sample_set_id} ---")
        for sec in sections_by_setid[sample_set_id][:2]:
            print(f"Title: {sec['title']}")
            print(f"Content: {str(sec['content'])[:100]}...")

if __name__ == "__main__":
    main()
