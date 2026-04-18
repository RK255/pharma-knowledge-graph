#!/usr/bin/env python3
"""
Walk the path: IN → Target TTYs (SCD, SCDG, SBD, BN) → SCD/SBD/BPCK/GPCK → NDCs → Set ID → Package Insert

Filters relationships by type to avoid walking through unrelated drugs.
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

# Target TTY levels that have NDCs
TTYS_WITH_NDCS = {'SCD', 'SBD', 'BPCK', 'GPCK'}

# Property IDs (from actual GRC-20 entities)
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'

# Relationship types we want to follow (based on analysis)
# These are the types that connect ingredients to products
RELEVANT_REL_TYPES = {
    '708910ff645b507ab5616dbd680b5802',  # IN → SCDF/SCDC (generic forms)
    'a42836a8c04757e1a995531b8ff3200b',  # IN → BN (brand names)
    '1df119c2ba785c688aafd35556e3fab6',  # IN → MIN (multiple ingredients)
    'dd9264e954d650f98f97cc5d471e5a51',  # SCDC/SCDF → SCD (clinical drug)
    '12a84f5c305857b782821609c5e2b59b',  # BN → SBD (branded drug)
    'd085f236da3c51fca583c72e7058973b',  # SCDC/SCDF → SCDG (generic pack)
    'dbc766b554f0579da4c7b7c29924d6a3',  # BN → GPCK (generic pack)
}

def load_data():
    """Load all necessary data from our existing datasets"""
    print("Loading data from existing datasets...")
    
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
    
    # Create RxCUI → NDCs mapping (reverse)
    rxcui_to_ndcs = defaultdict(list)
    for ndc, rxcui in ndc_to_rxcui.items():
        # Handle list or single value
        if isinstance(rxcui, list):
            for r in rxcui:
                rxcui_to_ndcs[str(r)].append(ndc)
        else:
            rxcui_to_ndcs[str(rxcui)].append(ndc)
    print(f"  Built RxCUI → NDCs mapping: {len(rxcui_to_ndcs):,} RxCUIs")
    
    # Load RxNorm entities from GRC-20
    rxnorm_entities = {}
    rxcui_to_entity = {}
    rxcui_to_tty = {}
    rxcui_to_name = {}
    
    rxnorm_file = DATA_DIR / "rxnorm_entities.jsonl"
    if rxnorm_file.exists():
        print(f"  Loading RxNorm entities from {rxnorm_file}...")
        with open(rxnorm_file, 'r') as f:
            for line in f:
                entity = json.loads(line)
                rxnorm_entities[entity['id']] = entity
                
                # Extract RxCUI, TTY, and name
                rxcui = None
                tty = None
                name = None
                
                for val in entity.get('values', []):
                    prop = val.get('property')
                    value = val.get('value')
                    
                    if prop == PROP_RXCUI:
                        rxcui = value
                        rxcui_to_entity[str(rxcui)] = entity['id']
                    elif prop == PROP_TTY:
                        tty = value
                    elif prop == PROP_NAME:
                        name = value
                
                if rxcui:
                    if tty:
                        rxcui_to_tty[str(rxcui)] = tty
                    if name:
                        rxcui_to_name[str(rxcui)] = name
        
        print(f"    Loaded {len(rxnorm_entities):,} RxNorm entities")
        print(f"    Extracted {len(rxcui_to_tty):,} RxCUI → TTY mappings")
        print(f"    Extracted {len(rxcui_to_name):,} RxCUI → Name mappings")
    
    # Load RxNorm relationships with type filtering
    print(f"  Loading RxNorm relationships...")
    
    # Build relationship graph with type filtering
    rel_graph = defaultdict(list)  # from_rxcui → [(to_rxcui, rel_type)]
    
    rel_file = DATA_DIR / "rxnorm_relations.jsonl"
    if rel_file.exists():
        with open(rel_file, 'r') as f:
            for line in f:
                rel = json.loads(line)
                
                # Get source and target entity IDs
                from_id = rel.get('from')
                to_id = rel.get('to')
                rel_type = rel.get('type')
                
                # Only load relevant relationship types
                if rel_type not in RELEVANT_REL_TYPES:
                    continue
                
                # Get RxCUIs for source and target
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
                
                # Add to graph
                rel_graph[from_rxcui].append((to_rxcui, rel_type))
        
        print(f"    Built filtered relationship graph: {len(rel_graph):,} source RxCUIs")
        total_edges = sum(len(targets) for targets in rel_graph.values())
        print(f"    Total edges in filtered graph: {total_edges:,}")
    
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
        'rxnorm_entities': rxnorm_entities,
        'rxcui_to_entity': rxcui_to_entity,
        'rxcui_to_tty': rxcui_to_tty,
        'rxcui_to_name': rxcui_to_name,
        'rel_graph': rel_graph,
        'setid_to_dailymed': setid_to_dailymed
    }

def walk_in_to_setid(in_name, data):
    """Walk from IN name to Set IDs"""
    print("\n" + "=" * 80)
    print(f"WALKING FROM IN: {in_name}")
    print("=" * 80 + "\n")
    
    # Find IN RxCUI by name
    in_rxcui = None
    in_full_name = None
    
    for rxcui, name in data['rxcui_to_name'].items():
        if in_name.lower() in name.lower() and data['rxcui_to_tty'].get(rxcui) == 'IN':
            in_rxcui = rxcui
            in_full_name = name
            break
    
    if not in_rxcui:
        print(f"❌ IN '{in_name}' not found")
        return
    
    print(f"IN: {in_full_name} (RxCUI: {in_rxcui})\n")
    
    # Use BFS to find all reachable RxCUIs with NDCs
    visited = set()
    queue = [(in_rxcui, 0)]  # (rxcui, depth)
    reachable_rxcuis = []
    
    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > 3:  # Limit depth to 3 hops
            continue
        
        visited.add(current)
        
        # Check if this RxCui has NDCs
        if current in data['rxcui_to_ndcs']:
            tty = data['rxcui_to_tty'].get(current, "UNKNOWN")
            reachable_rxcuis.append((current, tty, depth))
        
        # Add neighbors to queue
        if current in data['rel_graph']:
            for neighbor, rel_type in data['rel_graph'][current]:
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
    
    print(f"Found {len(reachable_rxcuis):,} RxCUIs with NDCs reachable from this IN\n")
    
    if not reachable_rxcuis:
        print("❌ No RxCUIs with NDCs found reachable from this IN")
        return
    
    # Group by TTY
    tty_groups = defaultdict(list)
    for rxcui, tty, depth in reachable_rxcuis:
        tty_groups[tty].append((rxcui, depth))
    
    # For each TTY group, show the path
    for tty in sorted(tty_groups.keys()):
        if tty not in TTYS_WITH_NDCS:
            continue
            
        print(f"{'=' * 80}")
        print(f"TTY: {tty} ({len(tty_groups[tty]):,} RxCUIs)")
        print(f"{'=' * 80}\n")
        
        # Show first few examples
        for i, (rxcui, depth) in enumerate(tty_groups[tty][:5], 1):
            name = data['rxcui_to_name'].get(rxcui, "Unknown")
            print(f"  {i}. {name} (RxCUI: {rxcui}, depth: {depth})")
            
            # Get NDCs
            ndcs = data['rxcui_to_ndcs'].get(rxcui, [])
            print(f"     NDCs: {len(ndcs):,}")
            
            if ndcs:
                # Get Set IDs for these NDCs
                setids = set()
                for ndc in ndcs:
                    setid = data['ndc_to_setid'].get(ndc)
                    if setid:
                        setids.add(setid)
                
                print(f"     Set IDs: {len(setids):,}")
                
                if setids:
                    # Show first Set ID and its Package Insert
                    first_setid = list(setids)[0]
                    dailymed_doc = data['setid_to_dailymed'].get(first_setid)
                    if dailymed_doc:
                        print(f"     Package Insert: {dailymed_doc.get('title', 'N/A')}")
                        print(f"     Effective Date: {dailymed_doc.get('effective_time', 'N/A')}")
                else:
                    print(f"     ❌ No Set IDs for this RxCUI's NDCs")
            else:
                print(f"     ❌ No NDCs for this RxCUI")
            
            print()
        
        if len(tty_groups[tty]) > 5:
            print(f"  ... and {len(tty_groups[tty]) - 5} more RxCUIs\n")

def main():
    print("=" * 80)
    print("WALKING IN → TARGET TTYS → NDCs → SET ID (WITH RELATIONSHIP FILTERING)")
    print("=" * 80)
    
    data = load_data()
    
    # Test with common ingredients
    test_ingredients = ["Hydrogen Peroxide", "Acetaminophen", "Ibuprofen", "Lisinopril", "Metformin"]
    
    for ingredient in test_ingredients:
        walk_in_to_setid(ingredient, data)

if __name__ == "__main__":
    main()
