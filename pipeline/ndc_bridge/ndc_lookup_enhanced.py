#!/usr/bin/env python3
"""
Enhanced NDC Lookup - Production Integration
=============================================
Combines direct RxNorm matching with equivalence-based linking.

This is the main entry point for NDC lookups in your knowledge graph.
"""

import sys
import os
from typing import Dict, List, Optional, Any, Tuple

# Add paths
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production')

from ndc_utils import normalize_ndc
from ndc_equivalence import NDCEquivalence

# Load RxNorm NDC to RxCUI mapping
RXNORM_NDC_FILE = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/ndc_normalized_v2.txt"

class EnhancedNDCLookup:
    """
    Two-tier NDC lookup:
    1. Direct match: NDC → RxNorm RxCUI
    2. Equivalence match: NDC → Equivalent NDC → RxNorm RxCUI
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not EnhancedNDCLookup._initialized:
            self._load_data()
            EnhancedNDCLookup._initialized = True
    
    def _load_data(self):
        """Load RxNorm NDCs and equivalence system"""
        print("Loading NDC lookup system...")
        
        # Load RxNorm NDCs (direct matches)
        self.rxnorm_ndc_to_rxcui = {}
        self.rxnorm_ndcs = set()
        
        if os.path.exists(RXNORM_NDC_FILE):
            with open(RXNORM_NDC_FILE, 'r') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        ndc = normalize_ndc(parts[0])
                        rxcui = parts[1] if len(parts) > 1 else None
                        if ndc:
                            self.rxnorm_ndcs.add(ndc)
                            if rxcui:
                                self.rxnorm_ndc_to_rxcui[ndc] = rxcui
            print(f"  ✅ Loaded {len(self.rxnorm_ndcs):,} RxNorm NDCs")
        
        # Load equivalence system
        self.equivalence = NDCEquivalence()
        eq_stats = self.equivalence.get_stats()
        print(f"  ✅ Loaded equivalence system: {eq_stats['total_linkable_ndcs']:,} linkable NDCs")
    
    def lookup(self, ndc: str) -> Dict[str, Any]:
        """
        Lookup an NDC with both direct and equivalence matching.
        
        Returns:
            {
                'ndc': normalized NDC,
                'direct_match': True/False,
                'equivalence_match': True/False,
                'rxcui': RxCUI if found,
                'match_type': 'direct'|'equivalence'|None,
                'equivalence_key': equivalence key if matched,
                'equivalent_ndcs': list of equivalent NDCs,
                'manufacturers': list of manufacturers
            }
        """
        normalized = normalize_ndc(ndc)
        if not normalized:
            return {'ndc': ndc, 'error': 'Invalid NDC format', 'direct_match': False}
        
        result = {
            'ndc': normalized,
            'direct_match': False,
            'equivalence_match': False,
            'rxcui': None,
            'match_type': None,
            'equivalence_key': None,
            'equivalent_ndcs': [],
            'manufacturers': []
        }
        
        # Tier 1: Direct RxNorm match
        if normalized in self.rxnorm_ndcs:
            result['direct_match'] = True
            result['match_type'] = 'direct'
            result['rxcui'] = self.rxnorm_ndc_to_rxcui.get(normalized)
            return result
        
        # Tier 2: Equivalence match
        eq_result = self.equivalence.lookup_ndc(normalized)
        if eq_result.get('rxnorm_linked'):
            result['equivalence_match'] = True
            result['match_type'] = 'equivalence'
            result['equivalence_key'] = eq_result.get('equivalence_key')
            result['equivalent_ndcs'] = eq_result.get('equivalent_ndcs', [])
            result['manufacturers'] = eq_result.get('manufacturers', [])
            
            # Find RxCUI from linked RxNorm NDCs
            linked_ndcs = eq_result.get('linked_rxnorm_ndcs', [])
            for linked_ndc in linked_ndcs:
                if linked_ndc in self.rxnorm_ndc_to_rxcui:
                    result['rxcui'] = self.rxnorm_ndc_to_rxcui[linked_ndc]
                    result['linked_via_ndc'] = linked_ndc
                    break
        
        return result
    
    def batch_lookup(self, ndcs: List[str]) -> Dict[str, Dict]:
        """Lookup multiple NDCs at once"""
        return {ndc: self.lookup(ndc) for ndc in ndcs}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        eq_stats = self.equivalence.get_stats()
        return {
            'rxnorm_direct_ndcs': len(self.rxnorm_ndcs),
            'equivalence_linkable_ndcs': eq_stats['total_linkable_ndcs'],
            'total_coverage': len(self.rxnorm_ndcs) + eq_stats['total_linkable_ndcs'] - eq_stats['rxnorm_linked_groups'],
            'equivalence_groups': eq_stats['total_equivalence_groups']
        }


# Quick lookup function
_lookup_instance = None

def lookup_ndc(ndc: str) -> Dict[str, Any]:
    """Quick NDC lookup"""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = EnhancedNDCLookup()
    return _lookup_instance.lookup(ndc)


def get_ndc_lookup_stats() -> Dict[str, Any]:
    """Get lookup system statistics"""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = EnhancedNDCLookup()
    return _lookup_instance.get_stats()


if __name__ == "__main__":
    print("=" * 70)
    print("ENHANCED NDC LOOKUP - Demo")
    print("=" * 70)
    
    lookup = EnhancedNDCLookup()
    stats = lookup.get_stats()
    
    print(f"\nSystem Coverage:")
    print(f"  Direct RxNorm matches: {stats['rxnorm_direct_ndcs']:,}")
    print(f"  Equivalence-linked NDCs: {stats['equivalence_linkable_ndcs']:,}")
    print(f"  Total NDCs covered: {stats['total_coverage']:,}")
    
    # Test some lookups
    test_ndcs = [
        ("76420-0009-01", "Celecoxib (should link via equivalence)"),
        ("67877-0450-01", "Tamsulosin (should link via equivalence)"),
        ("00071-0158", "Lipitor (might be direct)"),
    ]
    
    print(f"\nTest Lookups:")
    for ndc, desc in test_ndcs:
        result = lookup.lookup(ndc)
        print(f"\n  {desc}")
        print(f"    NDC: {ndc}")
        print(f"    Match type: {result['match_type']}")
        print(f"    Direct match: {result['direct_match']}")
        print(f"    Equivalence match: {result['equivalence_match']}")
        print(f"    RxCUI: {result.get('rxcui', 'N/A')}")
        if result.get('linked_via_ndc'):
            print(f"    Linked via: {result['linked_via_ndc']}")
        if result.get('manufacturers'):
            print(f"    Manufacturers: {len(result['manufacturers'])}")
