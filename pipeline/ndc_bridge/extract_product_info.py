#!/usr/bin/env python3
"""
SPL Product Info Extractor
==========================
Extracts structured product information from SPL XML for drug equivalence matching:
- Active ingredients with strengths
- Dosage form
- Route of administration

This enables linking repackager NDCs to original manufacturer NDCs via product equivalence.
"""

import os
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import re

# Add production path for imports
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production')
from ndc_utils import normalize_ndc

# SPL namespace
SPL_NS = {'ns0': 'urn:hl7-org:v3'}

# RxNorm route code mappings (simplified)
ROUTE_CODE_MAP = {
    'C38288': 'oral',
    'C38295': 'rectal',
    'C38299': 'sublingual',
    'C38300': 'topical',
    'C38290': 'intravenous',
    'C38276': 'intramuscular',
    'C38284': 'inhalation',
    'C38287': 'nasal',
    'C38292': 'ophthalmic',
    'C38293': 'otic',
    'C38296': 'subcutaneous',
    'C38275': 'buccal',
    'C38298': 'transdermal',
    'C38277': 'intradermal',
    'C38279': 'intraarterial',
    'C38282': 'intraarticular',
    'C38283': 'intracardiac',
    'C38286': 'intrathecal',
    'C38289': 'intravesical',
    'C38291': 'urethral',
    'C38297': 'vaginal',
    'C60628': 'implantation',
    'C38238': 'injection',
}

# RxNorm dose form code mappings (simplified)
DOSE_FORM_MAP = {
    'C42998': 'tablet',
    'C42992': 'capsule',
    'C42974': 'injection',
    'C42981': 'solution',
    'C42982': 'suspension',
    'C42983': 'syrup',
    'C42984': 'elixir',
    'C42985': 'emulsion',
    'C42986': 'gel',
    'C42987': 'cream',
    'C42988': 'ointment',
    'C42989': 'lotion',
    'C42990': 'patch',
    'C42991': 'powder',
    'C42993': 'suppository',
    'C42994': 'spray',
    'C42995': 'aerosol',
    'C42996': 'inhalant',
    'C42999': 'film',
    'C43000': 'granule',
    'C43100': 'strip',
    'C43101': 'troche',
    'C43102': 'lozenge',
    'C43103': 'chewable tablet',
    'C43104': 'extended release',
    'C43105': 'delayed release',
    'C43106': 'coated',
    'C43107': 'film coated',
    'C60927': 'tablet, film coated',
    'C60928': 'tablet, extended release',
    'C60929': 'capsule, extended release',
    'C60930': 'capsule, delayed release',
}


def extract_text(element: ET.Element) -> str:
    """Extract text from an XML element."""
    if element is None:
        return ""
    text_parts = []
    if element.text:
        text_parts.append(element.text)
    for child in element:
        child_text = extract_text(child)
        if child_text:
            text_parts.append(child_text)
        if child.tail:
            text_parts.append(child.tail)
    return ' '.join(text_parts).strip()


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_strength(quantity_elem: ET.Element) -> Dict[str, Any]:
    """Parse strength from a quantity element."""
    strength = {}
    if quantity_elem is None:
        return strength
    
    # Try to get numerator/denominator for concentration
    numerator = quantity_elem.find('.//ns0:numerator', SPL_NS)
    denominator = quantity_elem.find('.//ns0:denominator', SPL_NS)
    
    if numerator is not None:
        value = numerator.get('value', '')
        unit = numerator.get('unit', '')
        strength['value'] = value
        strength['unit'] = unit
    
    if denominator is not None:
        denom_value = denominator.get('value', '')
        denom_unit = denominator.get('unit', '')
        strength['denominator_value'] = denom_value
        strength['denominator_unit'] = denom_unit
    
    # Also check for direct value attribute
    if not strength:
        value = quantity_elem.get('value', '')
        unit = quantity_elem.get('unit', '')
        if value:
            strength['value'] = value
            strength['unit'] = unit
    
    return strength


