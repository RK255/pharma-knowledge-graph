#!/usr/bin/env python3
"""
NDC → RxCUI Lookup System - Production Module
==============================================
Complete NDC to RxCUI lookup with:
1. Direct mapping from RxNorm (242K NDCs)
2. Equivalence-based linking for repackagers (111K additional NDCs)

Usage:
    from ndc_rxcui_lookup import NDCRxCUILookup
    
    lookup = NDCRxCUILookup()
    result = lookup.lookup("55154-1234")
    # Returns: {'rxcui': '123456', 'match_type': 'direct'|'equivalence', ...}
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime

# Paths
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/raw_data"

# Add production path for normalize_ndc
import sys
sys.path.insert(0, f'{BASE_DIR}/scripts/production')
from ndc_utils import normalize_ndc


class NDCRxCUILookup:
    """
    Two-tier NDC → RxCUI lookup:
    1. Direct: NDC → RxCUI (from RxNorm RXNSAT)
    2. Equivalence: NDC → Equivalent NDC → RxCUI (from DailyMed SPL)
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not NDCRxCUILookup._initialized:
            self._load_data()
            NDCRxCUILookup._initialized = True
    
    def _load_data(self):
        """Load all NDC mappings"""
        print("Loading NDC → RxCUI lookup system...")
        
        # Tier 1: Direct RxNorm NDC → RxCUI
        self.ndc_to_rxcui = {}
        self.rxcui_to_ndcs = {}
        
        ndc_rxcui_file = f"{DATA_DIR}/ndc_to_rxcui.json"
        if os.path.exists(ndc_rxcui_file):
            with open(ndc_rxcui_file, 'r') as f:
                data = json.load(f)
                self.ndc_to_rxcui = data.get('ndc_to_rxcui', {})
                self.rxcui_to_ndcs = data.get('rxcui_to_ndcs', {})
            print(f"  ✅ Direct mappings: {len(self.ndc_to_rxcui):,} NDCs → {len(self.rxcui_to_ndcs):,} RxCUIs")
        
        # Tier 2: Equivalence-based linking
        self.ndc_to_equivalence = {}
        self.equivalence_groups = {}
        
        equiv_map_file = f"{BASE_DIR}/scripts/development/output/ndc_to_equivalence.json"
        equiv_links_file = f"{BASE_DIR}/scripts/development/output/equivalence_links.json"
        
        if os.path.exists(equiv_map_file):
            with open(equiv_map_file, 'r') as f:
                self.ndc_to_equivalence = json.load(f)
            print(f"  ✅ Equivalence map: {len(self.ndc_to_equivalence):,} NDCs")
        
        if os.path.exists(equiv_links_file):
            with open(equiv_links_file, 'r') as f:
                data = json.load(f)
                for link in data.get('equivalence_links', []):
                    self.equivalence_groups[link['equivalence_key']] = link
            print(f"  ✅ Equivalence groups: {len(self.equivalence_groups):,}")
        
        # Calculate coverage
        direct_ndcs = set(self.ndc_to_rxcui.keys())
        equiv_ndcs = set(self.ndc_to_equivalence.keys())
        overlap = direct_ndcs & equiv_ndcs
        equiv_only = equiv_ndcs - direct_ndcs
        
        self.stats = {
            'direct_ndcs': len(direct_ndcs),
            'equivalence_ndcs': len(equiv_ndcs),
            'overlap': len(overlap),
            'equivalence_only': len(equiv_only),
            'total_coverage': len(direct_ndcs) + len(equiv_only),
            'direct_rxcuis': len(self.rxcui_to_ndcs)
        }
        
        print(f"  ✅ Total coverage: {self.stats['total_coverage']:,} NDCs")
    
    def lookup(self, ndc: str) -> Dict[str, Any]:
        """
        Look up an NDC and find its RxCUI.
        
        Returns:
            {
                'ndc': normalized NDC,
                'rxcui': RxCUI if found,
                'match_type': 'direct'|'equivalence'|None,
                'equivalence_key': key if equivalence match,
                'equivalent_ndcs': list of equivalent NDCs,
                'linked_via_ndc': NDC used for equivalence link
            }
        """
        normalized = normalize_ndc(ndc)
        if not normalized:
            return {'ndc': ndc, 'error': 'Invalid NDC format', 'rxcui': None}
        
        result = {
            'ndc': normalized,
            'rxcui': None,
            'match_type': None,
            'equivalence_key': None,
            'equivalent_ndcs': [],
            'linked_via_ndc': None
        }
        
        # Tier 1: Direct match
        if normalized in self.ndc_to_rxcui:
            result['rxcui'] = self.ndc_to_rxcui[normalized]
            result['match_type'] = 'direct'
            return result
        
        # Tier 2: Equivalence match
        eq_key = self.ndc_to_equivalence.get(normalized)
        if eq_key:
            result['equivalence_key'] = eq_key
            group = self.equivalence_groups.get(eq_key)
            
            if group:
                result['equivalent_ndcs'] = group.get('all_ndcs', [])
                result['match_type'] = 'equivalence'
                
                # Find RxCUI via linked RxNorm NDCs
                for linked_ndc in group.get('rxnorm_ndcs', []):
                    if linked_ndc in self.ndc_to_rxcui:
                        result['rxcui'] = self.ndc_to_rxcui[linked_ndc]
                        result['linked_via_ndc'] = linked_ndc
                        break
        
        return result
    
    def lookup_rxcui(self, rxcui: str) -> List[str]:
        """Get all NDCs for a given RxCUI"""
        return self.rxcui_to_ndcs.get(rxcui, [])
    
    def get_equivalent_ndcs(self, ndc: str) -> List[str]:
        """Get all NDCs equivalent to the given NDC"""
        result = self.lookup(ndc)
        return [n['ndc'] for n in result.get('equivalent_ndcs', [])]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        return self.stats.copy()


