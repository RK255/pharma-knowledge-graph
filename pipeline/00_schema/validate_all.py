#!/usr/bin/env python3
"""
GRC-20 Validation Script (v2)
==============================
Validates the final graph output against the Pharma Schema.
Supports JSONL format with entities and relations files.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from pharma_schema import PharmaSchema

DATA_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2")
ENTITIES_FILE = DATA_DIR / "grc20_merged_entities.jsonl"
RELATIONS_FILE = DATA_DIR / "grc20_merged_relations.jsonl"


def load_jsonl(filepath):
    """Load records from JSONL file."""
    records = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def main():
    print("=" * 70)
    print("GRC-20 VALIDATOR")
    print("=" * 70)
    
    schema = PharmaSchema()
    print(f"Schema Loaded: {schema.metadata.get('name', 'Unknown')} v{schema.metadata.get('version', 'Unknown')}")
    
    # Get IDs from schema
    has_provenance_id = schema.relations.get("has_provenance")
    provenance_type_id = schema.type_id("Provenance")
    
    print(f"\nSchema IDs:")
    print(f"  has_provenance relation: {has_provenance_id}")
    print(f"  Provenance type: {provenance_type_id}")
    
    # Check files exist
    if not ENTITIES_FILE.exists():
        print(f"❌ Error: Entities file not found at {ENTITIES_FILE}")
        sys.exit(1)
    
    if not RELATIONS_FILE.exists():
        print(f"❌ Error: Relations file not found at {RELATIONS_FILE}")
        sys.exit(1)
    
    print(f"\nLoading data...")
    print(f"  Entities: {ENTITIES_FILE.name}")
    print(f"  Relations: {RELATIONS_FILE.name}")
    
    entities = load_jsonl(ENTITIES_FILE)
    relations = load_jsonl(RELATIONS_FILE)
    
    print(f"  Total entities: {len(entities):,}")
    print(f"  Total relations: {len(relations):,}")
    
    # Build indexes
    entity_ids = set()
    provenance_entities = []
    provenance_ids = set()
    type_counts = defaultdict(int)
    unknown_type_ids = defaultdict(int)
    unknown_prop_ids = defaultdict(int)
    unknown_rel_ids = defaultdict(int)
    
    # Valid IDs from schema
    valid_type_ids = set(schema.types.values())
    valid_prop_ids = set(schema.properties.values())
    valid_rel_ids = set(schema.relations.values())
    
    print("\n" + "=" * 70)
    print("VALIDATING ENTITIES")
    print("=" * 70)
    
    for entity in entities:
        entity_id = entity.get("id")
        entity_ids.add(entity_id)
        
        # Check types
        types = entity.get("types", [])
        for type_id in types:
            type_counts[type_id] += 1
            if type_id not in valid_type_ids:
                unknown_type_ids[type_id] += 1
            
            # Track provenance entities
            if type_id == provenance_type_id:
                provenance_entities.append(entity)
                provenance_ids.add(entity_id)
        
        # Check properties
        for value in entity.get("values", []):
            prop_id = value.get("property")
            if prop_id and prop_id not in valid_prop_ids:
                unknown_prop_ids[prop_id] += 1
    
    # Resolve type names
    type_id_to_name = {v: k for k, v in schema.types.items()}
    
    print(f"\nEntity Types ({len(type_counts)} unique):")
    print("-" * 60)
    for type_id, count in sorted(type_counts.items(), key=lambda x: -x[1])[:15]:
        type_name = type_id_to_name.get(type_id, "unknown")
        pct = count / len(entities) * 100
        print(f"  {type_name:30} {count:10,}   {pct:5.1f}%")
    
    if len(type_counts) > 15:
        remaining = sum(c for t, c in type_counts.items() if type_id_to_name.get(t) not in list(type_id_to_name.keys())[:15])
        print(f"  {'... and more':30} {remaining:10,}")
    
    print("\n" + "=" * 70)
    print("VALIDATING RELATIONS")
    print("=" * 70)
    
    rel_type_counts = defaultdict(int)
    rel_missing_from = 0
    rel_missing_to = 0
    has_provenance_count = 0
    entities_with_provenance = set()
    
    for rel in relations:
        rel_id = rel.get("type")
        from_id = rel.get("from")
        to_id = rel.get("to")
        
        # Check relation type
        if rel_id:
            rel_type_counts[rel_id] += 1
            if rel_id not in valid_rel_ids:
                unknown_rel_ids[rel_id] += 1
        
        # Track has_provenance
        if rel_id == has_provenance_id:
            has_provenance_count += 1
            entities_with_provenance.add(from_id)
        
        # Check dangling references
        if from_id and from_id not in entity_ids:
            rel_missing_from += 1
        if to_id and to_id not in entity_ids:
            rel_missing_to += 1
    
    # Resolve relation type names
    rel_id_to_name = {v: k for k, v in schema.relations.items()}
    
    print(f"\nRelation Types ({len(rel_type_counts)} unique):")
    print("-" * 60)
    for rel_id, count in sorted(rel_type_counts.items(), key=lambda x: -x[1])[:15]:
        rel_name = rel_id_to_name.get(rel_id, "unknown")
        pct = count / len(relations) * 100
        print(f"  {rel_name:30} {count:10,}   {pct:5.1f}%")
    
    if len(rel_type_counts) > 15:
        print(f"  {'... and more':30}")
    
    print(f"\nDangling references:")
    print(f"  Relations with missing 'from' entity: {rel_missing_from}")
    print(f"  Relations with missing 'to' entity: {rel_missing_to}")
    
    print("\n" + "=" * 70)
    print("VALIDATING PROVENANCE")
    print("=" * 70)
    
    # Get provenance entity names
    provenance_sources = defaultdict(int)
    name_prop_id = schema.prop("name")
    
    for prov in provenance_entities:
        name = "Unknown"
        for value in prov.get("values", []):
            if value.get("property") == name_prop_id:
                name = value.get("value", "Unknown")
                break
        provenance_sources[name] += 1
    
    print(f"\nProvenance entities: {len(provenance_entities)}")
    print("\nProvenance Sources:")
    for source, count in sorted(provenance_sources.items()):
        print(f"  {source}: {count}")
    
    # Calculate provenance coverage
    non_prov_entities = len(entities) - len(provenance_entities)
    coverage = len(entities_with_provenance) / non_prov_entities * 100 if non_prov_entities > 0 else 100
    
    print(f"\nProvenance Coverage:")
    print(f"  Non-provenance entities: {non_prov_entities:,}")
    print(f"  Entities with has_provenance: {len(entities_with_provenance):,}")
    print(f"  Coverage: {coverage:.1f}%")
    
    if coverage >= 99.9:
        print("  ✅ Excellent coverage!")
    elif coverage >= 95:
        print("  ⚠️  Good coverage, but some entities missing provenance")
    else:
        print("  ❌ Low coverage - many entities missing provenance")
    
    print("\n" + "=" * 70)
    print("UNKNOWN IDS REPORT")
    print("=" * 70)
    
    issues = 0
    
    if unknown_type_ids:
        print(f"\n⚠️  Unknown Type IDs ({len(unknown_type_ids)} unique):")
        for uid, count in sorted(unknown_type_ids.items(), key=lambda x: -x[1])[:10]:
            print(f"  {uid}: {count:,}")
        issues += sum(unknown_type_ids.values())
    else:
        print("\n✅ All type IDs are valid")
    
    if unknown_prop_ids:
        print(f"\n⚠️  Unknown Property IDs ({len(unknown_prop_ids)} unique):")
        for uid, count in sorted(unknown_prop_ids.items(), key=lambda x: -x[1])[:10]:
            print(f"  {uid}: {count:,}")
        issues += sum(unknown_prop_ids.values())
    else:
        print("\n✅ All property IDs are valid")
    
    if unknown_rel_ids:
        print(f"\n⚠️  Unknown Relation Type IDs ({len(unknown_rel_ids)} unique):")
        for uid, count in sorted(unknown_rel_ids.items(), key=lambda x: -x[1])[:10]:
            print(f"  {uid}: {count:,}")
        issues += sum(unknown_rel_ids.values())
    else:
        print("\n✅ All relation type IDs are valid")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print(f"""
  Entities:        {len(entities):>10,}
  Relations:       {len(relations):>10,}
  Entity Types:    {len(type_counts):>10}
  Relation Types:  {len(rel_type_counts):>10}
  Provenance:      {coverage:>9.1f}%
  Unknown IDs:     {issues:>10,}
""")
    
    if issues == 0 and coverage >= 99.9:
        print("✅ VALIDATION PASSED")
        return 0
    else:
        print("⚠️  VALIDATION COMPLETED WITH WARNINGS")
        return 1


if __name__ == "__main__":
    sys.exit(main())