def extract_ingredients(root: ET.Element) -> List[Dict[str, Any]]:
    """
    Extract active ingredients with strengths from SPL XML.
    
    The structure is typically:
    <manufacturedProduct>
      <manufacturedMaterial>
        <ingredient>...</ingredient>
      </manufacturedMaterial>
    </manufacturedProduct>
    """
    ingredients = []
    
    # Find all ingredient elements
    for ingredient in root.findall('.//ns0:ingredient', SPL_NS):
        try:
            ing_data = {}
            
            # Get ingredient name
            name_elem = ingredient.find('.//ns0:name', SPL_NS)
            if name_elem is not None:
                ing_data['name'] = clean_text(extract_text(name_elem))
            
            # Get ingredient code (UNII code)
            code_elem = ingredient.find('.//ns0:code', SPL_NS)
            if code_elem is not None:
                ing_data['code'] = code_elem.get('code', '')
                ing_data['code_system'] = code_elem.get('codeSystem', '')
            
            # Get quantity/strength
            quantity_elem = ingredient.find('.//ns0:quantity', SPL_NS)
            if quantity_elem is not None:
                strength = parse_strength(quantity_elem)
                if strength:
                    ing_data['strength'] = strength
            
            # Check if this is an active ingredient
            # Look for classCode="ACTIB" or "ACTIM" for active ingredients
            class_code = ingredient.get('classCode', '')
            if class_code in ['ACTIB', 'ACTIM', 'ACTIR']:  # Active ingredient codes
                ing_data['type'] = 'active'
            else:
                ing_data['type'] = 'inactive'  # Default, may be inactive
            
            # Only include if we have a name
            if ing_data.get('name'):
                ingredients.append(ing_data)
                
        except Exception as e:
            continue
    
    # Also check for active ingredient specific paths
    if not any(i.get('type') == 'active' for i in ingredients):
        # Try manufacturedMaterial/ingredient path
        for mm_ingredient in root.findall('.//ns0:manufacturedMaterial/ns0:ingredient', SPL_NS):
            try:
                ing_data = {}
                
                name_elem = mm_ingredient.find('.//ns0:name', SPL_NS)
                if name_elem is not None:
                    ing_data['name'] = clean_text(extract_text(name_elem))
                
                code_elem = mm_ingredient.find('.//ns0:code', SPL_NS)
                if code_elem is not None:
                    ing_data['code'] = code_elem.get('code', '')
                
                quantity_elem = mm_ingredient.find('.//ns0:quantity', SPL_NS)
                if quantity_elem is not None:
                    strength = parse_strength(quantity_elem)
                    if strength:
                        ing_data['strength'] = strength
                
                ing_data['type'] = 'active'  # Assume active for this path
                
                if ing_data.get('name'):
                    ingredients.append(ing_data)
                    
            except Exception:
                continue
    
    return ingredients


def extract_dosage_form(root: ET.Element) -> Dict[str, Any]:
    """Extract dosage form from SPL XML."""
    dose_form = {}
    
    # Look for formCode element
    form_code_elem = root.find('.//ns0:formCode', SPL_NS)
    if form_code_elem is not None:
        code = form_code_elem.get('code', '')
        display_name = form_code_elem.get('displayName', '')
        
        dose_form['code'] = code
        dose_form['display_name'] = display_name
        
        # Map code to standard name
        if code in DOSE_FORM_MAP:
            dose_form['standard_name'] = DOSE_FORM_MAP[code]
        elif display_name:
            dose_form['standard_name'] = display_name.lower()
    
    return dose_form


def extract_routes(root: ET.Element) -> List[Dict[str, Any]]:
    """Extract routes of administration from SPL XML."""
    routes = []
    
    # Look for routeCode elements
    for route_elem in root.findall('.//ns0:routeCode', SPL_NS):
        try:
            route_data = {}
            
            code = route_elem.get('code', '')
            display_name = route_elem.get('displayName', '')
            
            route_data['code'] = code
            route_data['display_name'] = display_name
            
            # Map code to standard name
            if code in ROUTE_CODE_MAP:
                route_data['standard_name'] = ROUTE_CODE_MAP[code]
            elif display_name:
                route_data['standard_name'] = display_name.lower()
            
            if route_data.get('standard_name') and route_data not in routes:
                routes.append(route_data)
                
        except Exception:
            continue
    
    return routes