# Singleton instance
_lookup_instance = None

def lookup_ndc(ndc: str) -> Dict[str, Any]:
    """Quick NDC lookup"""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = NDCRxCUILookup()
    return _lookup_instance.lookup(ndc)

def get_stats() -> Dict[str, Any]:
    """Get lookup statistics"""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = NDCRxCUILookup()
    return _lookup_instance.get_stats()


if __name__ == "__main__":
    print("=" * 70)
    print("NDC → RxCUI LOOKUP SYSTEM - Demo")
    print("=" * 70)
    
    lookup = NDCRxCUILookup()
    stats = lookup.get_stats()
    
    print(f"\nSystem Statistics:")
    print(f"  Direct NDC→RxCUI: {stats['direct_ndcs']:,}")
    print(f"  Equivalence NDCs: {stats['equivalence_ndcs']:,}")
    print(f"  Overlap: {stats['overlap']:,}")
    print(f"  Equivalence-only (repackagers): {stats['equivalence_only']:,}")
    print(f"  Total coverage: {stats['total_coverage']:,}")
    print(f"  Direct RxCUIs: {stats['direct_rxcuis']:,}")
    
    # Test lookups with real NDCs from our data
    print(f"\n" + "=" * 70)
    print("TEST LOOKUPS")
    print("=" * 70)
    
    test_ndcs = [
        ("59050-0268-00", "Direct RxNorm NDC"),
        ("76420-0009-01", "Celecoxib (equivalence)"),
        ("84280-0120-01", "Tamsulosin repackager"),
        ("50090-0247-09", "Sulfamethoxazole repackager"),
    ]
    
    for ndc, desc in test_ndcs:
        result = lookup.lookup(ndc)
        print(f"\n{desc}:")
        print(f"  NDC: {result['ndc']}")
        print(f"  Match type: {result['match_type']}")
        print(f"  RxCUI: {result['rxcui']}")
        if result.get('linked_via_ndc'):
            print(f"  Linked via: {result['linked_via_ndc']}")
        if result.get('equivalent_ndcs'):
            print(f"  Equivalent NDCs: {len(result['equivalent_ndcs'])}")
