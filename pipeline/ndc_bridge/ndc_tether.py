#!/usr/bin/env python3
"""
NDC Tether System - Links SPL Package Inserts to RxNorm RxCUIs
===============================================================
Uses NDC as the tether between:
- SPL Package Inserts (DailyMed) → NDCs
- RxNorm Drug Concepts → NDCs

Creates relationships:
(:PackageInsert)-[:DESCRIBES_DRUG]->(:Drug {rxcui: ...})
"""

import json
import os
import sys
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime

# Add production path
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production')
from ndc_utils import normalize_ndc
from ndc_rxcui_lookup import NDCRxCUILookup

# Paths
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/raw_data"
OUTPUT_DIR = f"{BASE_DIR}/scripts/development/output"


class NDCTether:
    """
    Links SPL Package Inserts to RxNorm RxCUIs via NDC.
    """
    
    def __init__(self):
        """Initialize with NDC lookup and product info"""
        print("=" * 70)
        print("NDC TETHER SYSTEM")
        print("=" * 70)
        
        # Load NDC → RxCUI lookup
        print("\n[1/3] Loading NDC → RxCUI lookup...")
        self.lookup = NDCRxCUILookup()
        
        # Load product info (SPL → NDCs)
        print("\n[2/3] Loading SPL Product Info...")
        self.products = {}  # set_id → product info
        self.ndc_to_set_ids = defaultdict(list)  # NDC → set_ids
        
        product_file = f"{OUTPUT_DIR}/product_info_full.json"
        if os.path.exists(product_file):
            with open(product_file, 'r') as f:
                data = json.load(f)
                
                for product in data.get('products', []):
                    set_id = product.get('set_id')
                    if set_id:
                        self.products[set_id] = product
                        
                        # Index by NDC
                        for ndc in product.get('ndc_codes', []):
                            normalized = normalize_ndc(ndc)
                            if normalized and set_id not in self.ndc_to_set_ids[normalized]:
                                self.ndc_to_set_ids[normalized].append(set_id)
            
            print(f"  ✅ Loaded {len(self.products):,} products")
            print(f"  ✅ Indexed {len(self.ndc_to_set_ids):,} NDCs")
        
        # Build tether relationships
        self.tethers = {}  # set_id → {rxcuis, ndcs, match_types}
    
    def build_tethers(self) -> Dict[str, Any]:
        """
        Build tether relationships from SPL to RxCUI.
        
        Returns dict with:
        - tethers: set_id → {rxcuis, ndcs, match_info}
        - stats: tethering statistics
        """
        print("\n[3/3] Building tethers...")
        
        stats = {
            'total_products': len(self.products),
            'products_with_rxcui': 0,
            'products_without_rxcui': 0,
            'direct_matches': 0,
            'equivalence_matches': 0,
            'no_match': 0,
            'multiple_rxcuis': 0,
            'total_rxcui_links': 0
        }
        
        for set_id, product in self.products.items():
            ndcs = product.get('ndc_codes', [])
            product_rxcuis = set()
            product_matches = []
            
            for ndc in ndcs:
                normalized = normalize_ndc(ndc)
                if not normalized:
                    continue
                
                result = self.lookup.lookup(normalized)
                
                if result.get('rxcui'):
                    product_rxcuis.add(result['rxcui'])
                    product_matches.append({
                        'ndc': normalized,
                        'rxcui': result['rxcui'],
                        'match_type': result['match_type'],
                        'linked_via': result.get('linked_via_ndc')
                    })
                    
                    stats['total_rxcui_links'] += 1
                    if result['match_type'] == 'direct':
                        stats['direct_matches'] += 1
                    else:
                        stats['equivalence_matches'] += 1
            
            # Store tether info
            self.tethers[set_id] = {
                'rxcuis': list(product_rxcuis),
                'ndcs': ndcs,
                'matches': product_matches,
                'product_name': product.get('product_name'),
                'manufacturer': product.get('manufacturer')
            }
            
            if product_rxcuis:
                stats['products_with_rxcui'] += 1
                if len(product_rxcuis) > 1:
                    stats['multiple_rxcuis'] += 1
            else:
                stats['products_without_rxcui'] += 1
                stats['no_match'] += 1
        
        # Calculate coverage
        stats['coverage_pct'] = (stats['products_with_rxcui'] / stats['total_products'] * 100) if stats['total_products'] > 0 else 0
        
        print(f"\n  ✅ Tethered {stats['products_with_rxcui']:,} / {stats['total_products']:,} products ({stats['coverage_pct']:.1f}%)")
        print(f"     Direct matches: {stats['direct_matches']:,}")
        print(f"     Equivalence matches: {stats['equivalence_matches']:,}")
        print(f"     No match: {stats['no_match']:,}")
        
        return {'tethers': self.tethers, 'stats': stats}
    
    def get_rxcui_for_set_id(self, set_id: str) -> List[str]:
        """Get all RxCUIs for a package insert"""
        tether = self.tethers.get(set_id, {})
        return tether.get('rxcuis', [])
    
    def get_set_ids_for_rxcui(self, rxcui: str) -> List[str]:
        """Get all package inserts for an RxCUI"""
        set_ids = []
        for set_id, tether in self.tethers.items():
            if rxcui in tether.get('rxcuis', []):
                set_ids.append(set_id)
        return set_ids
    
    def get_tether(self, set_id: str) -> Optional[Dict]:
        """Get full tether info for a package insert"""
        return self.tethers.get(set_id)
    
    def export_for_neo4j(self, output_dir: str = None) -> Dict[str, str]:
        """
        Export tether relationships for Neo4j import.
        
        Creates:
        - package_insert_rxcui_relationships.csv: For importing relationships
        """
        if output_dir is None:
            output_dir = f"{BASE_DIR}/data/import_csvs"
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Export relationships
        rel_file = f"{output_dir}/package_insert_rxcui_relationships.csv"
        
        with open(rel_file, 'w') as f:
            f.write("set_id,rxcui,match_type,ndc,linked_via,product_name\n")
            
            for set_id, tether in self.tethers.items():
                for match in tether.get('matches', []):
                    f.write(f"{set_id},{match['rxcui']},{match['match_type']},{match['ndc']},{match.get('linked_via') or ''},\"{tether.get('product_name', '')}\"\n")
        
        print(f"\n📁 Exported relationships to {rel_file}")
        
        # Export summary
        summary_file = f"{output_dir}/tether_summary.json"
        with open(summary_file, 'w') as f:
            json.dump({
                'created': datetime.now().isoformat(),
                'stats': self.build_tethers().get('stats', {}),
                'sample_tethers': dict(list(self.tethers.items())[:5])
            }, f, indent=2)
        
        print(f"📁 Exported summary to {summary_file}")
        
        return {'relationships': rel_file, 'summary': summary_file}
    
    def print_sample_tethers(self, n: int = 5):
        """Print sample tethers for verification"""
        print("\n" + "=" * 70)
        print("SAMPLE TETHERS")
        print("=" * 70)
        
        # Show some with direct matches
        direct_samples = [(sid, t) for sid, t in self.tethers.items() 
                          if any(m['match_type'] == 'direct' for m in t.get('matches', []))][:n]
        
        # Show some with equivalence matches
        equiv_samples = [(sid, t) for sid, t in self.tethers.items() 
                         if any(m['match_type'] == 'equivalence' for m in t.get('matches', []))][:n]
        
        print("\n--- Direct Matches ---")
        for set_id, tether in direct_samples:
            print(f"\nSet ID: {set_id}")
            print(f"  Product: {tether.get('product_name', 'N/A')}")
            print(f"  RxCUIs: {tether['rxcuis']}")
            print(f"  NDCs: {tether['ndcs'][:3]}...")
            for m in tether.get('matches', [])[:2]:
                print(f"    {m['ndc']} → {m['rxcui']} ({m['match_type']})")
        
        print("\n--- Equivalence Matches (Repackagers) ---")
        for set_id, tether in equiv_samples:
            print(f"\nSet ID: {set_id}")
            print(f"  Product: {tether.get('product_name', 'N/A')}")
            print(f"  Manufacturer: {tether.get('manufacturer', 'N/A')}")
            print(f"  RxCUIs: {tether['rxcuis']}")
            for m in tether.get('matches', [])[:2]:
                if m['match_type'] == 'equivalence':
                    print(f"    {m['ndc']} → {m['rxcui']} (via {m.get('linked_via', 'N/A')})")


# Singleton instance
_tether_instance = None

def get_tether() -> NDCTether:
    """Get singleton tether instance"""
    global _tether_instance
    if _tether_instance is None:
        _tether_instance = NDCTether()
        _tether_instance.build_tethers()
    return _tether_instance


def get_rxcui_for_set_id(set_id: str) -> List[str]:
    """Quick lookup: set_id → RxCUIs"""
    tether = get_tether()
    return tether.get_rxcui_for_set_id(set_id)


if __name__ == "__main__":
    tether = NDCTether()
    tether.build_tethers()
    tether.print_sample_tethers()
    tether.export_for_neo4j()
