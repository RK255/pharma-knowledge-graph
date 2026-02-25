#!/usr/bin/env python3
"""
Load drug data from provenance ledger into Redis for search.
"""
import json
import redis
import sys
from typing import Dict, List

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)

# Path to provenance ledger
PROVENANCE_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/provenance/Granular_Provenance_Ledger.json"

def load_drugs():
    """Load drugs from provenance ledger into Redis."""
    print("Loading provenance ledger...")
    with open(PROVENANCE_PATH, 'r') as f:
        data = json.load(f)
    
    print(f"Total entries: {len(data)}")
    
    # Build search index
    drug_index: Dict[str, List[Dict]] = {}
    drug_details = {}
    count = 0
    
    for hash_key, entry in data.items():
        if not isinstance(entry, dict):
            continue
            
        if entry.get('data_type') != 'concept':
            continue
            
        name = entry.get('name', '')
        if not name:
            continue
            
        name_lower = name.lower()
        rxcui = entry.get('rxcui', '')
        tty = entry.get('tty', '')
        
        # Skip certain TTYs that aren't useful for search
        if tty in ['DF', 'DFG']:  # Dose forms
            continue
        
        # Add to index
        if name_lower not in drug_index:
            drug_index[name_lower] = []
        
        drug_info = {
            'id': hash_key,
            'name': name,
            'rxcui': rxcui,
            'tty': tty,
            'manufacturer': '',  # Will be filled from FDA data if available
            'citation': entry.get('full_citation', '')
        }
        
        drug_index[name_lower].append(drug_info)
        
        # Store full details
        drug_details[hash_key] = json.dumps({
            'id': hash_key,
            'name': name,
            'rxcui': rxcui,
            'tty': tty,
            'provenance': entry
        })
        
        count += 1
        if count % 100000 == 0:
            print(f"Processed {count} entries...")
    
    print(f"Total drugs indexed: {len(drug_index)}")
    print(f"Total variants: {count}")
    
    # Load into Redis
    print("Loading into Redis...")
    
    # Clear existing data
    redis_client.delete('pharma:drug_index')
    redis_client.delete('pharma:drug_details')
    redis_client.delete('pharma:enhanced_drugs')
    
    # Load drug details
    if drug_details:
        redis_client.hset('pharma:drug_details', mapping=drug_details)
        print(f"Loaded {len(drug_details)} drug details")
    
    # Load search index
    index_json = json.dumps(drug_index)
    redis_client.set('pharma:drug_index', index_json)
    print(f"Loaded search index")
    
    # Set loaded flag
    redis_client.set('pharma:loaded', 'true')
    
    # Stats
    print("\n=== Load Complete ===")
    print(f"Unique drug names: {len(drug_index)}")
    print(f"Total variants: {count}")
    
    # Sample lookups
    print("\nSample lookups:")
    for name in ['simvastatin', 'atorvastatin', 'metformin', 'aspirin']:
        if name in drug_index:
            print(f"  {name}: {len(drug_index[name])} variants")
            print(f"    First: {drug_index[name][0]}")
    
    return drug_index, drug_details

if __name__ == '__main__':
    load_drugs()
