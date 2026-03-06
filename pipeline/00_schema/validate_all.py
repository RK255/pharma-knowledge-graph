#!/usr/bin/env python3
"""
GRC-20 Validation Script
=========================
Validates the final graph output against the Pharma Schema.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from pharma_schema import PharmaSchema

DATA_FILE = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2/grc20_with_relations.json")

def main():
    print("=" * 70)
    print("GRC-20 VALIDATOR")
    print("=" * 70)
    
    schema = PharmaSchema()
    print(f"Schema Loaded: {schema.metadata.get('name', 'Unknown')} v{schema.metadata.get('version', 'Unknown')}")
    
    # DYNAMIC IDs: Get them from the Schema, don't hardcode
    # System Attributes (GRC-20 Standard)
    type_attr_id = "Jfmby78N4BCseZinBmdVov"
    from_attr_id = "RERshk4JoYoMC17r1qAo9J"
    to_attr_id   = "Qx8dASiTNsxxP3rJbd4Lzd"
    
    # Schema Attributes
    prov_attr_id = schema.attr("provenance")
    name_attr_id = schema.attr("name")
    source_attr_id = schema.attr("source")
    
    print(f"System IDs:\n  Type: {type_attr_id}\n  From: {from_attr_id}\n  To: {to_attr_id}")
    print(f"Schema IDs:\n  Provenance: {prov_attr_id}\n  Name: {name_attr_id}")
    
    if not DATA_FILE.exists():
        print(f"❌ Error: Data file not found at {DATA_FILE}")
        sys.exit(1)
        
    print(f"\nLoading data from {DATA_FILE.name}...")
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        entities = data if isinstance(data, list) else data.get("entities", [])
    
    print(f"  Total entities: {len(entities):,}")
    
    unknown_type_ids = defaultdict(int)
    unknown_attr_ids = defaultdict(int)
    provenance_entities = []
    relation_entities = []
    provenance_map = defaultdict(int)
    
    # Set of valid IDs for fast checking
    valid_relation_ids = set(schema.relations.values())
    # System Attribute IDs that should NOT be flagged as unknown
    system_attr_ids = {type_attr_id, from_attr_id, to_attr_id}
    valid_attr_ids = set(schema.attributes.values()).union(system_attr_ids)
    
    for e in entities:
        entity_id = e.get("entity")
        triples = e.get("triples", [])
        
        is_provenance = False
        is_relation = False
        prov_name = "Unknown"
        prov_source = "Unknown"
        
        for t in triples:
            attr = t.get("attribute")
            val = t.get("value", {})
            val_str = str(val.get("value", ""))
            
            # 1. Check for Relation Entities
            if attr == from_attr_id or attr == to_attr_id:
                is_relation = True
                
            # 2. Check Provenance Types
            if attr == type_attr_id:
                # Check if the value ID matches the Provenance Type ID in Schema
                if val_str == schema.types.get("Provenance"):
                    is_provenance = True
                # Check Unknown Relation Type IDs (Only if it's a relation entity)
                if is_relation and val_str not in valid_relation_ids:
                    # Filter out system types like "Relation"
                    if val_str not in ["Relation", "RelationType", "Attribute", "Type"]:
                        unknown_type_ids[val_str] += 1
            
            # 3. Extract Provenance Details (Name & Source)
            if is_provenance:
                if attr == name_attr_id: prov_name = val_str
                if attr == source_attr_id: prov_source = val_str
            
            # 4. Detect Unknown Attribute IDs
            if attr not in valid_attr_ids:
                unknown_attr_ids[attr] += 1
        
        if is_provenance:
            provenance_entities.append({
                "id": entity_id,
                "source": prov_source,
                "name": prov_name
            })
            provenance_map[prov_source] += 1
            
        if is_relation:
            relation_entities.append(e)

    # REPORTING
    print("\n" + "=" * 70)
    print("VALIDATING RELATION ENTITIES")
    print("=" * 70)
    
    total_rels = len(relation_entities)
    incomplete_rels = 0
    rel_type_counts = defaultdict(int)
    unknown_rel_types = 0
    
    print(f"Total relation entities: {total_rels:,}")
    
    for rel in relation_entities:
        triples = rel.get("triples", [])
        has_from = False
        has_to = False
        rel_type_id = None
        
        for t in triples:
            attr = t.get("attribute")
            val = t.get("value", {}).get("value")
            
            if attr == from_attr_id: has_from = True
            if attr == to_attr_id: has_to = True
            if attr == type_attr_id and val not in ["Attribute", "Relation", "RelationType"]:
                rel_type_id = val
        
        if not has_from or not has_to:
            incomplete_rels += 1
        
        # Resolve Type Name
        type_name = "unknown"
        if rel_type_id:
            # Reverse lookup in schema.relations
            type_name = next((k for k,v in schema.relations.items() if v == rel_type_id), "unknown")
            if type_name == "unknown":
                unknown_rel_types += 1
        
        rel_type_counts[type_name] += 1
    
    print(f"Incomplete relations (missing from/to): {incomplete_rels}")
    print(f"⚠️  Relations with IDs not in schema: {unknown_rel_types} (Shown as 'unknown' below)")
    
    print("\nRelation Type                       Count        %")
    print("-" * 60)
    total_valid_rels = sum(rel_type_counts.values())
    for r_name, count in sorted(rel_type_counts.items(), key=lambda x: -x[1]):
        pct = (count / total_valid_rels * 100) if total_valid_rels > 0 else 0
        print(f"{r_name:30} {count:10,}   {pct:5.1f}%")
    
    print("\n" + "=" * 70)
    print("VALIDATING PROVENANCE")
    print("=" * 70)
    
    print(f"Provenance entities: {len(provenance_entities)}\n")
    print("Provenance Sources:")
    for source, count in sorted(provenance_map.items()):
        print(f"  {source}: {count:,}")
    
    # Calculate Coverage
    total_entities = len(entities)
    prov_entities_count = len(provenance_entities)
    other_entities = total_entities - prov_entities_count
    
    # Count entities WITH provenance attribute using the Schema ID
    entities_with_provenance = 0
    for e in entities:
        # Skip type definition entities
        if e.get('entity') in [
            "Ens7AArMgnLiF6xyuacwKR",
            "HoYHubmhgWM9j3BJZXPytL",
            "AiPDpTAJaap8B2EbDcpudK",
        ]:
            continue
        if any(t.get("attribute") == prov_attr_id for t in e.get("triples", [])):
            entities_with_provenance += 1
            
    print(f"\nEntities (excluding provenance): {other_entities:,}")
    print(f"  With provenance: {entities_with_provenance:,} ({(entities_with_provenance/other_entities*100) if other_entities else 100:.1f}%)")
    print(f"  Without provenance: {other_entities - entities_with_provenance:,} ({((other_entities - entities_with_provenance)/other_entities*100) if other_entities else 0:.1f}%)")

    print("\n" + "=" * 70)
    print("UNKNOWN IDS REPORT")
    print("=" * 70)
    
    print(f"\nUnknown Type IDs ({len(unknown_type_ids)} unique, {sum(unknown_type_ids.values())} total):")
    if unknown_type_ids:
        for uid, count in sorted(unknown_type_ids.items(), key=lambda x: -x[1]):
            print(f"  {uid}: {count:,}")
    else:
        print("  None")

    print(f"\nUnknown Attribute IDs ({len(unknown_attr_ids)} unique, {sum(unknown_attr_ids.values())} total):")
    if unknown_attr_ids:
        for uid, count in sorted(unknown_attr_ids.items(), key=lambda x: -x[1]):
            print(f"  {uid}: {count:,}")
    else:
        print("  None")
        
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Total entities: {total_entities:,}")
    print(f"Entity types: {len(schema.types)}")
    print(f"Unique attributes: {len(schema.attributes)}")
    print(f"Relation types: {len(schema.relations)}")
    
    all_good = (
        incomplete_rels == 0 and 
        unknown_rel_types == 0 and 
        len(unknown_type_ids) == 0 and 
        len(unknown_attr_ids) == 0
    )
    
    if all_good:
        print("  ✅ Schema Consistency: Complete")
    else:
        print("  ❌ Schema Consistency: Issues Found")
        
    if entities_with_provenance == other_entities:
        print("  ✅ Provenance Coverage: Complete")
    else:
        print(f"  ❌ Provenance Coverage: Incomplete ({other_entities - entities_with_provenance:,} missing)")

if __name__ == "__main__":
    main()
