#!/usr/bin/env python3
"""
NDC Utilities Module
====================
Reusable NDC normalization and handling logic.
Import this module in all NDC-related scripts.

Usage:
    from ndc_utils import normalize_ndc, NDCNormalizer
"""

import re
from typing import Optional, Set, Dict, List


def normalize_ndc(ndc_str: str, format: str = "5-4-2") -> Optional[str]:
    """
    Normalize ANY NDC format to standard format.
    
    Handles:
    - 11-digit (no hyphens): 59050026800 → 59050-0268-00
    - 5-4-2 hyphenated: 59050-0268-00 → 59050-0268-00
    - 5-3-2 hyphenated: 59050-268-00 → 59050-0268-00 (pad middle)
    - 4-4-2 hyphenated: 0869-0871-18 → 08690-0871-18 (pad first)
    - 5-4-1 hyphenated: 59050-268-0 → 59050-0268-00 (pad last)
    - 10-digit (no hyphens): assumes 5-3-2 → 5-4-2
    
    Args:
        ndc_str: NDC string in any format
        format: Output format ("5-4-2" is default/standard)
    
    Returns:
        Normalized NDC string or None if invalid
    """
    if not ndc_str:
        return None
    
    # Clean input
    clean = ndc_str.strip().replace("-", "").replace(" ", "")
    
    # Validate digits only
    if not clean.isdigit():
        return None
    
    # Handle different lengths
    if len(clean) == 11:
        # Standard 11-digit - already correct
        labeler = clean[:5]
        product = clean[5:9]
        package = clean[9:]
    elif len(clean) == 10:
        # 10-digit - need to determine original format
        # Parse original to understand padding
        parts = ndc_str.strip().split('-')
        if len(parts) == 3:
            p1, p2, p3 = parts
            if len(p1) == 5 and len(p2) == 3:
                # 5-3-2 format - pad middle
                labeler = clean[:5]
                product = clean[5:8].zfill(4)
                package = clean[8:]
            elif len(p1) == 4 and len(p2) == 4:
                # 4-4-2 format - pad first
                labeler = clean[:4].zfill(5)
                product = clean[4:8]
                package = clean[8:]
            else:
                # Default: assume 5-3-2
                labeler = clean[:5]
                product = clean[5:8].zfill(4)
                package = clean[8:]
        else:
            # No hyphens - assume 5-3-2
            labeler = clean[:5]
            product = clean[5:8].zfill(4)
            package = clean[8:]
    elif len(clean) == 9:
        # 9-digit - assume 5-3-1, pad last two
        labeler = clean[:5]
        product = clean[5:8].zfill(4)
        package = clean[8:].zfill(2)
    else:
        # Invalid length
        return None
    
    # Format output
    if format == "5-4-2":
        return f"{labeler}-{product}-{package}"
    elif format == "11-digit":
        return f"{labeler}{product}{package}"
    elif format == "no-hyphens":
        return f"{labeler}{product}{package}"
    else:
        return f"{labeler}-{product}-{package}"


def get_labeler(ndc: str) -> Optional[str]:
    """Extract the 5-digit labeler code from an NDC."""
    normalized = normalize_ndc(ndc)
    if normalized:
        return normalized.split('-')[0]
    return None


def get_product(ndc: str) -> Optional[str]:
    """Extract the 4-digit product code from an NDC."""
    normalized = normalize_ndc(ndc)
    if normalized:
        return normalized.split('-')[1]
    return None


def get_package(ndc: str) -> Optional[str]:
    """Extract the 2-digit package code from an NDC."""
    normalized = normalize_ndc(ndc)
    if normalized:
        return normalized.split('-')[2]
    return None


def ndcs_same_product(ndc1: str, ndc2: str) -> bool:
    """Check if two NDCs represent the same product (ignore package code)."""
    n1 = normalize_ndc(ndc1)
    n2 = normalize_ndc(ndc2)
    if not n1 or not n2:
        return False
    # Compare first 9 digits (labeler + product)
    return n1[:10].replace('-', '') == n2[:10].replace('-', '')