def extract_ndc_codes(root: ET.Element) -> List[str]:
    """Extract and normalize NDC codes from SPL XML."""
    ndc_codes = set()
    
    # Method 1: containerPackagedProduct/code
    for ndc in root.findall('.//ns0:containerPackagedProduct/ns0:code', SPL_NS):
        code = ndc.get('code', '')
        if code:
            normalized = normalize_ndc(code)
            if normalized:
                ndc_codes.add(normalized)
    
    # Method 2: manufacturedProduct/code with NDC code system
    for code_elem in root.findall('.//ns0:manufacturedProduct/ns0:code', SPL_NS):
        code_system = code_elem.get('codeSystem', '')
        if '2.16.840.1.113883.6.69' in code_system:  # NDC code system OID
            code = code_elem.get('code', '')
            if code:
                normalized = normalize_ndc(code)
                if normalized:
                    ndc_codes.add(normalized)
    
    return sorted(list(ndc_codes))


def extract_product_info(xml_path: str) -> Dict[str, Any]:
    """
    Extract all product information from an SPL XML file.
    Returns structured data for drug equivalence matching.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        return {'error': str(e), 'file': str(xml_path)}
    
    # Extract basic identifiers
    doc_id_elem = root.find('.//ns0:id', SPL_NS)
    set_id_elem = root.find('.//ns0:setId', SPL_NS)
    
    product_info = {
        'file_path': str(xml_path),
        'document_id': doc_id_elem.get('root', '') if doc_id_elem is not None else '',
        'set_id': set_id_elem.get('root', '') if set_id_elem is not None else '',
    }
    
    # Extract product name
    name_elem = root.find('.//ns0:manufacturedProduct/ns0:name', SPL_NS)
    if name_elem is not None:
        product_info['product_name'] = clean_text(extract_text(name_elem))
    else:
        # Fallback to title
        title_elem = root.find('.//ns0:title', SPL_NS)
        if title_elem is not None:
            product_info['product_name'] = clean_text(extract_text(title_elem))
    
    # Extract manufacturer
    mfr_elem = root.find('.//ns0:author//ns0:representedOrganization//ns0:name', SPL_NS)
    if mfr_elem is not None:
        product_info['manufacturer'] = clean_text(extract_text(mfr_elem))
    
    # Extract NDC codes
    product_info['ndc_codes'] = extract_ndc_codes(root)
    
    # Extract ingredients
    ingredients = extract_ingredients(root)
    product_info['ingredients'] = ingredients
    
    # Separate active and inactive ingredients
    product_info['active_ingredients'] = [
        i for i in ingredients if i.get('type') == 'active' or 'strength' in i
    ]
    product_info['inactive_ingredients'] = [
        i for i in ingredients if i.get('type') == 'inactive'
    ]
    
    # Extract dosage form
    product_info['dosage_form'] = extract_dosage_form(root)
    
    # Extract routes
    product_info['routes'] = extract_routes(root)
    
    # Create a normalized product key for equivalence matching
    product_info['equivalence_key'] = create_equivalence_key(product_info)
    
    return product_info


def create_equivalence_key(product_info: Dict[str, Any]) -> str:
    """
    Create a normalized key for drug equivalence matching.
    
    Format: ingredient1_strength|ingredient2_strength|dose_form|route
    
    This allows matching repackager NDCs to original manufacturer NDCs
    when they represent the same drug formulation.
    """
    key_parts = []
    
    # Add active ingredients (sorted for consistency)
    active_ings = product_info.get('active_ingredients', [])
    if active_ings:
        ing_strs = []
        for ing in sorted(active_ings, key=lambda x: x.get('name', '')):
            name = ing.get('name', '').lower()
            strength = ing.get('strength', {})
            if strength:
                value = strength.get('value', '')
                unit = strength.get('unit', '').lower()
                ing_strs.append(f"{name}_{value}{unit}")
            else:
                ing_strs.append(name)
        key_parts.append('|'.join(ing_strs))
    
    # Add dosage form
    dose_form = product_info.get('dosage_form', {})
    if dose_form.get('standard_name'):
        key_parts.append(dose_form['standard_name'])
    elif dose_form.get('display_name'):
        key_parts.append(dose_form['display_name'].lower())
    
    # Add routes
    routes = product_info.get('routes', [])
    if routes:
        route_strs = sorted([r.get('standard_name', r.get('display_name', '')).lower() for r in routes])
        key_parts.append('|'.join(route_strs))
    
    return '||'.join(key_parts)


def process_directory(xml_dir: str, output_file: str = None, limit: int = None) -> Dict[str, Any]:
    """
    Process all XML files in a directory and extract product info.
    
    Returns:
        Dictionary with:
        - products: List of product info dicts
        - equivalence_groups: Dict mapping equivalence keys to NDC lists
        - stats: Processing statistics
    """
    xml_path = Path(xml_dir)
    xml_files = list(xml_path.glob('*.xml'))
    
    if limit:
        xml_files = xml_files[:limit]
    
    print(f"Processing {len(xml_files)} XML files...")
    
    products = []
    equivalence_groups = defaultdict(list)  # key -> list of NDCs
    ndc_to_product = {}  # ndc -> product info
    
    stats = {
        'total_files': len(xml_files),
        'products_with_ingredients': 0,
        'products_with_dose_form': 0,
        'products_with_routes': 0,
        'products_with_ndc': 0,
        'unique_equivalence_keys': 0,
        'errors': 0
    }
    
    for i, xml_file in enumerate(xml_files):
        if (i + 1) % 1000 == 0:
            print(f"  Processed {i+1:,} / {len(xml_files):,} files...")
        
        try:
            product_info = extract_product_info(xml_file)
            
            if 'error' in product_info:
                stats['errors'] += 1
                continue
            
            products.append(product_info)
            
            # Track equivalence groups
            eq_key = product_info.get('equivalence_key', '')
            if eq_key:
                equivalence_groups[eq_key].append({
                    'ndc_codes': product_info.get('ndc_codes', []),
                    'product_name': product_info.get('product_name', ''),
                    'manufacturer': product_info.get('manufacturer', ''),
                    'set_id': product_info.get('set_id', '')
                })
            
            # Track stats
            if product_info.get('active_ingredients'):
                stats['products_with_ingredients'] += 1
            if product_info.get('dosage_form'):
                stats['products_with_dose_form'] += 1
            if product_info.get('routes'):
                stats['products_with_routes'] += 1
            if product_info.get('ndc_codes'):
                stats['products_with_ndc'] += 1
            
            # Build NDC index
            for ndc in product_info.get('ndc_codes', []):
                ndc_to_product[ndc] = product_info
                
        except Exception as e:
            stats['errors'] += 1
            continue
    
    stats['unique_equivalence_keys'] = len(equivalence_groups)
    
    result = {
        'products': products,
        'equivalence_groups': dict(equivalence_groups),
        'ndc_to_product': ndc_to_product,
        'stats': stats
    }
    
    if output_file:
        # Save to JSON (without the large ndc_to_product index)
        output_data = {
            'products': products,
            'equivalence_groups': dict(equivalence_groups),
            'stats': stats
        }
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"Saved to {output_file}")
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract product info from SPL XML files')
    parser.add_argument('--xml-dir', required=True, help='Directory containing SPL XML files')
    parser.add_argument('--output', default='product_info.json', help='Output JSON file')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    args = parser.parse_args()
    
    result = process_directory(args.xml_dir, args.output, args.limit)
    
    print("\n=== Extraction Summary ===")
    print(f"Total files processed: {result['stats']['total_files']:,}")
    print(f"Products with ingredients: {result['stats']['products_with_ingredients']:,}")
    print(f"Products with dose form: {result['stats']['products_with_dose_form']:,}")
    print(f"Products with routes: {result['stats']['products_with_routes']:,}")
    print(f"Products with NDC codes: {result['stats']['products_with_ndc']:,}")
    print(f"Unique equivalence keys: {result['stats']['unique_equivalence_keys']:,}")
    print(f"Errors: {result['stats']['errors']:,}")
