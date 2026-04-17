#!/usr/bin/env python3
"""
Step 13: Extract Data for Geo Import - CORRECTED RxNorm DOCUMENTED FLOW VERSION

Extracts entities mapped to the existing Geo ontology using the EXACT RxNorm documented flow.

CRITICAL DISCOVERY - RELATIONSHIP FILE DIRECTION:
The relationship file stores ALL relationships in FORWARD direction!

CRITICAL DISCOVERY - UNDOCUMENTED RELATIONSHIP TYPES:
During investigation, we discovered several undocumented relationship types:
- dd9264e954d650f98f97cc5d471e5a51: SCDF/SCDG -> SCD (appears to be "constitutes" variant)
- cbf90e604bf458719df7ad10fd90c07f: DF -> SCD (appears to be "has_dose_form")
- dbc766b554f0579da4c7b7c29924d6a3: SBD -> SCD (appears to be "tradename_of")
- 1df119c2ba785c688aafd35556e3fab6: IN -> MIN (undocumented)
- 94272e15b3535feab43867d3b374f608: MIN -> IN/PIN (undocumented)
- f44019f93b2258119d1022c4f39b9da5: MIN -> SCD (undocumented)
- 12a84f5c305857b782821609c5e2b59b: SCD -> SCDG/TMSY (undocumented)
- b74d6b2005505263a22c10fe0ed1f591: DFG -> SCDG (undocumented)

CRITICAL FIX - FILTER OUT SECONDARY CODES:
TMSY, PSN, and SY are secondary/auxiliary codes that cause false connections.
They MUST be BLOCKED from our capture to ensure data quality.
- TMSY: Typographic Match String (secondary representation)
- PSN: Prescribable Name (secondary representation)
- SY: Synonym (secondary representation)

CRITICAL FIX - MIN DIRECT SCD CONNECTIONS:
MINs connect DIRECTLY to SCDs via f44019f93b2258119d1022c4f39b9da5, not just through intermediate nodes!
Example: hydrochlorothiazide / losartan MIN connects directly to SCDs like:
  - hydrochlorothiazide 12.5 MG / losartan potassium 100 MG Oral Tablet (RxCUI: 979464)
  - hydrochlorothiazide 12.5 MG / losartan potassium 50 MG Oral Tablet (RxCUI: 979468)

CRITICAL FIX - CAPTURE ALL SCDs:
We must capture ALL SCDs, even those without NDCs. Some SCDs are valid concepts
even if they don't have NDCs in our current mapping.

CRITICAL FIX - NO OVERLAP BETWEEN BLOCKED AND ALLOWED:
BLOCKED_TTYS (TMSY, PSN, SY) MUST NOT be in ALLOWED_TTYS. This ensures clear,
non-conflicting filtering logic.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"
CID_MAPPING_FILE = DATA_DIR / "pubchem_cid_mapping.json"
ENRICHED_ENTITIES_FILE = DATA_DIR / "rxnorm_entities_enriched.jsonl"


# Target ingredients list - with VERIFIED IN RxCUIs from entity data
TARGET_INGREDIENTS = {
    "Ivermectin": "6069",
    "Acetaminophen": "161",
    "Ibuprofen": "5640",
    "Lisinopril": "29046",
    "Metformin": "6809",
    "Amlodipine": "17767",
    "Omeprazole": "7646",
    "Atorvastatin": "83367",
    "Losartan": "52175",
    "Gabapentin": "25480",
    "Metoprolol": "6918",
    "Levothyroxine": "10582"
}

# Property IDs
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'

# RxNorm DOCUMENTED relationship types (EXACT IDs from schema)
REL_HAS_FORM = '3df206ec784d51c5a1bf724192b70a95'
REL_FORM_OF = 'd3077c62a9875bfbace8602b42872f43'
REL_HAS_INGREDIENT = 'd085f236da3c51fca583c72e7058973b'
REL_INGREDIENT_OF = '708910ff645b507ab5616dbd680b5802'
REL_PRECISE_INGREDIENT_OF = '9147c85a51ea5a2481824d2aefe5956d'
REL_HAS_PRECISE_INGREDIENT = '307907247a3c5be682ed242bb61a2947'
REL_HAS_TRADENAME = 'a42836a8c04757e1a995531b8ff3200b'
REL_TRADENAME_OF = 'dbc766b554f0579da4c7b7c29924d6a3'
REL_CONSISTS_OF = '88c43b5be4eb5fe78b09872e9a9c3c70'
REL_CONSTITUTES = 'f5e289c3d13a5aaaa38b22448f7e38ab'

# UNDOCUMENTED relationship types discovered through investigation
REL_IN_TO_MIN = '1df119c2ba785c688aafd35556e3fab6'  # IN -> MIN
REL_MIN_TO_INGREDIENT = '94272e15b3535feab43867d3b374f608'  # MIN -> IN/PIN
REL_MIN_TO_SCD = 'f44019f93b2258119d1022c4f39b9da5'  # MIN -> SCD
REL_SCDG_SCDF_TO_SCD = 'dd9264e954d650f98f97cc5d471e5a51'  # SCDF/SCDG -> SCD
REL_DF_TO_SCD = 'cbf90e604bf458719df7ad10fd90c07f'  # DF -> SCD
REL_SCD_TO_SCDG_TMSY = '12a84f5c305857b782821609c5e2b59b'  # SCD -> SCDG/TMSY
REL_DFG_TO_SCDG = 'b74d6b2005505263a22c10fe0ed1f591'  # DFG -> SCDG

# CRITICAL: TTY types we ALLOW in our traversal
# NOTE: BLOCKED_TTYS (TMSY, PSN, SY) are NOT in this list!
ALLOWED_TTYS = {
    'PIN',
    'IN',
    'MIN',
    'SCDC',
    'SCDF',
    'SCDG',
    'SBDC',
    'SBDF',
    'BN',
    'SCD',
    'SBD',
    'GPCK',
    'BPCK',
    'DF'
}

# CRITICAL: BLOCK all secondary/auxiliary codes that cause false connections
BLOCKED_TTYS = {
    'TMSY',  # Typographic Match String - secondary representation
    'PSN',   # Prescribable Name - secondary representation
    'SY',    # Synonym - secondary representation
}

# Geo ontology types
GEO_TYPES = {
    'INGREDIENT': 'Ingredient',
    'PRECISE_INGREDIENT': 'Precise Ingredient',
    'MULTIPLE_INGREDIENT': 'Multiple Ingredient',
    'SCD': 'Semantic Clinical Drug',
    'SBD': 'Semantic Branded Drug',
    'BN': 'Brand Name',
    'SCDG': 'Semantic Clinical Dose Group',
    'NDC': 'NDC'
}

def load_data():
    """Load all necessary data"""
    print("Loading data...")
    
    # Load NDC -> Set ID mapping
    setid_file = RAW_DATA_DIR / "ndc_to_setid_final_v3.json"
    with open(setid_file, 'r') as f:
        setid_data = json.load(f)
    ndc_to_setid = setid_data['ndc_to_setid']
    print(f"  Loaded {len(ndc_to_setid):,} NDC -> Set ID mappings")
    
    # Load NDC -> RxCUI mapping
    rxcui_file = RAW_DATA_DIR / "ndc_to_rxcui.json"
    with open(rxcui_file, 'r') as f:
        rxcui_data = json.load(f)
    ndc_to_rxcui = rxcui_data['ndc_to_rxcui']
    print(f"  Loaded {len(ndc_to_rxcui):,} NDC -> RxCUI mappings")
    
    # Create RxCUI -> NDCs mapping
    rxcui_to_ndcs = defaultdict(list)
    for ndc, rxcui in ndc_to_rxcui.items():
        if isinstance(rxcui, list):
            for r in rxcui:
                rxcui_to_ndcs[str(r)].append(ndc)
        else:
            rxcui_to_ndcs[str(rxcui)].append(ndc)
    print(f"  Built RxCUI -> NDCs mapping: {len(rxcui_to_ndcs):,} RxCUIs")
    
    # Load RxNorm entities
    rxnorm_entities = {}
    rxcui_to_tty = {}
    rxcui_to_name = {}
    rxcui_to_entity_id = {}
    
    rxnorm_file = DATA_DIR / "rxnorm_entities.jsonl"
    with open(rxnorm_file, 'r') as f:
        for line in f:
            entity = json.loads(line)
            entity_id = entity['id']
            rxnorm_entities[entity_id] = entity
            
            rxcui = None
            tty = None
            name = None
            
            for val in entity.get('values', []):
                prop = val.get('property')
                value = val.get('value')
                
                if prop == PROP_RXCUI:
                    rxcui = value
                    rxcui_to_entity_id[str(rxcui)] = entity_id
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
    
    # Verify all target RxCUIs exist and are IN type
    print("\nVerifying target RxCUIs:")
    for ingredient, rxcui in TARGET_INGREDIENTS.items():
        if rxcui in rxcui_to_tty:
            tty = rxcui_to_tty[rxcui]
            name = rxcui_to_name.get(rxcui, 'NO NAME')
            print(f"  OK {ingredient}: RxCUI {rxcui} - {name} (TTY: {tty})")
        else:
            print(f"  X {ingredient}: RxCUI {rxcui} NOT FOUND in entity data")
    
    # Build relationship graph - FORWARD (from_id -> to_id)
    rel_graph = defaultdict(list)
    
    rel_file = DATA_DIR / "rxnorm_relations.jsonl"
    with open(rel_file, 'r') as f:
        for line in f:
            rel = json.loads(line)
            
            from_id = rel.get('from')
            to_id = rel.get('to')
            rel_type = rel.get('type')
            
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
        
            # Build FORWARD graph: from_rxcui -> to_rxcui
            rel_graph[from_rxcui].append((to_rxcui, rel_type))
    
    print(f"\nBuilt relationship graph (FORWARD): {len(rel_graph):,} source RxCUIs")
    
    # Load DailyMed documents
    dailymed_file = DATA_DIR / "dailymed_documents.json"
    with open(dailymed_file, 'r') as f:
        dailymed_docs = json.load(f)
    
    setid_to_dailymed = {}
    for doc in dailymed_docs:
        set_id = doc.get("fda_set_id")
        if set_id:
            setid_to_dailymed[set_id] = doc
    print(f"  Loaded {len(setid_to_dailymed):,} Set ID -> DailyMed mappings")
    # Load enriched RxNorm entities with PubChem properties
    enriched_entities = {}
    with open(ENRICHED_ENTITIES_FILE, 'r') as f:
        for line in f:
            entity = json.loads(line)
            enriched_entities[entity['id']] = entity
    print(f"  Loaded {len(enriched_entities):,} enriched RxNorm entities")
    
    # Load CID mapping file
    with open(CID_MAPPING_FILE, 'r') as f:
        cid_mapping_data = json.load(f)
    
    cid_mapping = cid_mapping_data.get('cid_mapping', {})
    print(f"  Loaded {len(cid_mapping):,} CID mappings")

    
    return {
        'ndc_to_setid': ndc_to_setid,
        'ndc_to_rxcui': ndc_to_rxcui,
        'rxcui_to_ndcs': rxcui_to_ndcs,
        'rxcui_to_tty': rxcui_to_tty,
        'rxcui_to_name': rxcui_to_name,
        'rxcui_to_entity_id': rxcui_to_entity_id,
        'rel_graph': rel_graph,
        'setid_to_dailymed': setid_to_dailymed,
        'enriched_entities': enriched_entities,
        'cid_mapping': cid_mapping
    }

def walk_starting_point(starting_rxcui, source_type, data):
    """
    Walk from a starting point (PIN/IN/MIN) DOWN the hierarchy.
    
    CRITICAL UPDATE: Now includes ALL undocumented relationship types discovered through investigation:
    - dd9264e954d650f98f97cc5d471e5a51: SCDF/SCDG -> SCD
    - cbf90e604bf458719df7ad10fd90c07f: DF -> SCD
    - f44019f93b2258119d1022c4f39b9da5: MIN -> SCD
    - 12a84f5c305857b782821609c5e2b59b: SCD -> SCDG/TMSY
    - b74d6b2005505263a22c10fe0ed1f591: DFG -> SCDG
    
    CRITICAL FIX - EARLY TTY BLOCKING:
    BLOCKED_TTYS (TMSY, PSN, SY) are checked IMMEDIATELY after retrieving TTY,
    before any processing or categorization occurs. This ensures these secondary
    codes are never captured.
    
    CRITICAL FIX: Capture ALL SCDs, even those without NDCs!
    """
    visited = set()
    queue = [(starting_rxcui, 0)]
    
    entities = {
        'starting_point': None,
        'brand_names': [],
        'scdgs': [],
        'scds': [],
        'sbds': [],
        'ndcs': [],
        'set_ids': set()
    }
    
    # Track NDCs to avoid duplicates
    seen_ndcs = set()
    
    # Capture the starting point
    tty = data['rxcui_to_tty'].get(starting_rxcui, "UNKNOWN")
    name = data['rxcui_to_name'].get(starting_rxcui, "Unknown")
    entity_id = data['rxcui_to_entity_id'].get(starting_rxcui)
    
    if source_type == 'PIN':
        geo_type = GEO_TYPES['PRECISE_INGREDIENT']
    elif source_type == 'IN':
        geo_type = GEO_TYPES['INGREDIENT']
    elif source_type == 'MIN':
        geo_type = GEO_TYPES['MULTIPLE_INGREDIENT']
    else:
        geo_type = source_type
    
    entities['starting_point'] = {
        'rxcui': starting_rxcui,
        'name': name,
        'entity_id': entity_id,
        'geo_type': geo_type,
        'source_tty': tty
    }
    
    # Valid forward relationship types based on starting TTY
    valid_forward_rels = set()
    
    if source_type == 'IN':
        # IN -> SCDC, SCDG, SCDF via ingredient_of
        # IN -> BN via has_tradename
        valid_forward_rels.add(REL_INGREDIENT_OF)
        valid_forward_rels.add(REL_HAS_TRADENAME)
    elif source_type == 'PIN':
        # PIN -> SCDC, BN via precise_ingredient_of
        valid_forward_rels.add(REL_PRECISE_INGREDIENT_OF)
    elif source_type == 'MIN':
        # MIN -> SCD via f44019f93b2258119d1022c4f39b9da5 (undocumented)
        valid_forward_rels.add(REL_MIN_TO_SCD)
    
    while queue:
        current, depth = queue.pop(0)
        if current in visited or depth > 5:
            continue
        
        visited.add(current)
        
        # CRITICAL: Get TTY and check BLOCKED_TTYS IMMEDIATELY
        tty = data['rxcui_to_tty'].get(current, "UNKNOWN")
        
        # CRITICAL: BLOCK all unwanted TTY types - CHECK THIS FIRST!
        if tty in BLOCKED_TTYS:
            # Skip this node and don't add it to any category
            # But still process its neighbors if they're not blocked
            pass
        
        # CRITICAL: BLOCK all other PIN/IN/MIN entities (they are mutually exclusive starting points)
        elif tty in ('PIN', 'IN', 'MIN') and current != starting_rxcui:
            # Don't traverse from other foundational entities
            pass
        
        # Only process ALLOWED TTY types
        elif tty not in ALLOWED_TTYS:
            # Skip this node and don't process it
            pass
        
        # Process the starting point separately
        elif current == starting_rxcui:
            # Add neighbors to queue using valid forward relationships
            if current in data['rel_graph']:
                for neighbor, rel_type in data['rel_graph'][current]:
                    if neighbor not in visited and rel_type in valid_forward_rels:
                        queue.append((neighbor, depth + 1))
        
        # Process allowed nodes
        else:
            name = data['rxcui_to_name'].get(current, "Unknown")
            entity_id = data['rxcui_to_entity_id'].get(current)
            
            # Determine valid relationships based on current TTY
            current_valid_rels = set()
            
            if tty == 'SCDC':
                # SCDC -> SBDC via has_tradename
                # SCDC -> SCD, SBD via constitutes
                current_valid_rels.add(REL_HAS_TRADENAME)
                current_valid_rels.add(REL_CONSTITUTES)
            elif tty == 'SCDF':
                # SCDF -> SCD via dd9264e954d650f98f97cc5d471e5a51 (undocumented)
                current_valid_rels.add(REL_SCDG_SCDF_TO_SCD)
            elif tty == 'SCDG':
                # SCDG -> SCD via dd9264e954d650f98f97cc5d471e5a51 (undocumented)
                current_valid_rels.add(REL_SCDG_SCDF_TO_SCD)
            elif tty == 'DF':
                # DF -> SCD via cbf90e604bf458719df7ad10fd90c07f (undocumented)
                current_valid_rels.add(REL_DF_TO_SCD)
            elif tty == 'BN':
                # BN -> SBDC, SBD via ingredient_of
                current_valid_rels.add(REL_INGREDIENT_OF)
            elif tty == 'SBDC':
                # SBDC -> SBD via constitutes
                current_valid_rels.add(REL_CONSTITUTES)
            elif tty == 'SCD':
                # SCD -> SCDG/TMSY via 12a84f5c305857b782821609c5e2b59b (undocumented)
                # SCD -> SBD via has_tradename
                current_valid_rels.add(REL_SCD_TO_SCDG_TMSY)
                current_valid_rels.add(REL_HAS_TRADENAME)
            elif tty == 'SBD':
                # SBD has no forward relationships (it's an endpoint)
                current_valid_rels = set()
            elif tty in ('GPCK', 'BPCK'):
                # Packs have no forward relationships
                current_valid_rels = set()
            
            # Categorize by TTY
            if tty == 'BN':
                entities['brand_names'].append({
                    'rxcui': current,
                    'name': name,
                    'entity_id': entity_id,
                    'geo_type': GEO_TYPES['BN'],
                    'source_tty': tty,
                    'source': source_type
                })
            elif tty == 'SCDG':
                has_ndcs = current in data['rxcui_to_ndcs']
                entities['scdgs'].append({
                    'rxcui': current,
                    'name': name,
                    'entity_id': entity_id,
                    'geo_type': GEO_TYPES['SCDG'],
                    'source_tty': tty,
                    'has_ndcs': has_ndcs,
                    'source': source_type
                })
                
                # Add NDCs from SCDG
                if has_ndcs:
                    for ndc in data['rxcui_to_ndcs'][current]:
                        if ndc not in seen_ndcs:
                            seen_ndcs.add(ndc)
                            set_id = data['ndc_to_setid'].get(ndc)
                            if set_id:
                                entities['set_ids'].add(set_id)
                            entities['ndcs'].append({
                                'ndc': ndc,
                                'set_id': set_id,
                                'geo_type': GEO_TYPES['NDC'],
                                'source_rxcui': current,
                                'source_tty': 'SCDG',
                                'source': source_type
                            })
            elif tty == 'SCD':
                # CRITICAL FIX: Capture ALL SCDs, even those without NDCs!
                ndcs = data['rxcui_to_ndcs'].get(current, [])
                
                # Build NDC list
                ndc_list = []
                for ndc in ndcs:
                    if ndc not in seen_ndcs:
                        seen_ndcs.add(ndc)
                        set_id = data['ndc_to_setid'].get(ndc)
                        if set_id:
                            entities['set_ids'].add(set_id)
                        ndc_list.append({
                            'ndc': ndc,
                            'set_id': set_id
                        })
                        entities['ndcs'].append({
                            'ndc': ndc,
                            'set_id': set_id,
                            'geo_type': GEO_TYPES['NDC'],
                            'source_rxcui': current,
                            'source_tty': 'SCD',
                            'source': source_type
                        })
                
                # ALWAYS add the SCD, even if it has no NDCs
                entities['scds'].append({
                    'rxcui': current,
                    'name': name,
                    'entity_id': entity_id,
                    'geo_type': GEO_TYPES['SCD'],
                    'source_tty': tty,
                    'ndcs': ndc_list,
                    'source': source_type
                })
            elif tty == 'SBD':
                ndcs = data['rxcui_to_ndcs'].get(current, [])
                
                # Build NDC list
                ndc_list = []
                for ndc in ndcs:
                    if ndc not in seen_ndcs:
                        seen_ndcs.add(ndc)
                        set_id = data['ndc_to_setid'].get(ndc)
                        if set_id:
                            entities['set_ids'].add(set_id)
                        ndc_list.append({
                            'ndc': ndc,
                            'set_id': set_id
                        })
                        entities['ndcs'].append({
                            'ndc': ndc,
                            'set_id': set_id,
                            'geo_type': GEO_TYPES['NDC'],
                            'source_rxcui': current,
                            'source_tty': 'SBD',
                            'source': source_type
                        })
                
                # ALWAYS add the SBD, even if it has no NDCs
                entities['sbds'].append({
                    'rxcui': current,
                    'name': name,
                    'entity_id': entity_id,
                    'geo_type': GEO_TYPES['SBD'],
                    'source_tty': tty,
                    'ndcs': ndc_list,
                    'source': source_type
                })
            elif tty in ('GPCK', 'BPCK'):
                ndcs = data['rxcui_to_ndcs'].get(current, [])
                if ndcs:
                    for ndc in ndcs:
                        if ndc not in seen_ndcs:
                            seen_ndcs.add(ndc)
                            set_id = data['ndc_to_setid'].get(ndc)
                            if set_id:
                                entities['set_ids'].add(set_id)
                            entities['ndcs'].append({
                                'ndc': ndc,
                                'set_id': set_id,
                                'geo_type': GEO_TYPES['NDC'],
                                'source_rxcui': current,
                                'source_tty': tty,
                                'source': source_type
                            })
        
        # CRITICAL: Even if the current node is blocked, we still process its neighbors
        # This ensures we don't block the entire subgraph
        if current in data['rel_graph']:
            # Determine which relationships to follow based on current TTY
            current_valid_rels = set()
            
            # Get TTY for current node (might be blocked)
            current_tty = data['rxcui_to_tty'].get(current, "UNKNOWN")
            
            if current_tty in BLOCKED_TTYS:
                # BLOCKED nodes don't have outgoing relationships
                current_valid_rels = set()
            elif current_tty == 'SCDC':
                current_valid_rels.add(REL_HAS_TRADENAME)
                current_valid_rels.add(REL_CONSTITUTES)
            elif current_tty == 'SCDF':
                current_valid_rels.add(REL_SCDG_SCDF_TO_SCD)
            elif current_tty == 'SCDG':
                current_valid_rels.add(REL_SCDG_SCDF_TO_SCD)
            elif current_tty == 'DF':
                current_valid_rels.add(REL_DF_TO_SCD)
            elif current_tty == 'BN':
                current_valid_rels.add(REL_INGREDIENT_OF)
            elif current_tty == 'SBDC':
                current_valid_rels.add(REL_CONSTITUTES)
            elif current_tty == 'SCD':
                current_valid_rels.add(REL_SCD_TO_SCDG_TMSY)
                current_valid_rels.add(REL_HAS_TRADENAME)
            elif current_tty == 'SBD':
                current_valid_rels = set()
            elif current_tty in ('GPCK', 'BPCK'):
                current_valid_rels = set()
            else:
                current_valid_rels = set()
            
            # Add neighbors to queue
            for neighbor, rel_type in data['rel_graph'][current]:
                if neighbor not in visited and rel_type in current_valid_rels:
                    queue.append((neighbor, depth + 1))
    
    # Convert set_ids to sorted list
    entities['set_ids'] = sorted(list(entities['set_ids']))
    
    return entities

def find_pins_connected_to_in(in_rxcui, data):
    """Find PINs that have ACTUAL bidirectional relationships to an IN"""
    pins = []
    
    # Check IN <- form_of <- PIN (file stores PIN -> IN)
    for neighbor, rel_type in data['rel_graph'].get(in_rxcui, []):
        neighbor_tty = data['rxcui_to_tty'].get(neighbor, "UNKNOWN")
        if neighbor_tty == 'PIN' and rel_type == REL_HAS_FORM:
            pins.append(neighbor)
    
    return pins

def find_mins_connected_to_in(in_rxcui, data):
    """Find MINs that have ACTUAL bidirectional relationships to an IN"""
    mins = []
    
    # Check IN -> MIN via 1df119c2ba785c688aafd35556e3fab6 (undocumented)
    for neighbor, rel_type in data['rel_graph'].get(in_rxcui, []):
        neighbor_tty = data['rxcui_to_tty'].get(neighbor, "UNKNOWN")
        if neighbor_tty == 'MIN' and rel_type == REL_IN_TO_MIN:
            mins.append(neighbor)
    
    return mins


def fetch_pubchem_properties(cid, enriched_entities):
    """Fetch PubChem properties using CID
    
    This function checks if an entity with the given CID exists in the enriched entities,
    and if found, extracts the PubChem properties.
    
    Args:
        cid: PubChem Compound ID as string
        enriched_entities: Dictionary of enriched RxNorm entities
    
    Returns:
        Dictionary of PubChem properties or None if not found
    """
    # Search for entity with the given CID in enriched entities
    for entity_id, entity in enriched_entities.items():
        for prop in entity.get('values', []):
            if prop.get('property') == 'bdd863e095365bbea65deae8ebf1e81b' and prop.get('value') == cid:
                # Found entity with this CID, extract properties
                properties = {}
                
                # Property IDs for PubChem data (from pharma_schema.py)
                # These UUIDs match the PROPERTIES definitions in the schema
                PROP_CID = "bdd863e095365bbea65deae8ebf1e81b"      # pubchem_cid
                PROP_SMILES = "56e99a1b93b2573689e2f6a6c662df10"   # smiles
                PROP_INCHI = "6b432fc791ad5358b1f17fdc6abcfacc"     # inchikey (actually contains InChI string)
                PROP_PMID = "c2842d1831e35b2f82fb74b532f4508b"      # pmid (PubMed ID)
                PROP_IUPAC = "5fbf742a110d508abc9af6a1cd1e49e7"     # iupac_name
                PROP_FORMULA = "20aba01a611d57e1bb02ca665dd61acd"   # molecular_formula (with MW)
                
                for prop in entity.get('values', []):
                    prop_id = prop.get('property')
                    value = prop.get('value')
                    
                    if prop_id == PROP_CID:
                        properties['pubchem_cid'] = value
                    elif prop_id == PROP_SMILES:
                        properties['smiles'] = value
                    elif prop_id == PROP_INCHI:
                        # Note: This property ID maps to "inchikey" in schema but contains InChI string
                        properties['inchi'] = value
                    elif prop_id == PROP_PMID:
                        properties['pmid'] = value
                    elif prop_id == PROP_IUPAC:
                        properties['iupac_name'] = value
                    elif prop_id == PROP_FORMULA:
                        # Clean up molecular formula (remove molecular weight)
                        if '	' in value:
                            value = value.split('	')[0]
                        properties['molecular_formula'] = value
                
                return properties if properties else None
    
    return None

def extract_ingredient_data(ingredient_name, in_rxcui, data):
    """
    Extract all entities for a single ingredient using tri-hierarchy traversal.
    
    CRITICAL UPDATE: Now includes ALL undocumented relationship types:
    - SCDF/SCDG -> SCD via dd9264e954d650f98f97cc5d471e5a51
    - DF -> SCD via cbf90e604bf458719df7ad10fd90c07f
    - MIN -> SCD via f44019f93b2258119d1022c4f39b9da5
    - SCD -> SCDG/TMSY via 12a84f5c305857b782821609c5e2b59b
    - DFG -> SCDG via b74d6b2005505263a22c10fe0ed1f591
    
    CRITICAL FIX - EARLY TTY BLOCKING:
    BLOCKED_TTYS (TMSY, PSN, SY) are checked IMMEDIATELY after retrieving TTY,
    before any processing or categorization occurs. This ensures these secondary
    codes are never captured.
    
    CRITICAL FIX: Capture ALL SCDs and SBDs, even those without NDCs!
    """
    # Find connected PINs and MINs using ACTUAL relationships
    connected_pins = find_pins_connected_to_in(in_rxcui, data)
    connected_mins = find_mins_connected_to_in(in_rxcui, data)
    
    print(f"  Found {len(connected_pins)} related PINs")
    print(f"  Found {len(connected_mins)} related MINs")
    
    # Walk from IN
    print(f"  Walking from IN...")
    in_entities = walk_starting_point(in_rxcui, 'IN', data)
    
    # Walk from all connected PINs
    all_pin_entities = []
    for pin in connected_pins:
        pin_name = data['rxcui_to_name'].get(pin, "Unknown")
        print(f"    Walking from PIN: {pin} ({pin_name})...")
        pin_entities = walk_starting_point(pin, 'PIN', data)
        all_pin_entities.append(pin_entities)
    
    # Walk from all connected MINs
    all_min_entities = []
    for min_rxcui in connected_mins:
        min_name = data['rxcui_to_name'].get(min_rxcui, "Unknown")
        print(f"    Walking from MIN: {min_rxcui} ({min_name})...")
        min_entities = walk_starting_point(min_rxcui, 'MIN', data)
        all_min_entities.append(min_entities)
    
    # Merge all entities
    merged_entities = {
        'ingredient': in_entities['starting_point'],
        'connected_pins': [e['starting_point'] for e in all_pin_entities],
        'connected_mins': [e['starting_point'] for e in all_min_entities],
        'brand_names': [],
        'scdgs': [],
        'scds': [],
        'sbds': [],
        'ndcs': [],
        'set_ids': set()
    }
    
    # Merge brand names
    seen_brand_names = set()
    for entities_list in [in_entities] + all_pin_entities + all_min_entities:
        for bn in entities_list['brand_names']:
            if bn['rxcui'] not in seen_brand_names:
                seen_brand_names.add(bn['rxcui'])
                merged_entities['brand_names'].append(bn)
    
    # Merge SCDGs
    seen_scdgs = set()
    for entities_list in [in_entities] + all_pin_entities + all_min_entities:
        for scdg in entities_list['scdgs']:
            if scdg['rxcui'] not in seen_scdgs:
                seen_scdgs.add(scdg['rxcui'])
                merged_entities['scdgs'].append(scdg)
    
    # Merge SCDs
    seen_scds = set()
    for entities_list in [in_entities] + all_pin_entities + all_min_entities:
        for scd in entities_list['scds']:
            if scd['rxcui'] not in seen_scds:
                seen_scds.add(scd['rxcui'])
                merged_entities['scds'].append(scd)
    
    # Merge SBDs
    seen_sbds = set()
    for entities_list in [in_entities] + all_pin_entities + all_min_entities:
        for sbd in entities_list['sbds']:
            if sbd['rxcui'] not in seen_sbds:
                seen_sbds.add(sbd['rxcui'])
                merged_entities['sbds'].append(sbd)
    
    # Merge NDCs
    seen_ndcs = set()
    for entities_list in [in_entities] + all_pin_entities + all_min_entities:
        for ndc in entities_list['ndcs']:
            if ndc['ndc'] not in seen_ndcs:
                seen_ndcs.add(ndc['ndc'])
                merged_entities['ndcs'].append(ndc)
    
    # Merge Set IDs
    for entities_list in [in_entities] + all_pin_entities + all_min_entities:
        for set_id in entities_list['set_ids']:
            merged_entities['set_ids'].add(set_id)
    
    merged_entities['set_ids'] = sorted(list(merged_entities['set_ids']))
    
    # Add package insert information to NDCs
    for ndc_data in merged_entities['ndcs']:
        set_id = ndc_data.get('set_id')
        if set_id:
            dailymed_doc = data['setid_to_dailymed'].get(set_id)
            if dailymed_doc:
                ndc_data['package_insert'] = {
                    'title': dailymed_doc.get('title', 'N/A'),
                    'effective_date': dailymed_doc.get('effective_time', 'N/A'),
                    'set_id': set_id
                }
    
    # Add package insert summary
    merged_entities['package_inserts'] = []
    for set_id in merged_entities['set_ids']:
        dailymed_doc = data['setid_to_dailymed'].get(set_id)
        if dailymed_doc:
            merged_entities['package_inserts'].append({
                'set_id': set_id,
                'title': dailymed_doc.get('title', 'N/A'),
                'effective_date': dailymed_doc.get('effective_time', 'N/A')
            })
    
    return merged_entities

def main():
    print("=" * 80)
    print("EXTRACT DATA FOR GEO IMPORT (RxNorm DOCUMENTED FLOW VERSION)")
    print("=" * 80)
    print("CRITICAL UPDATE - UNDOCUMENTED RELATIONSHIP TYPES DISCOVERED!")
    print("\nWe discovered several undocumented relationship types:")
    print("  - dd9264e954d650f98f97cc5d471e5a51: SCDF/SCDG -> SCD")
    print("  - cbf90e604bf458719df7ad10fd90c07f: DF -> SCD")
    print("  - f44019f93b2258119d1022c4f39b9da5: MIN -> SCD")
    print("  - 1df119c2ba785c688aafd35556e3fab6: IN -> MIN")
    print("  - 94272e15b3535feab43867d3b374f608: MIN -> IN/PIN")
    print("  - 12a84f5c305857b782821609c5e2b59b: SCD -> SCDG/TMSY")
    print("  - b74d6b2005505263a22c10fe0ed1f591: DFG -> SCDG")
    print("\nThese undocumented types are NOW included in our traversal!")
    print("\nCRITICAL FIX - EARLY TTY BLOCKING:")
    print("BLOCKED_TTYS (TMSY, PSN, SY) are checked IMMEDIATELY after retrieving TTY,")
    print("before any processing or categorization occurs. This ensures these secondary")
    print("codes are never captured.")
    print("\nCRITICAL FIX: Capture ALL SCDs and SBDs, even those without NDCs!")
    print("=" * 80)
    
    data = load_data()
    
    # Extract data for all target ingredients using VERIFIED IN RxCUIs
    ingredients_data = []
    
    for ingredient_name, in_rxcui in TARGET_INGREDIENTS.items():
        print(f"\nProcessing: {ingredient_name} (RxCUI: {in_rxcui})")
        entities = extract_ingredient_data(ingredient_name, in_rxcui, data)
        
        if entities and entities['ingredient']:
            # Get CID from mapping
            cid = data['cid_mapping'].get(in_rxcui, {}).get('cid')
            
            # Extract PubChem properties for the ingredient
            pubchem_props = None
            if cid:
                pubchem_props = fetch_pubchem_properties(cid, data['enriched_entities'])
            
            # Build the ingredient data with PubChem properties at the top level
            ingredient_data = {
                'ingredient': ingredient_name,
                'rxcui': in_rxcui,
                'entities': entities
            }
            
            # Add PubChem properties at the top level if available
            if pubchem_props:
                ingredient_data['pubchem_properties'] = pubchem_props
            
            ingredients_data.append(ingredient_data)
            
            # Print summary
            print(f"  OK Ingredient: {entities['ingredient']['name']}")
            print(f"     Related PINs: {len(entities['connected_pins'])}")
            print(f"     Related MINs: {len(entities['connected_mins'])}")
            print(f"     Brand Names (BN): {len(entities['brand_names'])}")
            print(f"     SCDGs: {len(entities['scdgs'])}")
            print(f"     SCDs: {len(entities['scds'])}")
            print(f"     SBDs: {len(entities['sbds'])}")
            print(f"     NDCs: {len(entities['ndcs'])}")
            print(f"     Set IDs: {len(entities['set_ids'])}")
        else:
            print(f"  X No entities found for {ingredient_name}")
    
    # Create export object
    export = {
        'version': '13.0',
        'generated_at': datetime.now().isoformat(),
        'geo_ontology': {
            'types': GEO_TYPES,
            'description': 'Extracted entities mapped to existing Geo ontology using RxNorm documented flow with EXACT relationship types',
            'architecture': 'IN/PIN/MIN -> SCDC/SCDF/SCDG/BN -> SBDC -> SCD/SBD -> NDCs -> Set IDs',
            'blocked_tty': list(BLOCKED_TTYS),
            'allowed_tty': list(ALLOWED_TTYS),
            'discovery_method': 'Uses RxNorm documented relationships (has_form, has_ingredient, has_precise_ingredient, has_tradename, consists_of, constitutes) plus undocumented MIN relationships',
            'relationship_types': {
                'has_form': REL_HAS_FORM,
                'form_of': REL_FORM_OF,
                'has_ingredient': REL_HAS_INGREDIENT,
                'ingredient_of': REL_INGREDIENT_OF,
                'precise_ingredient_of': REL_PRECISE_INGREDIENT_OF,
                'has_precise_ingredient': REL_HAS_PRECISE_INGREDIENT,
                'has_tradename': REL_HAS_TRADENAME,
                'tradename_of': REL_TRADENAME_OF,
                'consists_of': REL_CONSISTS_OF,
                'constitutes': REL_CONSTITUTES,
                'in_to_min': REL_IN_TO_MIN,
                'min_to_ingredient': REL_MIN_TO_INGREDIENT,
                'min_to_scd': REL_MIN_TO_SCD,
                'scdg_scdf_to_scd': REL_SCDG_SCDF_TO_SCD,
                'df_to_scd': REL_DF_TO_SCD,
                'scd_to_scdg_tmsy': REL_SCD_TO_SCDG_TMSY,
                'dfg_to_scdg': REL_DFG_TO_SCDG
            },
            'critical_fix': 'Relationship file stores relationships in FORWARD direction. Graph is built in FORWARD direction with correct relationship type IDs. CRITICAL: SCDC -> SCD/SBD uses "constitutes" (f5e289c3d13a5aaaa38b22448f7e38ab), NOT "consists_of"! CRITICAL: MINs are included using undocumented relationship type f44019f93b2258119d1022c4f39b9da5 for MIN -> SCD connections. CRITICAL: SCDF/SCDG -> SCD uses undocumented relationship type dd9264e954d650f98f97cc5d471e5a51! CRITICAL: DF -> SCD uses undocumented relationship type cbf90e604bf458719df7ad10fd90c07f! CRITICAL: SCD -> SCDG/TMSY uses undocumented relationship type 12a84f5c305857b782821609c5e2b59b! CRITICAL: Capture ALL SCDs and SBDs, even those without NDCs! CRITICAL: Filter out TMSY, PSN, and SY codes completely - these are secondary/auxiliary codes that cause false connections! CRITICAL: EARLY TTY BLOCKING - BLOCKED_TTYS are checked IMMEDIATELY after retrieving TTY!'
        },
        'metadata': {
            'total_ingredients': len(ingredients_data),
            'ingredients': [i['ingredient'] for i in ingredients_data]
        },
        'ingredients': ingredients_data
    }
    
    # Save to file
    output_file = BASE_DIR / "data" / "grc20_v2" / "geo_import_extraction.json"
    with open(output_file, 'w') as f:
        json.dump(export, f, indent=2)
    
    # Calculate statistics
    total_pins = sum(len(i['entities']['connected_pins']) for i in ingredients_data)
    total_mins = sum(len(i['entities']['connected_mins']) for i in ingredients_data)
    total_brand_names = sum(len(i['entities']['brand_names']) for i in ingredients_data)
    total_scdgs = sum(len(i['entities']['scdgs']) for i in ingredients_data)
    total_scds = sum(len(i['entities']['scds']) for i in ingredients_data)
    total_sbds = sum(len(i['entities']['sbds']) for i in ingredients_data)
    total_ndcs = sum(len(i['entities']['ndcs']) for i in ingredients_data)
    total_set_ids = sum(len(i['entities']['set_ids']) for i in ingredients_data)
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"  Ingredients: {len(ingredients_data)}")
    print(f"  Total PINs: {total_pins}")
    print(f"  Total MINs: {total_mins}")
    print(f"  Brand Names: {total_brand_names}")
    print(f"  SCDGs: {total_scdgs}")
    print(f"  SCDs: {total_scds}")
    print(f"  SBDs: {total_sbds}")
    print(f"  NDCs: {total_ndcs}")
    print(f"  Set IDs: {total_set_ids}")
    print(f"  Output file: {output_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
