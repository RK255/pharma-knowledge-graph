#!/usr/bin/env python3
"""
Extract Full Connectivity for All CID-Matched Ingredients (with NDCs and PubChem)
==================================================================================

V3: Clean version with scoped combo SBD tethering - combo brands properly nested under their MINs.
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

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
NDC_TO_SETID_FILE = RAW_DATA_DIR / "ndc_to_setid.json"

OUTPUT_FILE = OUTPUT_DIR / "full_geo_extraction_v3.json"

# Property IDs
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'
PROP_CID = 'bdd863e095365bbea65deae8ebf1e81b'
PROP_SMILES = '56e99a1b93b2573689e2f6a6c662df10'
PROP_INCHIKEY = '6b432fc791ad5358b1f17fdc6abcfacc'
PROP_IUPAC_NAME = '5fbf742a110d508abc9af6a1cd1e49e7'
PROP_MOL_WEIGHT = '20aba01a611d57e1bb02ca665dd61acd'
PROP_PMID = 'c2842d1831e35b2f82fb74b532f4508b'

# TTY types
BLOCKED_TTYS = {'TMSY', 'PSN', 'SY'}


def load_rxnorm_entities():
    print("Loading RxNorm entities...")
    rxcui_to_entity = {}
    entity_id_to_entity = {}
    
    with open(RXNORM_ENTITIES_FILE, 'r') as f:
        for line in f:
            e = json.loads(line)
            eid = e.get('id')
            rxcui = name = tty = cid = smiles = inchikey = iupac = mol_weight = pmid = None
            for p in e.get('values', []):
                pid, val = p.get('property'), p.get('value')
                if pid == PROP_RXCUI:
                    rxcui = val
                elif pid == PROP_NAME:
                    name = val
                elif pid == PROP_TTY:
                    tty = val
                elif pid == PROP_CID:
                    cid = val
                elif pid == PROP_SMILES:
                    smiles = val
                elif pid == PROP_INCHIKEY:
                    inchikey = val
                elif pid == PROP_IUPAC_NAME:
                    iupac = val
                elif pid == PROP_MOL_WEIGHT:
                    mol_weight = val
                elif pid == PROP_PMID:
                    pmid = val
            if rxcui:
                entity_data = {'id': eid, 'rxcui': rxcui, 'name': name or f"Unknown_{rxcui}", 'tty': tty,
                               'cid': cid, 'smiles': smiles, 'inchikey': inchikey, 'iupac_name': iupac,
                               'mol_weight': mol_weight, 'pmid': pmid}
                rxcui_to_entity[rxcui] = entity_data
                entity_id_to_entity[eid] = entity_data
    
    print(f"  Loaded {len(rxcui_to_entity):,} entities")
    return rxcui_to_entity, entity_id_to_entity


def load_rxnorm_relations():
    print("Loading RxNorm relations...")
    forward = defaultdict(list)
    reverse = defaultdict(list)
    
    with open(RXNORM_RELATIONS_FILE, 'r') as f:
        for line in f:
            r = json.loads(line)
            fid, tid, rt = r.get('from'), r.get('to'), r.get('type')
            if fid and tid and rt:
                forward[fid].append((rt, tid))
                reverse[tid].append((rt, fid))
    
    print(f"  Loaded {sum(len(v) for v in forward.values()):,} relations")
    return dict(forward), dict(reverse)


def load_ndc_mappings():
    print("Loading NDC mappings...")
    with open(NDC_TO_RXCUI_FILE, 'r') as f:
        data = json.load(f)
    rxcui_to_ndcs = data.get('rxcui_to_ndcs', {})
    print(f"  Loaded {len(rxcui_to_ndcs):,} RxCUI → NDCs mappings")
    return rxcui_to_ndcs


def load_ndc_to_setid():
    print("Loading NDC → Set ID...")
    with open(NDC_TO_SETID_FILE, 'r') as f:
        data = json.load(f)
    ndc_to_setid = data.get('ndc_to_setid', {})
    print(f"  Loaded {len(ndc_to_setid):,} mappings")
    return ndc_to_setid


def load_cid_mapping():
    print("Loading CID mapping...")
    with open(CID_MAPPING_FILE, 'r') as f:
        data = json.load(f)
    cid_mapping = data.get('cid_mapping', {})
    print(f"  Loaded {len(cid_mapping):,} CID mappings")
    return cid_mapping


def get_scd_unique_ingredients(scd_entity_id, reverse, entity_id_to_entity):
    """Find all UNIQUE ingredient parents of an SCD/SBD."""
    ingredients = {}
    
    for rel_type, scdx_id in reverse.get(scd_entity_id, []):
        scdx_entity = entity_id_to_entity.get(scdx_id)
        if not scdx_entity or scdx_entity.get('tty') not in ('SCDC', 'SCDF', 'SCDG'):
            continue
        
        for rel2, ing_id in reverse.get(scdx_id, []):
            ing_entity = entity_id_to_entity.get(ing_id)
            if ing_entity and ing_entity.get('tty') == 'IN':
                rxcui = ing_entity['rxcui']
                if rxcui not in ingredients:
                    ingredients[rxcui] = {'rxcui': rxcui, 'name': ing_entity['name']}
    
    return ingredients


def extract_brand_from_sbd_name(sbd_name):
    if '[' in sbd_name and ']' in sbd_name:
        return sbd_name.split('[')[1].split(']')[0]
    return None


def find_connected_entities(in_rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse):
    result = {'scd': [], 'sbd': [], 'bn': [], 'pin': [], 'min': [], 'df': []}
    
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
    
    combo_scds = {}
    combo_sbds = {}
    brand_is_combo = {}
    bn_to_sbd = defaultdict(list)
    
    # Walk reverse from ingredient
    for rel_type, source_id in reverse.get(in_entity_id, []):
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
        elif source_tty in ('SCDC', 'SCDF', 'SCDG'):
            for rel2, target_id in reverse.get(source_id, []):
                target_entity = entity_id_to_entity.get(target_id)
                if not target_entity:
                    continue
                
                target_tty = target_entity['tty']
                target_rxcui = target_entity['rxcui']
                
                if target_tty == 'SCD':
                    scd_ingredients = get_scd_unique_ingredients(target_id, reverse, entity_id_to_entity)
                    num_ingredients = len(scd_ingredients)
                    
                    if num_ingredients > 1:
                        combo_scds[target_rxcui] = {
                            'entity': target_entity,
                            'ingredients': list(scd_ingredients.values())
                        }
                    else:
                        found_scds[target_rxcui] = target_entity
                
                elif target_tty == 'SBD':
                    sbd_ingredients = get_scd_unique_ingredients(target_id, reverse, entity_id_to_entity)
                    num_ingredients = len(sbd_ingredients)
                    brand_name = extract_brand_from_sbd_name(target_entity['name'])
                    
                    if num_ingredients > 1:
                        combo_sbds[target_rxcui] = {
                            'entity': target_entity,
                            'ingredients': list(sbd_ingredients.values()),
                            'brand_name': brand_name
                        }
                        if brand_name:
                            brand_is_combo[brand_name] = True
                    else:
                        found_sbds[target_rxcui] = target_entity
                        if brand_name:
                            brand_is_combo[brand_name] = False
    
    # Process BN -> SBD connections
    for bn_rxcui, bn_entity in found_bns.items():
        bn_id = bn_entity['id']
        for rel_type, target_id in forward.get(bn_id, []):
            target_entity = entity_id_to_entity.get(target_id)
            if target_entity and target_entity['tty'] == 'SBD':
                target_rxcui = target_entity['rxcui']
                if target_rxcui in combo_sbds:
                    continue  # Skip combo SBDs
                found_sbds[target_rxcui] = target_entity
                bn_to_sbd[bn_rxcui].append(target_rxcui)
    
    # Get dose forms from SCDs
    for scd_entity in found_scds.values():
        for rel_type, df_id in reverse.get(scd_entity['id'], []):
            df_entity = entity_id_to_entity.get(df_id)
            if df_entity and df_entity['tty'] == 'DF':
                found_dfs[df_entity['rxcui']] = df_entity
    
    # Build SBD -> BN mapping
    sbd_to_bn = {}
    for bn_rxcui, sbd_rxcuis in bn_to_sbd.items():
        for sbd_rxcui in sbd_rxcuis:
            sbd_to_bn[sbd_rxcui] = found_bns.get(bn_rxcui)
    
    # Build MIN list with combo products nested
    mins_output = []
    for min_rxcui, min_entity in found_mins.items():
        min_ingredients = {}
        for rel_type, ing_id in reverse.get(min_entity['id'], []):
            ing_entity = entity_id_to_entity.get(ing_id)
            if ing_entity and ing_entity['tty'] == 'IN':
                rxcui = ing_entity['rxcui']
                if rxcui not in min_ingredients:
                    min_ingredients[rxcui] = {'rxcui': rxcui, 'name': ing_entity['name']}
        
        min_ingredient_rxcuis = set(min_ingredients.keys())
        
        min_combo_scds = []
        for scd_rxcui, scd_data in combo_scds.items():
            scd_ingredient_rxcuis = set(i['rxcui'] for i in scd_data['ingredients'])
            if scd_ingredient_rxcuis == min_ingredient_rxcuis:
                min_combo_scds.append({
                    'rxcui': scd_rxcui,
                    'name': scd_data['entity']['name'],
                    'tty': 'SCD',
                    'ingredients': scd_data['ingredients']
                })
        
        min_combo_sbds = []
        for sbd_rxcui, sbd_data in combo_sbds.items():
            sbd_ingredient_rxcuis = set(i['rxcui'] for i in sbd_data['ingredients'])
            if sbd_ingredient_rxcuis == min_ingredient_rxcuis:
                min_combo_sbds.append({
                    'rxcui': sbd_rxcui,
                    'name': sbd_data['entity']['name'],
                    'tty': 'SBD',
                    'brand_name': sbd_data.get('brand_name'),
                    'ingredients': sbd_data['ingredients']
                })
        
        mins_output.append({
            'rxcui': min_rxcui,
            'name': min_entity['name'],
            'tty': 'MIN',
            'ingredients': list(min_ingredients.values()),
            'combo_scds': min_combo_scds,
            'combo_sbds': min_combo_sbds
        })
    
    # Build output
    for rxcui, entity in found_scds.items():
        result['scd'].append({'rxcui': rxcui, 'name': entity['name'], 'tty': 'SCD'})
    
    for rxcui, entity in found_sbds.items():
        sbd_entry = {'rxcui': rxcui, 'name': entity['name'], 'tty': 'SBD'}
        brand = sbd_to_bn.get(rxcui)
        if brand:
            sbd_entry['brand_name'] = {'rxcui': brand['rxcui'], 'name': brand['name'], 'tty': 'BN'}
        result['sbd'].append(sbd_entry)
    
    for rxcui, entity in found_bns.items():
        result['bn'].append({
            'rxcui': rxcui, 'name': entity['name'], 'tty': 'BN',
            'is_combo': brand_is_combo.get(entity['name'], False)
        })
    
    for rxcui, entity in found_pins.items():
        result['pin'].append({'rxcui': rxcui, 'name': entity['name'], 'tty': 'PIN'})
    
    result['min'] = mins_output
    
    for rxcui, entity in found_dfs.items():
        result['df'].append({'rxcui': rxcui, 'name': entity['name'], 'tty': 'DF'})
    
    return result


def add_ndcs(connections, rxcui_to_ndcs, ndc_to_setid):
    for scd in connections.get('scd', []):
        scd['ndcs'] = [{'ndc': ndc, 'set_id': ndc_to_setid.get(ndc)} 
                       for ndc in set(rxcui_to_ndcs.get(scd['rxcui'], []))]
    
    for sbd in connections.get('sbd', []):
        sbd['ndcs'] = [{'ndc': ndc, 'set_id': ndc_to_setid.get(ndc)} 
                       for ndc in set(rxcui_to_ndcs.get(sbd['rxcui'], []))]
    
    for min_data in connections.get('min', []):
        for scd in min_data.get('combo_scds', []):
            scd['ndcs'] = [{'ndc': ndc, 'set_id': ndc_to_setid.get(ndc)} 
                          for ndc in set(rxcui_to_ndcs.get(scd['rxcui'], []))]
        for sbd in min_data.get('combo_sbds', []):
            sbd['ndcs'] = [{'ndc': ndc, 'set_id': ndc_to_setid.get(ndc)} 
                          for ndc in set(rxcui_to_ndcs.get(sbd['rxcui'], []))]
    
    return connections


def has_drug_connections(connections):
    has_single = len(connections.get('scd', [])) > 0 or len(connections.get('sbd', [])) > 0
    has_combo = any(m.get('combo_scds') or m.get('combo_sbds') for m in connections.get('min', []))
    return has_single or has_combo


def has_ndcs(connections):
    for scd in connections.get('scd', []):
        if scd.get('ndcs'):
            return True
    for sbd in connections.get('sbd', []):
        if sbd.get('ndcs'):
            return True
    for m in connections.get('min', []):
        for p in m.get('combo_scds', []) + m.get('combo_sbds', []):
            if p.get('ndcs'):
                return True
    return False


def process_ingredient(name, rxcui, cid_mapping, rxcui_to_entity, entity_id_to_entity, forward, reverse, rxcui_to_ndcs, ndc_to_setid):
    entity = rxcui_to_entity.get(rxcui, {})
    mapping = cid_mapping.get(rxcui, {})
    
    connections = find_connected_entities(rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse)
    connections = add_ndcs(connections, rxcui_to_ndcs, ndc_to_setid)
    
    return {
        'rxcui': rxcui,
        'name': name,
        'cid': entity.get('cid') or mapping.get('cid'),
        'smiles': entity.get('smiles'),
        'inchi_key': entity.get('inchikey'),
        'iupac_name': entity.get('iupac_name'),
        'mol_weight': entity.get('mol_weight'),
        'pmid': entity.get('pmid'),
        'connections': connections
    }


def main():
    parser = argparse.ArgumentParser(description='Extract GEO v3')
    parser.add_argument('--include-without-ndc', action='store_true')
    args = parser.parse_args()
    
    print("=" * 80)
    print("EXTRACT GEO V3 - CLEAN COMBO TETHERING")
    print("=" * 80)
    
    rxcui_to_entity, entity_id_to_entity = load_rxnorm_entities()
    forward, reverse = load_rxnorm_relations()
    rxcui_to_ndcs = load_ndc_mappings()
    ndc_to_setid = load_ndc_to_setid()
    cid_mapping = load_cid_mapping()
    
    targets = [(m.get('name', 'Unknown'), r) for r, m in cid_mapping.items()]
    
    print(f"\nProcessing {len(targets):,} ingredients...")
    
    results = []
    filtered_no_conn = 0
    filtered_no_ndc = 0
    stats = defaultdict(int)
    unique_ndcs = set()
    
    for idx, (name, rxcui) in enumerate(targets):
        if (idx + 1) % 100 == 0 or idx == 0:
            print(f"  {idx + 1:,} / {len(targets):,}")
        
        result = process_ingredient(name, rxcui, cid_mapping, rxcui_to_entity, entity_id_to_entity, forward, reverse, rxcui_to_ndcs, ndc_to_setid)
        
        if not has_drug_connections(result['connections']):
            filtered_no_conn += 1
            continue
        
        if not args.include_without_ndc and not has_ndcs(result['connections']):
            filtered_no_ndc += 1
            continue
        
        results.append(result)
        
        conn = result['connections']
        stats['scd'] += len(conn.get('scd', []))
        stats['sbd'] += len(conn.get('sbd', []))
        stats['bn'] += len(conn.get('bn', []))
        stats['pin'] += len(conn.get('pin', []))
        stats['min'] += len(conn.get('min', []))
        stats['df'] += len(conn.get('df', []))
        
        if result.get('smiles'):
            stats['with_smiles'] += 1
        if result.get('inchi_key'):
            stats['with_inchikey'] += 1
        
        for m in conn.get('min', []):
            stats['combo_scd'] += len(m.get('combo_scds', []))
            stats['combo_sbd'] += len(m.get('combo_sbds', []))
            if m.get('combo_scds') or m.get('combo_sbds'):
                stats['mins_with_products'] += 1
        
        for item in conn.get('scd', []) + conn.get('sbd', []):
            for ndc in item.get('ndcs', []):
                unique_ndcs.add(ndc['ndc'])
                stats['ndc_occurrences'] += 1
                if ndc.get('set_id'):
                    stats['ndcs_with_setid'] += 1
        
        for m in conn.get('min', []):
            for item in m.get('combo_scds', []) + m.get('combo_sbds', []):
                for ndc in item.get('ndcs', []):
                    unique_ndcs.add(ndc['ndc'])
                    stats['ndc_occurrences'] += 1
                    if ndc.get('set_id'):
                        stats['ndcs_with_setid'] += 1
    
    print(f"\nFiltered: {filtered_no_conn:,} no connections, {filtered_no_ndc:,} no NDCs")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"Total Ingredients: {len(results):,}")
    print(f"Filtered (no SCD/SBD): {filtered_no_conn:,}")
    print(f"Filtered (no NDCs): {filtered_no_ndc:,}")
    print(f"\nPubChem Properties:")
    print(f"  Ingredients with SMILES: {stats.get('with_smiles', 0):,}")
    print(f"  Ingredients with InChIKey: {stats.get('with_inchikey', 0):,}")
    print(f"\nSingle-Ingredient Products:")
    print(f"  SCDs: {stats['scd']:,}")
    print(f"  SBDs: {stats['sbd']:,}")
    print(f"  Brand Names: {stats['bn']:,}")
    print(f"  PINs: {stats['pin']:,}")
    print(f"  MINs: {stats['min']:,}")
    print(f"  Dose Forms: {stats['df']:,}")
    print(f"\nCombo Products (under MINs):")
    print(f"  Combo SCDs: {stats['combo_scd']:,}")
    print(f"  Combo SBDs: {stats['combo_sbd']:,}")
    print(f"  MINs with products: {stats['mins_with_products']:,}")
    print(f"\nNDCs:")
    print(f"  Total occurrences: {stats['ndc_occurrences']:,}")
    print(f"  Distinct NDCs: {len(unique_ndcs):,}")
    print(f"  NDCs with Set IDs: {stats['ndcs_with_setid']:,}")
    coverage = (stats['ndcs_with_setid'] / stats['ndc_occurrences'] * 100) if stats['ndc_occurrences'] > 0 else 0
    print(f"  Set ID coverage: {coverage:.1f}%")
    print(f"\nOutput: {OUTPUT_FILE}")
    print("=" * 80)
    
    if results:
        s = results[0]
        print(f"\n--- Sample: {s['name']} ---")
        print(f"RxCUI: {s['rxcui']}")
        print(f"CID: {s.get('cid')}")
        print(f"SMILES: {s.get('smiles', 'N/A')[:60]}..." if s.get('smiles') else "SMILES: N/A")
        print(f"InChIKey: {s.get('inchi_key', 'N/A')}")
        print(f"SCDs: {len(s['connections'].get('scd', []))}")
        print(f"SBDs: {len(s['connections'].get('sbd', []))}")
        print(f"MINs: {len(s['connections'].get('min', []))}")
        for m in s['connections'].get('min', [])[:2]:
            print(f"  MIN: {m['name']}")
            print(f"    Ingredients: {[i['name'] for i in m.get('ingredients', [])]}")
            print(f"    Combo SCDs: {len(m.get('combo_scds', []))}, Combo SBDs: {len(m.get('combo_sbds', []))}")


if __name__ == "__main__":
    main()
