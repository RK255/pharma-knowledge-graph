#!/usr/bin/env python3
"""
Fetch PubChem properties (SMILES, InChIKey) for all CIDs in the mapping file
"""

import json
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
DATA_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2")
CID_MAPPING_FILE = DATA_DIR / "pubchem_cid_mapping.json"
OUTPUT_FILE = DATA_DIR / "pubchem_properties.json"

# Load CID mapping
print(f"Loading CID mapping from {CID_MAPPING_FILE}...")
with open(CID_MAPPING_FILE, 'r') as f:
    cid_data = json.load(f)

cid_mapping = cid_data.get('cid_mapping', {})
print(f"Found {len(cid_mapping):,} CIDs")

def fetch_cid_properties(rxcui, cid_info):
    """Fetch properties for a single CID"""
    cid = cid_info['cid']
    name = cid_info['name']
    
    try:
        # Use PubChem PUG REST API
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/CanonicalSMILES,InChIKey,IsomericSMILES/MJSON"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('Properties', {}).get('Comment'):
            # No data available
            print(f"  No data for {name} (CID: {cid})")
            return None
        
        props = data['PropertyTable']['Properties'][0]
        
        result = {
            'rxcui': rxcui,
            'cid': cid,
            'name': name,
            'canonical_smiles': props.get('CanonicalSMILES', ''),
            'isomeric_smiles': props.get('IsomericSMILES', ''),
            'inchikey': props.get('InChIKey', '')
        }
        
        if result['canonical_smiles'] or result['inchikey']:
            print(f"  ✓ {name} (CID: {cid})")
            return result
        else:
            print(f"  ✗ {name} (CID: {cid}) - No properties")
            return None
            
    except Exception as e:
        print(f"  ✗ {name} (CID: {cid}) - Error: {e}")
        return None

# Fetch properties for all CIDs
print("\nFetching properties from PubChem...")
print("This may take a while (API rate limiting)...\n")

properties = []
successful = 0

# Use ThreadPoolExecutor for parallel requests
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(fetch_cid_properties, rxcui, cid_info): rxcui 
               for rxcui, cid_info in cid_mapping.items()}
    
    for future in as_completed(futures):
        result = future.result()
        if result:
            properties.append(result)
            successful += 1
        
        # Rate limiting
        time.sleep(0.2)
        
        # Progress
        if successful % 100 == 0:
            print(f"Progress: {successful}/{len(cid_mapping)}")

print(f"\nSuccessfully fetched properties for {successful}/{len(cid_mapping)} CIDs")

# Create output data
output_data = {
    'generated_at': str(Path(__file__).stat().st_mtime),
    'source': 'PubChem PUG REST',
    'total_properties': len(properties),
    'properties': properties
}

# Save to file
print(f"\nSaving properties to {OUTPUT_FILE}...")
with open(OUTPUT_FILE, 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"Done! Saved {len(properties)} properties")
