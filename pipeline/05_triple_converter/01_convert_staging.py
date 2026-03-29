#!/usr/bin/env python3
"""
Simplified Convert Staging: Merge existing grc20_v2 JSONL files
"""

import sys
import json
import argparse
from pathlib import Path
import importlib.util
from datetime import datetime

# Import pharma_schema
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR.parent.parent))

spec = importlib.util.spec_from_file_location(
    "pharma_schema", 
    str(BASE_DIR.parent / "00_schema" / "pharma_schema.py")
)
pharma_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pharma_schema)

# Define paths
DATA_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2")
OUTPUT_FILE = DATA_DIR / "grc20_merged_entities.jsonl"

def load_json_file(filepath):
    """Load a JSON or JSONL file, returning a list of entities."""
    # Read entire file content first
    with open(filepath, 'r') as f:
        content = f.read()
    
    if not content.strip():
        return []
    
    # Try to detect format by checking if it's valid JSON first
    stripped = content.strip()
    
    # Check if it's a JSON array
    if stripped.startswith('['):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data.get('entities', [])
            elif isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    
    # Check if it's a JSON object with entities key (like dailymed_entities.json)
    elif stripped.startswith('{'):
        try:
            data = json.loads(content)
            if isinstance(data, dict) and 'entities' in data:
                return data.get('entities', [])
        except json.JSONDecodeError:
            pass
    
    # If we get here, it's likely JSONL format
    entities = []
    for line in content.split('\n'):
        line = line.strip()
        if line:
            try:
                entities.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entities

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of entities")
    args = parser.parse_args()
    
    print("=" * 80)
    print("GRC-20 STAGING CONVERTER (SIMPLIFIED)")
    print("=" * 80)
    print(f"Timestamp: {datetime.now()}")
    print(f"Data dir: {DATA_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print()
    
    # Collect all entity files
    entity_files = [
        "dailymed_entities.json",
        "rxnorm_entities.jsonl",
        "ndc_bridge_entities.jsonl",
        "pubchem_entities.jsonl",
    ]
    
    all_entities = []
    
    for filename in entity_files:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  ⚠️  {filename} not found, skipping")
            continue
        
        print(f"  ✓ Processing {filename}...")
        
        try:
            entities = load_json_file(filepath)
            all_entities.extend(entities)
            print(f"    Found {len(entities):,} entities")
        except Exception as e:
            print(f"    ⚠️  Error loading: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Limit if requested
    if args.limit:
        all_entities = all_entities[:args.limit]
    
    # Write output as JSONL
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    written = 0
    with open(OUTPUT_FILE, 'w') as f:
        for entity in all_entities:
            f.write(json.dumps(entity, default=str) + '\n')
            written += 1
    
    print()
    print("=" * 80)
    print("CONVERSION COMPLETE")
    print("=" * 80)
    print(f"  Total entities: {len(all_entities):,}")
    print(f"  Written: {written:,}")
    print(f"  Output file: {OUTPUT_FILE}")
    print("=" * 80)

if __name__ == "__main__":
    main()
