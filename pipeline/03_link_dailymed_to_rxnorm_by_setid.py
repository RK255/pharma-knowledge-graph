"""
03_link_dailymed_to_rxnorm_by_setid.py

Links DailyMed PackageInserts to RxNorm entities using SPL Set IDs.
This replaces the fragile NDC-NDC matching approach with Set ID-based linking.

Primary method: Set ID matching (75.8% coverage)
Fallback method: NDC matching (for remaining ~24% without Set IDs)
"""

import json
import os
from collections import defaultdict

# GRC-20 Property IDs
PACKAGEINSERT_TYPE = "0af427a2b7df5f6dbdb4fb86a54359fd"
FDA_SET_ID_PROPERTY = "78d0af3db973513e8be0cb76afa5e9c4"
NDC_CODE_PROPERTY = "694ec99a6c8e555caba8d8bb72f302c8"

def load_set_id_mappings():
    """Load NDC → Set ID mappings from RxNorm"""
    setid_file = '/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/ndc_to_setid_final_v3.json'
    
    if not os.path.exists(setid_file):
        print(f"Warning: Set ID mapping file not found: {setid_file}")
        return {}, {}
    
    with open(setid_file, 'r') as f:
        data = json.load(f)
    
    ndc_to_setid = data.get('ndc_to_setid', {})
    print(f"Loaded {len(ndc_to_setid):,} NDC → Set ID mappings")
    
    return ndc_to_setid, data

def load_ndc_to_rxcui_mappings():
    """Load NDC → RxCUI mappings from bridge"""
    bridge_file = '/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/ndc_to_rxcui.json'
    
    if not os.path.exists(bridge_file):
        print(f"Warning: NDC bridge file not found: {bridge_file}")
        return {}
    
    with open(bridge_file, 'r') as f:
        data = json.load(f)
    
    # Handle both formats
    if 'ndc_to_rxcui' in data:
        ndc_to_rxcui = data['ndc_to_rxcui']
    else:
        ndc_to_rxcui = data
    
    print(f"Loaded {len(ndc_to_rxcui):,} NDC → RxCUI mappings")
    
    return ndc_to_rxcui

def load_dailymed_package_inserts():
    """Load DailyMed PackageInsert entities from GRC-20 JSONL"""
    dailymed_file = '/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2/dailymed_entities.jsonl'
    
    if not os.path.exists(dailymed_file):
        print(f"Error: DailyMed entities file not found: {dailymed_file}")
        return []
    
    package_inserts = []
    
    print("Loading DailyMed entities...")
    with open(dailymed_file, 'r') as f:
        line_count = 0
        for line in f:
            try:
                entity = json.loads(line)
                
                # Check if this is a PackageInsert
                if 'types' in entity and PACKAGEINSERT_TYPE in entity['types']:
                    package_inserts.append(entity)
                
                line_count += 1
                if line_count % 100000 == 0:
                    print(f"  Processed {line_count:,} lines, found {len(package_inserts):,} PackageInserts...", end='\r')
            except json.JSONDecodeError:
                continue
    
    print(f"\nLoaded {len(package_inserts):,} PackageInserts from {line_count:,} entities")
    
    return package_inserts

def extract_set_id_from_package_insert(package_insert):
    """
    Extract Set ID from a PackageInsert entity (GRC-20 format).
    """
    if 'values' not in package_insert:
        return None
    
    for value_obj in package_insert['values']:
        if value_obj.get('property') == FDA_SET_ID_PROPERTY:
            set_id = value_obj.get('value')
            if set_id:
                return set_id
    
    return None

def extract_ndcs_from_package_insert(package_insert):
    """
    Extract NDCs from a PackageInsert entity (GRC-20 format).
    Used as fallback when Set ID is not available.
    """
    ndcs = []
    
    if 'values' not in package_insert:
        return ndcs
    
    for value_obj in package_insert['values']:
        if value_obj.get('property') == NDC_CODE_PROPERTY:
            ndc = value_obj.get('value')
            if ndc:
                ndcs.append(ndc)
    
    return ndcs

def link_package_insert_to_rxnorm(package_insert, ndc_to_setid, ndc_to_rxcui):
    """
    Link a PackageInsert to RxNorm entities using Set ID (primary)
    and NDC (fallback).
    
    Returns: {
        'package_insert_id': str,
        'set_id': str or None,
        'linking_method': 'set_id' or 'ndc_fallback' or 'no_link',
        'rxcuis': list[str],
        'ndcs_used': list[str]
    }
    """
    pi_id = package_insert.get('id', 'unknown')
    
    # Method 1: Set ID linking (primary)
    set_id = extract_set_id_from_package_insert(package_insert)
    
    if set_id:
        # Find all RxCUIs that have NDCs with this Set ID
        rxcuis = set()
        matching_ndcs = []
        
        for ndc, sid in ndc_to_setid.items():
            if sid == set_id:
                if ndc in ndc_to_rxcui:
                    rxcuis.add(str(ndc_to_rxcui[ndc]))
                    matching_ndcs.append(ndc)
        
        if rxcuis:
            return {
                'package_insert_id': pi_id,
                'set_id': set_id,
                'linking_method': 'set_id',
                'rxcuis': sorted(rxcuis),
                'ndcs_used': matching_ndcs,
                'match_count': len(rxcuis)
            }
    
    # Method 2: NDC fallback (for PackageInserts without Set IDs)
    ndcs = extract_ndcs_from_package_insert(package_insert)
    
    if ndcs:
        rxcuis = set()
        matching_ndcs = []
        
        for ndc in ndcs:
            if ndc in ndc_to_rxcui:
                rxcuis.add(str(ndc_to_rxcui[ndc]))
                matching_ndcs.append(ndc)
        
        if rxcuis:
            return {
                'package_insert_id': pi_id,
                'set_id': set_id,
                'linking_method': 'ndc_fallback',
                'rxcuis': sorted(rxcuis),
                'ndcs_used': matching_ndcs,
                'match_count': len(rxcuis)
            }
    
    # No link found
    return {
        'package_insert_id': pi_id,
        'set_id': set_id,
        'linking_method': 'no_link',
        'rxcuis': [],
        'ndcs_used': [],
        'match_count': 0
    }

