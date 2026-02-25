#!/usr/bin/env python3
"""
Repackager NDC Linker v2 - Equivalence-Based
=============================================
Links repackager NDCs to original manufacturer equivalents using
drug equivalence (same ingredient + strength + form + route).

This enables: "Repackager NDC X" → "Original NDC Y" → RxNorm RxCUI
"""

import json
import sys
from collections import defaultdict
from datetime import datetime

# Add production path
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production')
from ndc_utils import normalize_ndc

# Paths
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
PRODUCT_INFO_FILE = f"{BASE_DIR}/scripts/development/output/product_info_full.json"
RXNORM_NDC_FILE = f"{BASE_DIR}/data/raw_data/ndc_normalized_v2.txt"
OUTPUT_DIR = f"{BASE_DIR}/scripts/development/output"

def load_rxnorm_ndcs():
    """Load normalized RxNorm NDCs"""
    rxnorm_ndcs = set()
    with open(RXNORM_NDC_FILE, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if parts:
                ndc = normalize_ndc(parts[0])
                if ndc:
                    rxnorm_ndcs.add(ndc)
    return rxnorm_ndcs

def main():
    print("=" * 70)
    print("REPACKAGER NDC LINKER v2 - Equivalence-Based")
    print("=" * 70)
    
    # Load data
    print("\n[1/4] Loading RxNorm NDCs...")
    rxnorm_ndcs = load_rxnorm_ndcs()
    print(f"  ✅ Loaded {len(rxnorm_ndcs):,} RxNorm NDCs")
    
    print("\n[2/4] Loading product info...")
    with open(PRODUCT_INFO_FILE, 'r') as f:
        data = json.load(f)
    
    products = data['products']
    groups = data['equivalence_groups']
    print(f"  ✅ Loaded {len(products):,} products")
    print(f"  ✅ Loaded {len(groups):,} equivalence groups")
    
    print("\n[3/4] Building NDC links...")
    
    # Build equivalence groups with RxNorm matching
    equivalence_links = []
    ndc_to_equivalence = {}  # ndc -> equivalence_key
    rxnorm_linked_groups = 0
    total_linkable_ndcs = 0
    
    for eq_key, group_products in groups.items():
        # Find which NDCs in this group are in RxNorm
        rxnorm_ndcs_in_group = set()
        all_ndcs_in_group = []
        
        for product in group_products:
            for ndc in product['ndc_codes']:
                all_ndcs_in_group.append({
                    'ndc': ndc,
                    'manufacturer': product['manufacturer'],
                    'product_name': product['product_name'],
                    'set_id': product['set_id']
                })
                ndc_to_equivalence[ndc] = eq_key
                
                if ndc in rxnorm_ndcs:
                    rxnorm_ndcs_in_group.add(ndc)
        
        # If any NDC in the group is in RxNorm, all are linkable
        if rxnorm_ndcs_in_group:
            rxnorm_linked_groups += 1
            total_linkable_ndcs += len(all_ndcs_in_group)
            
            link = {
                'equivalence_key': eq_key,
                'total_products': len(group_products),
                'total_ndcs': len(all_ndcs_in_group),
                'rxnorm_ndcs': list(rxnorm_ndcs_in_group),
                'all_ndcs': all_ndcs_in_group
            }
            equivalence_links.append(link)
    
    print(f"  ✅ {len(equivalence_links):,} equivalence groups with RxNorm matches")
    print(f"  ✅ {total_linkable_ndcs:,} NDCs can be linked to RxNorm")
    
    print("\n[4/4] Saving results...")
    
    # Save equivalence links
    output_file = f"{OUTPUT_DIR}/equivalence_links.json"
    with open(output_file, 'w') as f:
        json.dump({
            'created': datetime.now().isoformat(),
            'stats': {
                'total_products': len(products),
                'total_equivalence_groups': len(groups),
                'rxnorm_ndcs_loaded': len(rxnorm_ndcs),
                'groups_with_rxnorm_match': rxnorm_linked_groups,
                'total_linkable_ndcs': total_linkable_ndcs
            },
            'equivalence_links': equivalence_links
        }, f, indent=2)
    print(f"  📁 Saved to {output_file}")
    
    # Save NDC to equivalence mapping
    ndc_map_file = f"{OUTPUT_DIR}/ndc_to_equivalence.json"
    with open(ndc_map_file, 'w') as f:
        json.dump(ndc_to_equivalence, f, indent=2)
    print(f"  📁 Saved NDC mapping to {ndc_map_file}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nRxNorm Coverage:")
    print(f"  RxNorm NDCs loaded: {len(rxnorm_ndcs):,}")
    print(f"  Equivalence groups with RxNorm match: {rxnorm_linked_groups:,}")
    print(f"  Total linkable NDCs: {total_linkable_ndcs:,}")
    
    print(f"\nCoverage Improvement:")
    print(f"  Before (direct RxNorm match only): ~12,826 NDCs")
    print(f"  After (equivalence-based linking): {total_linkable_ndcs:,} NDCs")
    print(f"  Improvement: {total_linkable_ndcs / 12826:.1f}x more NDCs linked!")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
