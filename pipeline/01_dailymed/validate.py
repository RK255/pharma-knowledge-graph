#!/usr/bin/env python3
"""
Dailymed GRC-20 Validation Wrapper
Validates both entities and relations files
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add parent directory to path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Import pharma_schema using importlib (handles '00_schema' naming issue)
import importlib.util
spec = importlib.util.spec_from_file_location("pharma_schema", str(BASE_DIR / "00_schema" / "pharma_schema.py"))
pharma_schema_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pharma_schema_module)


def is_entities_file(filepath: str) -> bool:
    """Check if file contains entities (not relations)."""
    if not Path(filepath).exists():
        return False
    
    with open(filepath, 'r') as f:
        first_line = f.readline()
    
    try:
        data = json.loads(first_line)
        # Entities have 'values', relations have 'from'/'to'
        return 'values' in data or ('type' in data and 'types' in data)
    except:
        return False


def validate_entities_file(entities_file: str) -> bool:
    """Validate entities file (JSONL format)."""
    
    print("=" * 70)
    print("VALIDATING ENTITIES")
    print("=" * 70)
    
    if not Path(entities_file).exists():
        print(f"❌ Entities file not found: {entities_file}")
        return False
    
    try:
        with open(entities_file, 'r') as f:
            entities = [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        print(f"❌ Error loading entities: {e}")
        return False
    
    print(f"Loaded {len(entities):,} entities")
    
    # Try to load schema
    schema = None
    valid_type_ids = set()
    valid_prop_ids = set()
    try:
        schema = pharma_schema_module.PharmaSchema()
        schema.initialize()
        valid_type_ids = {t['id'] for t in schema.types.values()}
        valid_prop_ids = {p['id'] for p in schema.properties.values()}
        print(f"Schema: {schema.metadata.get('name', 'Unknown')} v{schema.metadata.get('version', 'Unknown')}")
    except Exception as e:
        print(f"⚠️  Schema not available: {e}")
    
    # Validate entities
    errors = []
    
    for i, entity in enumerate(entities):
        entity_id = entity.get("id", "unknown")
        
        # Check for required fields
        if not entity_id:
            errors.append(f"[{i}] Entity missing 'id' field")
            continue
        
        # Check for types (plural or singular)
        has_types = entity.get('types') or entity.get('type')
        if not has_types:
            errors.append(f"[{i}] Entity {entity_id[:8]} missing type(s)")
        
        # Check values if schema available
        if schema and entity.get('values'):
            for j, value in enumerate(entity['values']):
                prop_id = value.get('property')
                if isinstance(prop_id, dict):
                    prop_id = prop_id.get('id', '')
                if prop_id and prop_id not in valid_prop_ids:
                    errors.append(f"[{i}] Entity {entity_id[:8]} has unknown property: {prop_id[:8]}")
    
    if errors:
        print(f"\n❌ Found {len(errors)} validation errors:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return False
    else:
        print(f"\n✅ All {len(entities):,} entities validated successfully")
        return True


def validate_relations_file(relations_file: str) -> bool:
    """Validate relations file (JSONL format)."""
    
    print("=" * 70)
    print("VALIDATING RELATIONS")
    print("=" * 70)
    
    if not Path(relations_file).exists():
        print(f"⚠️  Relations file not found: {relations_file}")
        return True  # Don't fail if missing
    
    try:
        with open(relations_file, 'r') as f:
            relations = [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        print(f"❌ Error loading relations: {e}")
        return False
    
    print(f"Loaded {len(relations):,} relations")
    
    # Validate relations
    errors = []
    
    for i, rel in enumerate(relations):
        rel_id = rel.get("id", "unknown")
        
        # Check for required fields
        if not rel_id:
            errors.append(f"[{i}] Relation missing 'id' field")
            continue
        
        if 'from' not in rel:
            errors.append(f"[{i}] Relation {rel_id[:8]} missing 'from' field")
        
        if 'to' not in rel:
            errors.append(f"[{i}] Relation {rel_id[:8]} missing 'to' field")
        
        if 'type' not in rel:
            errors.append(f"[{i}] Relation {rel_id[:8]} missing 'type' field")
    
    if errors:
        print(f"\n❌ Found {len(errors)} validation errors:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return False
    else:
        print(f"\n✅ All {len(relations):,} relations validated successfully")
        return True


def validate_grc20(entities_file: str, relations_file: str = None) -> bool:
    """Validate GRC-20 output files."""
    
    print("=" * 70)
    print("DAILYMED GRC-20 VALIDATION")
    print("=" * 70)
    
    # Auto-detect if input is entities or relations
    if not Path(entities_file).exists():
        print(f"❌ File not found: {entities_file}")
        return False
    
    if is_entities_file(entities_file):
        print(f"\n📄 Auto-detected: {entities_file} contains ENTITIES")
        return validate_entities_file(entities_file)
    else:
        print(f"\n📄 Auto-detected: {entities_file} contains RELATIONS")
        return validate_relations_file(entities_file)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("entities_file", help="Path to entities file (JSONL)")
    parser.add_argument("--relations", help="Path to relations file (optional)")
    args = parser.parse_args()
    
    success = validate_grc20(args.entities_file, args.relations)
    sys.exit(0 if success else 1)
