#!/usr/bin/env python3
"""
Extract Full Connectivity for All CID-Matched Ingredients (with NDCs and PubChem)
==================================================================================

Extracts all CID-matched ingredients with their full connectivity:
- PIN (Precise Ingredients)
- MIN (Multiple Ingredients)  
- BN (Brand Names)
- DF (Dose Forms)
- SCD (Semantic Clinical Drugs) - with NDCs
- SBD (Semantic Branded Drugs) - with NDCs
- PubChem properties (SMILES, InChIKey, etc.)

Output matches the structure expected by the Geo SDK importer.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Paths
BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"
OUTPUT_DIR = BASE_DIR / "scripts" / "production" / "geo-ingestor" / "data_to_publish"

# Input files
RXNORM_ENTITIES_FILE = DATA_DIR / "rxnorm_entities_enriched.jsonl"
RXNORM_RELATIONS_FILE = DATA_DIR / "rxnorm_relations.jsonl"
CID_MAPPING_FILE = DATA_DIR / "pubchem_cid_mapping.json"
NDC_TO_RXCUI_FILE = RAW_DATA_DIR / "ndc_to_rxcui.json"
NDC_TO_SETID_FILE = RAW_DATA_DIR / "ndc_to_setid_final_v3.json"

# Output file
OUTPUT_FILE = OUTPUT_DIR / "test_geo_extraction.json"

# Property IDs (from GRC-20 entities)
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'

# PubChem property IDs
PROP_CID = 'bdd863e095365bbea65deae8ebf1e81b'
PROP_SMILES = '56e99a1b93b2573689e2f6a6c662df10'
PROP_INCHIKEY = '6b432fc791ad5358b1f17fdc6abcfacc'
PROP_IUPAC_NAME = '5fbf742a110d508abc9af6a1cd1e49e7'
PROP_MOL_WEIGHT = '20aba01a611d57e1bb02ca665dd61acd'
PROP_PMID = 'c2842d1831e35b2f82fb74b532f4508b'

# Relationship types (from GRC-20 relations)
REL_IN_TO_PIN = '307907247a3c5be682ed242bb61a2947'
REL_IN_TO_MIN = '1df119c2ba785c688aafd35556e3fab6'
REL_IN_TO_BN = 'a42836a8c04757e1a995531b8ff3200b'
REL_IN_TO_SCDG = 'd085f236da3c51fca583c72e7058973b'
REL_SCDG_TO_SCD = 'dd9264e954d650f98f97cc5d471e5a51'
REL_SCD_TO_SBD = '12a84f5c305857b782821609c5e2b59b'
REL_DF_TO_SCD = 'cbf90e604bf458719df7ad10fd90c07f'
REL_MIN_TO_SCD = 'f44019f93b2258119d1022c4f39b9da5'

# TTY types
ALLOWED_TTYS = {'PIN', 'MIN', 'BN', 'DF', 'SCD', 'SBD', 'SCDG', 'SBDF', 'SCDC', 'SBDC'}
BLOCKED_TTYS = {'TMSY', 'PSN', 'SY'}


def load_rxnorm_entities():
    """Load RxNorm entities into lookup dictionaries, including PubChem properties."""
    print("Loading RxNorm entities (enriched)...")
    
    rxcui_to_entity = {}
    entity_id_to_entity = {}
    
    with open(RXNORM_ENTITIES_FILE, 'r') as f:
        for line in f:
            entity = json.loads(line)
            entity_id = entity.get('id')
            
            rxcui = None
            name = None
            tty = None
            cid = None
            smiles = None
            inchikey = None
            iupac_name = None
            mol_weight = None
            pmid = None
            
            for prop in entity.get('values', []):
                prop_id = prop.get('property')
                val = prop.get('value')
                
                if prop_id == PROP_RXCUI:
                    rxcui = val
                elif prop_id == PROP_NAME:
                    name = val
                elif prop_id == PROP_TTY:
                    tty = val
                elif prop_id == PROP_CID:
                    cid = val
                elif prop_id == PROP_SMILES:
                    smiles = val
                elif prop_id == PROP_INCHIKEY:
                    inchikey = val
                elif prop_id == PROP_IUPAC_NAME:
                    iupac_name = val
                elif prop_id == PROP_MOL_WEIGHT:
                    mol_weight = val
                elif prop_id == PROP_PMID:
                    pmid = val
            
            if rxcui:
                entity_data = {
                    'id': entity_id,
                    'rxcui': rxcui,
                    'name': name or f"Unknown_{rxcui}",
                    'tty': tty,
                    'cid': cid,
                    'smiles': smiles,
                    'inchikey': inchikey,
                    'iupac_name': iupac_name,
                    'mol_weight': mol_weight,
                    'pmid': pmid
                }
                rxcui_to_entity[rxcui] = entity_data
                entity_id_to_entity[entity_id] = entity_data
    
    print(f"  Loaded {len(rxcui_to_entity):,} RxNorm entities")
    return rxcui_to_entity, entity_id_to_entity


def load_rxnorm_relations():
    """Load RxNorm relations and build forward/reverse indexes."""
    print("Loading RxNorm relations...")
    
    forward = defaultdict(list)
    reverse = defaultdict(list)
    
    with open(RXNORM_RELATIONS_FILE, 'r') as f:
        for line in f:
            rel = json.loads(line)
            from_id = rel.get('from')
            to_id = rel.get('to')
            rel_type = rel.get('type')
            
            if from_id and to_id and rel_type:
                forward[from_id].append((rel_type, to_id))
                reverse[to_id].append((rel_type, from_id))
    
    print(f"  Loaded {sum(len(v) for v in forward.values()):,} relations")
    return dict(forward), dict(reverse)


def load_ndc_mappings():
    """Load NDC to RxCUI and NDC to Set ID mappings."""
    print("Loading NDC mappings...")
    
    with open(NDC_TO_RXCUI_FILE, 'r') as f:
        data = json.load(f)
    
    ndc_to_rxcui = data.get('ndc_to_rxcui', {})
    rxcui_to_ndcs = data.get('rxcui_to_ndcs', {})
    
    print(f"  Loaded {len(ndc_to_rxcui):,} NDC -> RxCUI mappings")
    print(f"  Loaded {len(rxcui_to_ndcs):,} RxCUI -> NDCs mappings (pre-built)")
    
    with open(NDC_TO_SETID_FILE, 'r') as f:
        data = json.load(f)
    ndc_to_setid = data.get('ndc_to_setid', {})
    print(f"  Loaded {len(ndc_to_setid):,} NDC -> Set ID mappings")
    
    return ndc_to_rxcui, rxcui_to_ndcs, ndc_to_setid


def load_cid_mapping():
    """Load PubChem CID mapping."""
    print("Loading CID mapping...")
    
    with open(CID_MAPPING_FILE, 'r') as f:
        data = json.load(f)
    
    cid_mapping = data.get('cid_mapping', {})
    
    print(f"  Loaded {len(cid_mapping):,} CID mappings")
    return cid_mapping


def find_connected_entities(in_rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse):
    """Find all entities connected to an ingredient."""
    result = {
        'scd': [],
        'sbd': [],
        'bn': [],
        'pin': [],
        'min': [],
        'df': []
    }
    
    in_entity = rxcui_to_entity.get(in_rxcui)
    if not in_entity:
        return result
    
    in_entity_id = in_entity['id']
    
    found_scds = {}
    found_sbds = {}
    found_bns = {}
    found_pins = {}
    found_mins = {}
    found_dfs = {}
    
    bn_to_sbd = defaultdict(list)
    
    incoming = reverse.get(in_entity_id, [])
    
    for rel_type, source_id in incoming:
        source_entity = entity_id_to_entity.get(source_id)
        if not source_entity:
            continue
        
        source_rxcui = source_entity['rxcui']
        source_tty = source_entity['tty']
        
        if source_tty in BLOCKED_TTYS:
            continue
        
        if source_tty == 'PIN':
            found_pins[source_rxcui] = source_entity
        elif source_tty == 'MIN':
            found_mins[source_rxcui] = source_entity
        elif source_tty == 'BN':
            found_bns[source_rxcui] = source_entity
        elif source_tty in ('SCDG', 'SCDC', 'SCDF'):
            scdg_incoming = reverse.get(source_id, [])
            
            for rel2, target_id in scdg_incoming:
                target_entity = entity_id_to_entity.get(target_id)
                if not target_entity:
                    continue
                
                target_tty = target_entity['tty']
                target_rxcui = target_entity['rxcui']
                
                if target_tty == 'SCD':
                    found_scds[target_rxcui] = target_entity
                elif target_tty == 'SBD':
                    found_sbds[target_rxcui] = target_entity
    
    for bn_rxcui, bn_entity in found_bns.items():
        bn_id = bn_entity['id']
        bn_outgoing = forward.get(bn_id, [])
        
        for rel_type, target_id in bn_outgoing:
            target_entity = entity_id_to_entity.get(target_id)
            if not target_entity:
                continue
            
            target_tty = target_entity['tty']
            target_rxcui = target_entity['rxcui']
            
            if target_tty == 'SBD':
                found_sbds[target_rxcui] = target_entity
                bn_to_sbd[bn_rxcui].append(target_rxcui)
    
    for scd_rxcui, scd_entity in found_scds.items():
        scd_id = scd_entity['id']
        scd_incoming = reverse.get(scd_id, [])
        
        for rel_type, source_id in scd_incoming:
            if rel_type == REL_DF_TO_SCD:
                df_entity = entity_id_to_entity.get(source_id)
                if df_entity and df_entity['tty'] == 'DF':
                    found_dfs[df_entity['rxcui']] = df_entity
    
    for sbd_rxcui, sbd_entity in found_sbds.items():
        sbd_id = sbd_entity['id']
        sbd_incoming = reverse.get(sbd_id, [])
        
        for rel_type, source_id in sbd_incoming:
            if rel_type == REL_DF_TO_SCD:
                df_entity = entity_id_to_entity.get(source_id)
                if df_entity and df_entity['tty'] == 'DF':
                    found_dfs[df_entity['rxcui']] = df_entity
    
    sbd_to_bn = {}
    for bn_rxcui, sbd_rxcuis in bn_to_sbd.items():
        for sbd_rxcui in sbd_rxcuis:
            sbd_to_bn[sbd_rxcui] = found_bns.get(bn_rxcui)
    
    for rxcui, entity in found_scds.items():
        result['scd'].append({
            'rxcui': rxcui,
            'name': entity['name'],
            'tty': 'SCD'
        })
    
    for rxcui, entity in found_sbds.items():
        sbd_entry = {
            'rxcui': rxcui,
            'name': entity['name'],
            'tty': 'SBD'
        }
        
        brand = sbd_to_bn.get(rxcui)
        if brand:
            sbd_entry['brand_name'] = {
                'rxcui': brand['rxcui'],
                'name': brand['name'],
                'tty': 'BN'
            }
        
        result['sbd'].append(sbd_entry)
    
    for rxcui, entity in found_bns.items():
        result['bn'].append({
            'rxcui': rxcui,
            'name': entity['name'],
            'tty': 'BN'
        })
    
    for rxcui, entity in found_pins.items():
        result['pin'].append({
            'rxcui': rxcui,
            'name': entity['name'],
            'tty': 'PIN'
        })
    
    for rxcui, entity in found_mins.items():
        result['min'].append({
            'rxcui': rxcui,
            'name': entity['name'],
            'tty': 'MIN'
        })
    
    for rxcui, entity in found_dfs.items():
        result['df'].append({
            'rxcui': rxcui,
            'name': entity['name'],
            'tty': 'DF'
        })
    
    return result


def add_ndcs_to_connections(connections, rxcui_to_ndcs, ndc_to_setid):
    """Add NDC data to SCD and SBD entries."""
    
    for scd in connections.get('scd', []):
        rxcui = scd['rxcui']
        ndcs = []
        
        for ndc in rxcui_to_ndcs.get(rxcui, []):
            set_id = ndc_to_setid.get(ndc)
            ndcs.append({
                'ndc': ndc,
                'set_id': set_id
            })
        
        scd['ndcs'] = ndcs
    
    for sbd in connections.get('sbd', []):
        rxcui = sbd['rxcui']
        ndcs = []
        
        for ndc in rxcui_to_ndcs.get(rxcui, []):
            set_id = ndc_to_setid.get(ndc)
            ndcs.append({
                'ndc': ndc,
                'set_id': set_id
            })
        
        sbd['ndcs'] = ndcs
    
    return connections


def process_ingredient(ingredient_name, in_rxcui, cid_mapping, rxcui_to_entity, 
                       entity_id_to_entity, forward, reverse, 
                       rxcui_to_ndcs, ndc_to_setid):
    """Process a single ingredient and return its full connectivity."""
    
    # Get the entity from enriched data (has PubChem properties)
    entity = rxcui_to_entity.get(in_rxcui, {})
    
    # Get CID from mapping or entity
    mapping_data = cid_mapping.get(in_rxcui, {})
    cid = entity.get('cid') or mapping_data.get('cid')
    
    connections = find_connected_entities(
        in_rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse
    )
    
    connections = add_ndcs_to_connections(connections, rxcui_to_ndcs, ndc_to_setid)
    
    result = {
        'rxcui': in_rxcui,
        'name': ingredient_name,
        'cid': cid,
        'smiles': entity.get('smiles'),
        'inchi_key': entity.get('inchikey'),
        'iupac_name': entity.get('iupac_name'),
        'mol_weight': entity.get('mol_weight'),
        'pmid': entity.get('pmid'),
        'connections': connections
    }
    
    return result


def main():
    print("=" * 80)
    print("EXTRACT FULL GEO CONNECTIVITY (WITH NDCs AND PUBCHEM)")
    print("=" * 80)
    
    rxcui_to_entity, entity_id_to_entity = load_rxnorm_entities()
    forward, reverse = load_rxnorm_relations()
    ndc_to_rxcui, rxcui_to_ndcs, ndc_to_setid = load_ndc_mappings()
    cid_mapping = load_cid_mapping()
    
    target_ingredients = []
    for rxcui, mapping in cid_mapping.items():
        ingredient_name = mapping.get('name', 'Unknown')
        target_ingredients.append((ingredient_name, rxcui))
    
    print(f"\nProcessing {len(target_ingredients):,} CID-matched ingredients...")
    
    results = []
    stats = {
        'total_scds': 0,
        'total_sbds': 0,
        'total_bns': 0,
        'total_pins': 0,
        'total_mins': 0,
        'total_dfs': 0,
        'total_ndcs': 0,
        'total_set_ids': 0,
        'ingredients_with_ndcs': 0,
        'ingredients_with_smiles': 0,
        'ingredients_with_inchikey': 0
    }
    
    for idx, (ingredient_name, in_rxcui) in enumerate(target_ingredients):
        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1:,} / {len(target_ingredients):,}")
        
        result = process_ingredient(
            ingredient_name, in_rxcui, cid_mapping,
            rxcui_to_entity, entity_id_to_entity, forward, reverse,
            rxcui_to_ndcs, ndc_to_setid
        )
        
        results.append(result)
        
        conn = result['connections']
        stats['total_scds'] += len(conn.get('scd', []))
        stats['total_sbds'] += len(conn.get('sbd', []))
        stats['total_bns'] += len(conn.get('bn', []))
        stats['total_pins'] += len(conn.get('pin', []))
        stats['total_mins'] += len(conn.get('min', []))
        stats['total_dfs'] += len(conn.get('df', []))
        
        if result.get('smiles'):
            stats['ingredients_with_smiles'] += 1
        if result.get('inchi_key'):
            stats['ingredients_with_inchikey'] += 1
        
        has_ndcs = False
        for scd in conn.get('scd', []):
            ndcs = scd.get('ndcs', [])
            stats['total_ndcs'] += len(ndcs)
            stats['total_set_ids'] += sum(1 for n in ndcs if n.get('set_id'))
            if ndcs:
                has_ndcs = True
        
        for sbd in conn.get('sbd', []):
            ndcs = sbd.get('ndcs', [])
            stats['total_ndcs'] += len(ndcs)
            stats['total_set_ids'] += sum(1 for n in ndcs if n.get('set_id'))
            if ndcs:
                has_ndcs = True
        
        if has_ndcs:
            stats['ingredients_with_ndcs'] += 1
    
    print(f"\nSaving to: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Total Ingredients: {len(results):,}")
    print(f"")
    print(f"PubChem Properties:")
    print(f"  Ingredients with SMILES: {stats['ingredients_with_smiles']:,}")
    print(f"  Ingredients with InChIKey: {stats['ingredients_with_inchikey']:,}")
    print(f"")
    print(f"Connectivity:")
    print(f"  Total SCDs: {stats['total_scds']:,}")
    print(f"  Total SBDs: {stats['total_sbds']:,}")
    print(f"  Total Brand Names: {stats['total_bns']:,}")
    print(f"  Total PINs: {stats['total_pins']:,}")
    print(f"  Total MINs: {stats['total_mins']:,}")
    print(f"  Total Dose Forms: {stats['total_dfs']:,}")
    print(f"")
    print(f"NDCs:")
    print(f"  Ingredients with NDCs: {stats['ingredients_with_ndcs']:,}")
    print(f"  Total NDCs: {stats['total_ndcs']:,}")
    print(f"  Total Set IDs: {stats['total_set_ids']:,}")
    print(f"")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 80)
    
    print("\n--- Sample Output (First Ingredient) ---")
    sample = results[0]
    print(f"RxCUI: {sample['rxcui']}")
    print(f"Name: {sample['name']}")
    print(f"CID: {sample.get('cid')}")
    print(f"SMILES: {sample.get('smiles', 'N/A')[:60]}..." if sample.get('smiles') else "SMILES: N/A")
    print(f"InChIKey: {sample.get('inchi_key', 'N/A')}")
    print(f"Connections:")
    for conn_type, entries in sample.get('connections', {}).items():
        print(f"  {conn_type}: {len(entries)} entries")


if __name__ == "__main__":
    main()
