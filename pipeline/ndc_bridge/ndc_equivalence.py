#!/usr/bin/env python3
"""
NDC Equivalence System - Production Module
==========================================
Provides fast lookup for NDC-to-RxNorm linking via drug equivalence.

Usage:
    from ndc_equivalence import NDCEquivalence
    
    eq = NDCEquivalence()
    result = eq.lookup_ndc("55154-1234")
    # Returns: {'rxnorm_linked': True, 'equivalence_key': '...', 'linked_rxnorm_ndcs': [...]}
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime

# Paths
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
EQUIVALENCE_FILE = f"{BASE_DIR}/scripts/development/output/equivalence_links.json"
NDC_MAP_FILE = f"{BASE_DIR}/scripts/development/output/ndc_to_equivalence.json"

class NDCEquivalence:
    """
    NDC Equivalence Lookup System
    
    Links NDCs to RxNorm via drug equivalence (same ingredient+strength+form+route).
    Enables repackager NDCs to be linked to original manufacturer NDCs that are in RxNorm.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern for memory efficiency"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Load equivalence data on first use"""
        if not NDCEquivalence._initialized:
            self._load_data()
            NDCEquivalence._initialized = True
    
    def _load_data(self):
        """Load equivalence links and NDC mapping"""
        self.ndc_to_key = {}
        self.equivalence_groups = {}
        self.stats = {}
        
        # Load NDC to equivalence key mapping
        if os.path.exists(NDC_MAP_FILE):
            with open(NDC_MAP_FILE, 'r') as f:
                self.ndc_to_key = json.load(f)
        
        # Load equivalence links
        if os.path.exists(EQUIVALENCE_FILE):
            with open(EQUIVALENCE_FILE, 'r') as f:
                data = json.load(f)
                self.stats = data.get('stats', {})
                
                # Index by equivalence key for fast lookup
                for link in data.get('equivalence_links', []):
                    self.equivalence_groups[link['equivalence_key']] = link
    
    def lookup_ndc(self, ndc: str) -> Dict[str, Any]:
        """
        Look up an NDC and find its equivalence group and RxNorm links.
        
        Args:
            ndc: NDC code in any format (will be normalized)
            
        Returns:
            Dict with:
                - ndc: normalized NDC
                - found: whether NDC is in our database
                - rxnorm_linked: whether this NDC can be linked to RxNorm
                - equivalence_key: the drug equivalence key
                - linked_rxnorm_ndcs: list of NDCs in the same group that are in RxNorm
                - equivalent_ndcs: all NDCs in the same equivalence group
                - manufacturers: all manufacturers for this drug
        """
        from ndc_utils import normalize_ndc
        
        # Normalize NDC
        normalized = normalize_ndc(ndc)
        if not normalized:
            return {'ndc': ndc, 'found': False, 'error': 'Invalid NDC format'}
        
        result = {
            'ndc': normalized,
            'found': False,
            'rxnorm_linked': False,
            'equivalence_key': None,
            'linked_rxnorm_ndcs': [],
            'equivalent_ndcs': [],
            'manufacturers': []
        }
        
        # Find equivalence key
        eq_key = self.ndc_to_key.get(normalized)
        if not eq_key:
            return result
        
        result['found'] = True
        result['equivalence_key'] = eq_key
        
        # Get equivalence group
        group = self.equivalence_groups.get(eq_key)
        if group:
            result['rxnorm_linked'] = True
            result['linked_rxnorm_ndcs'] = group.get('rxnorm_ndcs', [])
            result['equivalent_ndcs'] = group.get('all_ndcs', [])
            result['manufacturers'] = list(set(
                p.get('manufacturer', '') for p in group.get('all_ndcs', [])
                if p.get('manufacturer')
            ))
        else:
            # NDC is in our database but not linked to RxNorm
            pass
        
        return result
    
    def get_equivalence_group(self, eq_key: str) -> Optional[Dict[str, Any]]:
        """Get all products in an equivalence group"""
        return self.equivalence_groups.get(eq_key)
    
    def find_equivalents(self, ndc: str) -> List[Dict[str, Any]]:
        """
        Find all equivalent NDCs for a given NDC.
        
        Returns list of dicts with ndc, manufacturer, product_name.
        """
        result = self.lookup_ndc(ndc)
        if not result['found']:
            return []
        return result.get('equivalent_ndcs', [])
    
    def is_rxnorm_linked(self, ndc: str) -> bool:
        """Check if an NDC can be linked to RxNorm via equivalence"""
        result = self.lookup_ndc(ndc)
        return result.get('rxnorm_linked', False)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the equivalence system"""
        return {
            'total_ndcs': len(self.ndc_to_key),
            'total_equivalence_groups': len(self.equivalence_groups),
            'rxnorm_linked_groups': self.stats.get('groups_with_rxnorm_match', 0),
            'total_linkable_ndcs': self.stats.get('total_linkable_ndcs', 0),
            'rxnorm_ndcs_loaded': self.stats.get('rxnorm_ndcs_loaded', 0)
        }


# Convenience function for quick lookups
_equivalence_instance = None

def lookup_ndc(ndc: str) -> Dict[str, Any]:
    """Quick lookup function for NDC equivalence"""
    global _equivalence_instance
    if _equivalence_instance is None:
        _equivalence_instance = NDCEquivalence()
    return _equivalence_instance.lookup_ndc(ndc)


def get_equivalence_stats() -> Dict[str, Any]:
    """Get equivalence system statistics"""
    global _equivalence_instance
    if _equivalence_instance is None:
        _equivalence_instance = NDCEquivalence()
    return _equivalence_instance.get_stats()


if __name__ == "__main__":
    # Demo / test
    print("=" * 70)
    print("NDC EQUIVALENCE SYSTEM - Demo")
    print("=" * 70)
    
    eq = NDCEquivalence()
    stats = eq.get_stats()
    
    print(f"\nSystem Statistics:")
    print(f"  Total NDCs: {stats['total_ndcs']:,}")
    print(f"  Equivalence groups: {stats['total_equivalence_groups']:,}")
    print(f"  RxNorm-linked groups: {stats['rxnorm_linked_groups']:,}")
    print(f"  Total linkable NDCs: {stats['total_linkable_ndcs']:,}")
    
    # Test lookups
    test_ndcs = [
        "55154-1234",  # Random repackager NDC
        "00071-0158",  # Pfizer Lipitor (should be in RxNorm)
        "76420-0009-01",  # Celecoxib from earlier example
    ]
    
    print(f"\nTest Lookups:")
    for ndc in test_ndcs:
        result = eq.lookup_ndc(ndc)
        print(f"\n  NDC: {ndc}")
        print(f"    Found: {result['found']}")
        print(f"    RxNorm linked: {result['rxnorm_linked']}")
        if result['equivalent_ndcs']:
            print(f"    Equivalent NDCs: {len(result['equivalent_ndcs'])}")
            print(f"    Manufacturers: {result['manufacturers'][:3]}...")
