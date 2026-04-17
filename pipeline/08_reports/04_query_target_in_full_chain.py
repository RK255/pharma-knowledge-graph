#!/usr/bin/env python3
"""
Query Full Drug Chain for 5 Target IN Codes

This script queries the GRC-20 JSON data for all related data for 5 target IN codes:
- flucytosine (RxCUI 4451)
- cetirizine (RxCUI 20610)
- pseudoephedrine (RxCUI 8896)
- semaglutide (RxCUI 1991302)
- ibuprofen (RxCUI 5640)

For each IN code, it follows the chain:
IN → TTY codes (SCDG, SCD, SBD, BN) → NDC → SPL Set ID

And outputs all related data in a structured format.
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

# Target IN codes with their RxCUIs
TARGET_IN_CODES = {
    "flucytosine": {"rxcui": "4451", "entity_id": "d2ff0dcf6da85d9bae789afd06c9cd0d"},
    "cetirizine": {"rxcui": "20610", "entity_id": "044a579c57705bdeb05cf556f5446594"},
    "pseudoephedrine": {"rxcui": "8896", "entity_id": "51168cf4cc97573ebe40fa31a31394ba"},
    "semaglutide": {"rxcui": "1991302", "entity_id": "197d66802ab55e2791fe4e953d8377f5"},
    "ibuprofen": {"rxcui": "5640", "entity_id": "8cc3c5e12fa15df19b5ff158423da872"}
}

# Target TTY levels that have NDCs
TTYS_WITH_NDCS = {'SCD', 'SBD', 'BN', 'SCDG'}

# Property IDs (from actual GRC-20 entities)
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'

# Relationship types we want to follow (from actual data analysis)
# These are the types that connect ingredients to products
RELEVANT_REL_TYPES = {
    'd085f236da3c51fca583c72e7058973b',  # IN → SCDC/SCDF/SCDG (generic forms)
    'dbc766b554f0579da4c7b7c29924d6a3',  # IN → BN (brand names)
    '94272e15b3535feab43867d3b374f608',  # IN → MIN (multiple ingredients)
    'd3077c62a9875bfbace8602b42872f43',  # IN → PIN (precise ingredient)
    'dd9264e954d650f98f97cc5d471e5a51',  # SCDC/SCDF/SCDG → SCD (clinical drug)
    'c4243118788e5a739998e57dfb4c6723',  # SCD → SBD (clinical drug component)
    'b09f1b8e67c85a56ab88816eb58f3e56',  # BN → BPCK (brand package)
    '5a9d2c8f67c95e78ab7772c7113e6a34',  # BPCK → GPCK (generic package)
    'cbf90e604bf458719df7ad10fd90c07f',  # DF → SCD
    '12a84f5c305857b782821609c5e2b59b',  # Additional relationship type
}

def load_mappings():
    """Load all necessary mappings"""
    print("Loading mappings...")
    
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
    
    # Load DailyMed documents
    dailymed_file = DATA_DIR / "dailymed_documents.json"
    with open(dailymed_file, 'r') as f:
        dailymed_docs = json.load(f)
    
    # Create Set ID → DailyMed doc mapping
    setid_to_dailymed = {}
    for doc in dailymed_docs:
        set_id = doc.get("fda_set_id")
        if set_id:
            setid_to_dailymed[set_id] = doc
    print(f"  Loaded {len(setid_to_dailymed):,} Set ID → DailyMed mappings")
    
    # Load RxNorm entities (correct structure)
    rxnorm_entities = {}
    rxnorm_file = DATA_DIR / "rxnorm_entities.jsonl"
    if Path(rxnorm_file).exists():
        with open(rxnorm_file, 'r') as f:
            for line in f:
                entity = json.loads(line)
                entity_id = entity.get("id")
                if entity_id:
                    rxnorm_entities[entity_id] = entity
        print(f"  Loaded {len(rxnorm_entities):,} RxNorm entities")
    else:
        print(f"  Warning: RxNorm entities file not found")
    
    # Load RxNorm relations (correct structure)
    rxnorm_relations = []
    relations_file = DATA_DIR / "rxnorm_relations.jsonl"
    if Path(relations_file).exists():
        with open(relations_file, 'r') as f:
            for line in f:
                relation = json.loads(line)
                rxnorm_relations.append(relation)
        print(f"  Loaded {len(rxnorm_relations):,} RxNorm relations")
    else:
        print(f"  Warning: RxNorm relations file not found")
    
    return ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities, rxnorm_relations

def get_entity_property(entity, property_id):
    """Get a property value from an entity by property ID"""
    if not entity or 'values' not in entity:
        return None
    for prop in entity['values']:
        if prop.get('property') == property_id:
            return prop.get('value')
    return None

def get_entity_name(entity):
    """Get the name of an entity"""
    name = get_entity_property(entity, PROP_NAME)
    if name:
        return name
    return entity.get('id', 'Unknown')

def get_entity_rxcui(entity):
    """Get the RxCUI of an entity"""
    return get_entity_property(entity, PROP_RXCUI)

def get_entity_tty(entity):
    """Get the TTY of an entity"""
    return get_entity_property(entity, PROP_TTY)

def build_relation_index(rxnorm_relations):
    """Build an index of relations by target entity (using 'to' field)"""
    index = defaultdict(list)
    for relation in rxnorm_relations:
        target_id = relation.get('to')
        if target_id:
            rel_type = relation.get('type')
            source_id = relation.get('from')
            index[target_id].append({
                'rel_type': rel_type,
                'source_id': source_id
            })
    return index

def walk_downstream(entity_id, rxnorm_entities, relation_index, visited=None, max_depth=3):
    """
    Walk downstream from an entity to find all related entities.
    
    Args:
        entity_id: The starting entity ID
        rxnorm_entities: Dictionary of all RxNorm entities
        relation_index: Index of relations by target entity
        visited: Set of already visited entity IDs (to avoid cycles)
        max_depth: Maximum depth to traverse
        
    Returns:
        Dictionary mapping entity IDs to their properties
    """
    if visited is None:
        visited = set()
    
    if entity_id in visited or max_depth <= 0:
        return {}
    
    visited.add(entity_id)
    results = {}
    
    # Get all relations pointing to this entity
    relations = relation_index.get(entity_id, [])
    
    for rel_info in relations:
        rel_type = rel_info['rel_type']
        source_id = rel_info['source_id']
        
        # Check if this is a relevant relationship type
        if rel_type in RELEVANT_REL_TYPES:
            # Get the source entity
            source_entity = rxnorm_entities.get(source_id)
            if not source_entity:
                continue
            
            # Add to results
            results[source_id] = {
                'tty': get_entity_tty(source_entity),
                'rxcui': get_entity_rxcui(source_entity),
                'name': get_entity_name(source_entity),
                'rel_type': rel_type
            }
            
            # Recursively walk downstream
            downstream_results = walk_downstream(
                source_id, 
                rxnorm_entities, 
                relation_index, 
                visited.copy(),
                max_depth - 1
            )
            results.update(downstream_results)
    
    return results

def walk_in_chain(in_name, in_rxcui, in_entity_id, ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities, relation_index):
    """
    Walk the full chain for a single IN code.
    
    Returns:
        Dictionary with all related data for the IN code
    """
    print(f"  Walking chain for: {in_name} (RxCUI {in_rxcui})")
    
    # Collect all related entities by walking downstream
    all_entities = walk_downstream(in_entity_id, rxnorm_entities, relation_index, max_depth=3)
    
    print(f"    Found {len(all_entities)} total entities (including downstream)")
    
    # Separate by type
    tty_nodes = []
    rxcuis = []
    ndcs = []
    setids = []
    dailymed_docs = []
    
    for entity_id, entity_info in all_entities.items():
        tty = entity_info['tty']
        rxcui = entity_info['rxcui']
        name = entity_info['name']
        rel_type = entity_info['rel_type']
        
        tty_nodes.append({
            "entity_id": entity_id,
            "tty": tty,
            "rxcui": rxcui,
            "name": name,
            "rel_type_id": rel_type
        })
        
        if rxcui:
            rxcuis.append({
                "rxcui": rxcui,
                "name": name,
                "tty": tty
            })
        
        # If this TTY has NDCs, look them up
        if tty in TTYS_WITH_NDCS and rxcui:
            # Find NDCs for this RxCUI
            for ndc_code, ndc_rxcui in ndc_to_rxcui.items():
                if ndc_rxcui == rxcui:
                    # Get Set ID for this NDC
                    set_id = ndc_to_setid.get(ndc_code)
                    
                    ndcs.append({
                        "ndc": ndc_code,
                        "rxcui": rxcui,
                        "set_id": set_id
                    })
                    
                    # If we have a Set ID, look up the DailyMed doc
                    if set_id and set_id in setid_to_dailymed:
                        dailymed_doc = setid_to_dailymed[set_id]
                        dailymed_docs.append({
                            "set_id": set_id,
                            "ndc": ndc_code,
                            "title": dailymed_doc.get('title', ''),
                            "sections": len(dailymed_doc.get('sections', []))
                        })
                        setids.append({
                            "set_id": set_id,
                            "ndc": ndc_code,
                            "title": dailymed_doc.get('title', '')
                        })
    
    print(f"    ✓ Found {len(tty_nodes)} TTY nodes")
    print(f"    ✓ Found {len(rxcuis)} RxCUIs")
    print(f"    ✓ Found {len(ndcs)} NDCs")
    print(f"    ✓ Found {len(setids)} Set IDs")
    print(f"    ✓ Found {len(dailymed_docs)} DailyMed docs")
    
    # Group TTY nodes by type
    tty_by_type = defaultdict(list)
    for tty in tty_nodes:
        tty_by_type[tty['tty']].append(tty)
    
    return {
        "in_code": in_name,
        "in_rxcui": in_rxcui,
        "in_entity_id": in_entity_id,
        "tty_nodes": tty_nodes,
        "tty_by_type": dict(tty_by_type),
        "rxcuis": rxcuis,
        "ndcs": ndcs,
        "setids": setids,
        "dailymed_docs": dailymed_docs,
        "total_tty_nodes": len(tty_nodes),
        "total_rxcuis": len(rxcuis),
        "total_ndcs": len(ndcs),
        "total_setids": len(setids),
        "total_dailymed_docs": len(dailymed_docs)
    }

def main():
    """
    Main function to query all target IN codes.
    """
    
    print("=" * 80)
    print("QUERY FULL DRUG CHAIN FOR 5 TARGET IN CODES")
    print("=" * 80)
    print(f"Target IN codes: {list(TARGET_IN_CODES.keys())}")
    print(f"Target TTY codes: {TTYS_WITH_NDCS}")
    print("=" * 80)
    
    # Load mappings
    ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities, rxnorm_relations = load_mappings()
    
    # Build relation index
    print("\nBuilding relation index...")
    relation_index = build_relation_index(rxnorm_relations)
    print(f"  Indexed {len(relation_index)} target entities")
    
    results = []
    
    for in_name, in_info in TARGET_IN_CODES.items():
        in_rxcui = in_info['rxcui']
        in_entity_id = in_info['entity_id']
        
        print(f"\n{'='*80}")
        print(f"Querying: {in_name} (RxCUI {in_rxcui})")
        print('='*80)
        
        result = walk_in_chain(in_name, in_rxcui, in_entity_id, ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities, relation_index)
        results.append(result)
    
    # Save results
    print("\n" + "=" * 80)
    print("QUERY COMPLETE")
    print("=" * 80)
    print(f"Total IN codes processed: {len(results)}")
    print(f"Successful: {sum(1 for r in results if 'error' not in r)}")
    print(f"Errors: {sum(1 for r in results if 'error' in r)}")
    print("=" * 80)
    
    # Print summary
    for result in results:
        if 'error' not in result:
            print(f"\n{result['in_code']} (RxCUI {result['in_rxcui']}):")
            print(f"  TTY Nodes: {result['total_tty_nodes']}")
            print(f"  RxCUIs: {result['total_rxcuis']}")
            print(f"  NDCs: {result['total_ndcs']}")
            print(f"  Set IDs: {result['total_setids']}")
            print(f"  DailyMed Docs: {result['total_dailymed_docs']}")
            
            # Show TTY breakdown
            if result['tty_by_type']:
                print(f"  TTY breakdown:")
                for tty_type, tty_list in result['tty_by_type'].items():
                    print(f"    {tty_type}: {len(tty_list)}")
                    for tty in tty_list[:3]:  # Show first 3
                        print(f"      - {tty['rxcui']}: {tty['name']}")
                    if len(tty_list) > 3:
                        print(f"      ... and {len(tty_list) - 3} more")
    
    # Save to JSON file
    output_file = DATA_DIR / "target_in_full_chain_data.json"
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()