class NDCNormalizer:
    """
    Batch NDC normalization with caching.
    
    Usage:
        normalizer = NDCNormalizer()
        normalized = normalizer.normalize("59050026800")
        stats = normalizer.get_stats()
    """
    
    def __init__(self):
        self._cache: Dict[str, Optional[str]] = {}
        self._stats = {
            'total': 0,
            'normalized': 0,
            'failed': 0,
            'cache_hits': 0
        }
    
    def normalize(self, ndc: str) -> Optional[str]:
        """Normalize an NDC with caching."""
        self._stats['total'] += 1
        
        # Check cache
        if ndc in self._cache:
            self._stats['cache_hits'] += 1
            return self._cache[ndc]
        
        # Normalize
        result = normalize_ndc(ndc)
        
        if result:
            self._stats['normalized'] += 1
        else:
            self._stats['failed'] += 1
        
        # Cache result
        self._cache[ndc] = result
        return result
    
    def normalize_batch(self, ndcs: List[str]) -> Dict[str, Optional[str]]:
        """Normalize a batch of NDCs."""
        return {ndc: self.normalize(ndc) for ndc in ndcs}
    
    def get_stats(self) -> Dict[str, int]:
        """Get normalization statistics."""
        return self._stats.copy()
    
    def clear_cache(self):
        """Clear the normalization cache."""
        self._cache.clear()
        self._stats = {
            'total': 0,
            'normalized': 0,
            'failed': 0,
            'cache_hits': 0
        }


class NDCSet:
    """
    Efficient NDC set operations with normalization.
    
    Usage:
        rxnorm_ndcs = NDCSet()
        rxnorm_ndcs.load_from_file("rxnorm_ndcs.txt")
        
        if rxnorm_ndcs.contains("59050-0268-00"):
            print("Found!")
    """
    
    def __init__(self):
        self._ndcs: Set[str] = set()
        self._normalizer = NDCNormalizer()
    
    def add(self, ndc: str) -> bool:
        """Add an NDC to the set (normalized)."""
        normalized = self._normalizer.normalize(ndc)
        if normalized:
            self._ndcs.add(normalized)
            return True
        return False
    
    def contains(self, ndc: str) -> bool:
        """Check if an NDC is in the set (normalized comparison)."""
        normalized = self._normalizer.normalize(ndc)
        return normalized in self._ndcs if normalized else False
    
    def load_from_file(self, filepath: str, delimiter: str = '\t'):
        """Load NDCs from a file (one per line, optional tab-delimited source)."""
        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split(delimiter)
                if parts:
                    self.add(parts[0])
        return self
    
    def __len__(self) -> int:
        return len(self._ndcs)
    
    def __contains__(self, ndc: str) -> bool:
        return self.contains(ndc)
    
    def __iter__(self):
        return iter(self._ndcs)
    
    def intersection(self, other: 'NDCSet') -> Set[str]:
        """Get intersection with another NDCSet."""
        return self._ndcs & other._ndcs
    
    def difference(self, other: 'NDCSet') -> Set[str]:
        """Get difference with another NDCSet."""
        return self._ndcs - other._ndcs


# Convenience function for quick normalization
def norm(ndc: str) -> Optional[str]:
    """Quick normalize function."""
    return normalize_ndc(ndc)


if __name__ == "__main__":
    # Test normalization
    test_cases = [
        ("59050026800", "59050-0268-00"),  # 11-digit
        ("59050-0268-00", "59050-0268-00"),  # 5-4-2
        ("59050-268-00", "59050-0268-00"),  # 5-3-2
        ("0869-0871-18", "00869-0871-18"),  # 4-4-2
        ("00002-0152-01", "00002-0152-01"),  # Already normalized
        (" 00002015201 ", "00002-0152-01"),  # With spaces
    ]
    
    print("NDC Normalization Tests:")
    print("-" * 60)
    for input_ndc, expected in test_cases:
        result = normalize_ndc(input_ndc)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{input_ndc}' → '{result}' (expected: '{expected}')")