def main():
    print("=" * 80)
    print("LINKING DAILYMED PACKAGE INSERTS TO RXNORM VIA SET IDs")
    print("=" * 80 + "\n")
    
    # Load mappings
    ndc_to_setid, setid_data = load_set_id_mappings()
    ndc_to_rxcui = load_ndc_to_rxcui_mappings()
    
    # Load PackageInserts
    package_inserts = load_dailymed_package_inserts()
    
    if not package_inserts:
        print("\nError: No PackageInserts loaded. Please check the file path.")
        return
    
    # Link each PackageInsert to RxNorm
    results = []
    
    print("\nLinking PackageInserts to RxNorm...")
    for i, pi in enumerate(package_inserts):
        result = link_package_insert_to_rxnorm(pi, ndc_to_setid, ndc_to_rxcui)
        results.append(result)
        
        if (i + 1) % 1000 == 0:
            print(f"  Processed {i+1:,}/{len(package_inserts):,} PackageInserts...", end='\r')
    
    print(f"\n  Processed {len(results):,} PackageInserts")
    
    # Analyze results
    set_id_links = [r for r in results if r['linking_method'] == 'set_id']
    ndc_fallback_links = [r for r in results if r['linking_method'] == 'ndc_fallback']
    no_links = [r for r in results if r['linking_method'] == 'no_link']
    
    print("\n" + "=" * 80)
    print("LINKING RESULTS")
    print("=" * 80 + "\n")
    
    print(f"Total PackageInserts: {len(results):,}")
    print(f"Set ID links: {len(set_id_links):,} ({len(set_id_links)/len(results)*100:.1f}%)")
    print(f"NDC fallback links: {len(ndc_fallback_links):,} ({len(ndc_fallback_links)/len(results)*100:.1f}%)")
    print(f"No links: {len(no_links):,} ({len(no_links)/len(results)*100:.1f}%)")
    
    print("\n" + "=" * 80)
    print("SAMPLE LINKS")
    print("=" * 80 + "\n")
    
    # Show some sample Set ID links
    print("Set ID links (sample):")
    for i, link in enumerate(set_id_links[:5]):
        print(f"  {i+1}. {link['package_insert_id']} → Set ID {link['set_id'][:30]}...")
        print(f"     RxCUIs: {', '.join(link['rxcuis'][:5])}...")
        print(f"     Matched {len(link['rxcuis'])} RxCUIs via {len(link['ndcs_used'])} NDCs")
    
    if ndc_fallback_links:
        print("\nNDC fallback links (sample):")
        for i, link in enumerate(ndc_fallback_links[:5]):
            print(f"  {i+1}. {link['package_insert_id']} (no Set ID)")
            print(f"     RxCUIs: {', '.join(link['rxcuis'][:5])}...")
            print(f"     Matched {len(link['rxcuis'])} RxCUIs via {len(link['ndcs_used'])} NDCs")
    
    if no_links:
        print(f"\nNo links (sample):")
        for i, link in enumerate(no_links[:5]):
            print(f"  {i+1}. {link['package_insert_id']}")
    
    # Save results
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80 + "\n")
    
    output_file = '/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2/dailymed_rxnorm_setid_links.json'
    
    output_data = {
        'links': results,
        'summary': {
            'total_package_inserts': len(results),
            'set_id_links': len(set_id_links),
            'ndc_fallback_links': len(ndc_fallback_links),
            'no_links': len(no_links),
            'set_id_coverage': len(set_id_links)/len(results)*100 if results else 0,
            'ndc_fallback_coverage': len(ndc_fallback_links)/len(results)*100 if results else 0,
            'total_coverage': (len(set_id_links) + len(ndc_fallback_links))/len(results)*100 if results else 0
        },
        'mapping_stats': {
            'ndc_to_setid_count': len(ndc_to_setid),
            'ndc_to_rxcui_count': len(ndc_to_rxcui),
            'set_id_coverage': setid_data.get('coverage_percent', 0)
        }
    }
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Saved results to: {output_file}")
    
    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"""
Summary:
  - Total PackageInserts processed: {len(results):,}
  - Linked via Set ID: {len(set_id_links):,}
  - Linked via NDC fallback: {len(ndc_fallback_links):,}
  - No link found: {len(no_links):,}
  - Total coverage: {output_data['summary']['total_coverage']:.1f}%

Output file:
  {output_file}
""")

if __name__ == '__main__':
    main()
