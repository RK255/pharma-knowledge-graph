#!/usr/bin/env python3
"""
Production Export: IN → Intermediate TTY → NDC → Set ID → Package Insert

Generates a comprehensive JSON file for bulk import by the GEO SDK.
Contains the complete chain for all ingredients in the target list.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

# Target ingredients list
TARGET_INGREDIENTS = [
    "Ivermectin",
    "Acetaminophen",
    "Ibuprofen",
    "Lisinopril",
    "Metformin",
    "Amlodipine",
    "Omeprazole",
    "Atorvastatin",
    "Losartan",
    "Gabapentin",
    "Metoprolol",
    "Levothyroxine"
]

# Property IDs
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'

# Relationship types for filtering
RELEVANT_REL_TYPES = {
    '708910ff645b507ab5616dbd680b5802',  # IN → SCDF/SCDC
    'a42836a8c04757e1a995531b8ff3200b',  # IN → BN
    '1df119c2ba785c688aafd35556e3fab6',  # IN → MIN
    'dd9264e954d650f98f97cc5d471e5a51',  # SCDC/SCDF → SCD
    '12a84f5c305857b782821609c5e2b59b',  # BN → SBD
    'd085f236da3c51fca583c72e7058973b',  # SCDC/SCDF → SCDG
    'dbc766b554f0579da4c7b7c29924d6a3',  # BN → GPCK
}

# TTY levels that have NDCs
TTYS_WITH_NDCS = {'SCD', 'SBD', 'BPCK', 'GPCK'}

def load_data():
    """Load all necessary data"""
    print("Loading data...")
    
    # Load NDC → Set ID mapping
    setid_file = RAW_DATA_DIR / "ndc_to_setid_final_v3.json"
    with open(setid_file, 'r') as f:
        setid_data = json.load(f)
    ndc_to_setid = setid_data['ndc_to_setid']
    print(f"  Loaded {len(ndc_to_setid):,} NDC → Set ID mappings")
    
    # Load NDC → RxCUI mapping
    rxcui_file = RAW_DATA_DIR / "ndc_to_rxcui.json"
    with open(rxcui_file, 'r') as f:
        rxcui_data = json.load(f)
    ndc_to_rxcui = rxcui_data['ndc_to_rxcui']
    print(f"  Loaded {len(ndc_to_rxcui):,} NDC → RxCUI mappings")
    
    # Create RxCUI → NDCs mapping
    rxcui_to_ndcs = defaultdict(list)
    for ndc, rxcui in ndc_to_rxcui.items():
        if isinstance(rxcui, list):
            for r in rxcui:
                rxcui_to_ndcs[str(r)].append(ndc)
        else:
            rxcui_to_ndcs[str(rxcui)].append(ndc)
    print(f"  Built RxCUI → NDCs mapping: {len(rxcui_to_ndcs):,} RxCUIs")
    
    # Load RxNorm entities
    rxnorm_entities = {}
    rxcui_to_tty = {}
    rxcui_to_name = {}
    
    rxnorm_file = DATA_DIR / "rxnorm_entities.jsonl"
    with open(rxnorm_file, 'r') as f:
        for line in f:
            entity = json.loads(line)
            rxnorm_entities[entity['id']] = entity
            
            rxcui = None
            tty = None
            name = None
            
            for val in entity.get('values', []):
                prop = val.get('property')
                value = val.get('value')
                
                if prop == PROP_RXCUI:
                    rxcui = value
                elif prop == PROP_TTY:
                    tty = value
                elif prop == PROP_NAME:
                    name = value
            
            if rxcui:
                if tty:
                    rxcui_to_tty[str(rxcui)] = tty
                if name:
                    rxcui_to_name[str(rxcui)] = name
    
    print(f"  Loaded {len(rxnorm_entities):,} RxNorm entities")
    
    # Load RxNorm relationships with filtering
    rel_graph = defaultdict(list)
    
    rel_file = DATA_DIR / "rxnorm_relations.jsonl"
    with open(rel_file, 'r') as f:
        for line in f:
            rel = json.loads(line)
            
            from_id = rel.get('from')
            to_id = rel.get('to')
            rel_type = rel.get('type')
            
            if rel_type not in RELEVANT_REL_TYPES:
                continue
            
            from_rxcui = None
            to_rxcui = None
            
            if from_id in rxnorm_entities:
                for val in rxnorm_entities[from_id].get('values', []):
                    if val.get('property') == PROP_RXCUI:
                        from_rxcui = str(val.get('value'))
                        break
            
            if to_id in rxnorm_entities:
                for val in rxnorm_entities[to_id].get('values', []):
                    if val.get('property') == PROP_RXCUI:
                        to_rxcui = str(val.get('value'))
                        break
            
            if not from_rxcui or not to_rxcui:
                continue
            
            rel_graph[from_rxcui].append((to_rxcui, rel_type))
    
    print(f"  Built filtered relationship graph: {len(rel_graph):,} source RxCUIs")
    
    # Load DailyMed documents
    dailymed_file = DATA_DIR / "dailymed_documents.json"
    with open(dailymed_file, 'r') as f:
        dailymed_docs = json.load(f)
    
    setid_to_dailymed = {}
    for doc in dailymed_docs:
        set_id = doc.get("fda_set_id")
        if set_id:
            setid_to_dailymed[set_id] = doc
    print(f"  Loaded {len(setid_to_dailymed):,} Set ID → DailyMed mappings")
    
    return {
        'ndc_to_setid': ndc_to_setid,
        'ndc_to_rxcui': ndc_to_rxcui,
        'rxcui_to_ndcs': rxcui_to_ndcs,
        'rxcui_to_tty': rxcui_to_tty,
        'rxcui_to_name': rxcui_to_name,
        'rel_graph': rel_graph,
        'setid_to_dailymed': setid_to_dailymed
    }

def walk_in_to_products(in_rxcui, data):
    """Walk from IN RxCUI to products with NDCs"""
    visited = set()
    queue = [(in_rxcui, 0)]
    products = []
    
    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > 3:
            continue
        
        visited.add(current)
        
        # Check if this RxCui has NDCs
        if current in data['rxcui_to_ndcs']:
            tty = data['rxcui_to_tty'].get(current, "UNKNOWN")
            if tty in TTYS_WITH_NDCS:
                products.append({
                    'product_rxcui': current,
                    'product_tty': tty,
                    'product_name': data['rxcui_to_name'].get(current, "Unknown")
                })
        
        # Add neighbors to queue
        if current in data['rel_graph']:
            for neighbor, rel_type in data['rel_graph'][current]:
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
    
    return products

def export_ingredient_data(ingredient_name, data):
    """Export data for a single ingredient"""
    # Find IN RxCUI by name
    in_rxcui = None
    in_full_name = None
    
    for rxcui, name in data['rxcui_to_name'].items():
        if ingredient_name.lower() in name.lower() and data['rxcui_to_tty'].get(rxcui) == 'IN':
            in_rxcui = rxcui
            in_full_name = name
            break
    
    if not in_rxcui:
        print(f"  ❌ IN '{ingredient_name}' not found")
        return None
    
    # Walk to products
    products = walk_in_to_products(in_rxcui, data)
    
    # For each product, get NDCs and package inserts
    products_with_ndcs = []
    total_ndcs = 0
    
    for product in products:
        ndcs = data['rxcui_to_ndcs'].get(product['product_rxcui'], [])
        if not ndcs:
            continue
        
        ndc_data = []
        for ndc in ndcs:
            total_ndcs += 1
            set_id = data['ndc_to_setid'].get(ndc)
            
            package_insert = None
            if set_id:
                dailymed_doc = data['setid_to_dailymed'].get(set_id)
                if dailymed_doc:
                    package_insert = {
                        'title': dailymed_doc.get('title', 'N/A'),
                        'effective_date': dailymed_doc.get('effective_time', 'N/A'),
                        'set_id': set_id
                    }
            
            ndc_data.append({
                'ndc': ndc,
                'set_id': set_id,
                'package_insert': package_insert
            })
        
        if ndc_data:
            product['ndcs'] = ndc_data
            products_with_ndcs.append(product)
    
    return {
        'ingredient_name': in_full_name,
        'ingredient_rxcui': in_rxcui,
        'products': products_with_ndcs,
        'total_products': len(products_with_ndcs),
        'total_ndcs': total_ndcs
    }

def main():
    print("=" * 80)
    print("PRODUCTION EXPORT: IN → PRODUCTS → NDCs → SET IDs → PACKAGE INSERTS")
    print("=" * 80)
    
    data = load_data()
    
    # Export data for all target ingredients
    ingredients_data = []
    total_products = 0
    total_ndcs = 0
    
    for ingredient in TARGET_INGREDIENTS:
        print(f"\nProcessing: {ingredient}")
        ingredient_data = export_ingredient_data(ingredient, data)
        
        if ingredient_data:
            ingredients_data.append(ingredient_data)
            total_products += ingredient_data['total_products']
            total_ndcs += ingredient_data['total_ndcs']
            print(f"  ✅ Found {ingredient_data['total_products']} products, {ingredient_data['total_ndcs']} NDCs")
    
    # Create export object
    export = {
        'version': '1.0',
        'generated_at': datetime.now().isoformat(),
        'metadata': {
            'total_ingredients': len(ingredients_data),
            'total_products': total_products,
            'total_ndcs': total_ndcs,
            'ingredients': [i['ingredient_name'] for i in ingredients_data]
        },
        'ingredients': ingredients_data
    }
    
    # Save to file
    output_file = BASE_DIR / "data" / "grc20_v2" / "production_export.json"
    with open(output_file, 'w') as f:
        json.dump(export, f, indent=2)
    
    print("\n" + "=" * 80)
    print("EXPORT COMPLETE")
    print("=" * 80)
    print(f"  Ingredients: {len(ingredients_data)}")
    print(f"  Products: {total_products:,}")
    print(f"  NDCs: {total_ndcs:,}")
    print(f"  Output file: {output_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
