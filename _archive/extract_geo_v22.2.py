#!/usr/bin/env python3
"""
Extract GEO with Pricing v22.2 - PIN Nesting with Combos (FIXED)
=================================================================
- SCDs, SBDs, BNs, DFs, NDCs nest under PINs
- SBDs nested under PIN now correctly get brand_name from their BN
- PIN combos (multiple ingredients) get MIN-style combo treatment
"""
import json
import argparse
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"
OUTPUT_DIR = BASE_DIR / "scripts" / "production" / "geo-ingestor" / "data_to_publish"

RXNORM_ENTITIES_FILE = DATA_DIR / "rxnorm_entities_enriched.jsonl"
RXNORM_RELATIONS_FILE = DATA_DIR / "rxnorm_relations.jsonl"
CID_MAPPING_FILE = DATA_DIR / "pubchem_cid_mapping.json"
NDC_MERGED_FILE = RAW_DATA_DIR / "ndc_merged.json"
NDC_TO_SETID_FILE = RAW_DATA_DIR / "ndc_to_setid.json"
PRICING_FILE = BASE_DIR / "data" / "pricing" / "analysis" / "pricing_for_your_ndcs.json"

OUTPUT_FILE = OUTPUT_DIR / "full_geo_extraction_v22.2.jsonl"

# Property IDs
PROP_NAME = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY = 'fd0c76eae47c55bbac4cca96203752c1'
PROP_CID = 'bdd863e095365bbea65deae8ebf1e81b'
PROP_SMILES = '56e99a1b93b2573689e2f6a6c662df10'
PROP_INCHIKEY = '6b432fc791ad5358b1f17fdc6abcfacc'
PROP_IUPAC = '5fbf742a110d508abc9af6a1cd1e49e7'
PROP_MOLWEIGHT = '20aba01a611d57e1bb02ca665dd61acd'
PROP_PMID = 'c2842d1831e35b2f82fb74b532f4508b'

# Relation IDs
REL_HAS_INGREDIENT = 'd085f236da3c51fca583c72e7058973b'
REL_INGREDIENT_OF = '708910ff645b507ab5616dbd680b5802'
REL_HAS_PRECISE_INGREDIENT = '307907247a3c5be682ed242bb61a2947'
REL_PRECISE_INGREDIENT_OF = '9147c85a51ea5a2481824d2aefe5956d'
REL_HAS_INGREDIENTS = '73f2d9bc321054dc80888064f36282fb'
REL_INGREDIENTS_OF = 'f44019f93b2258119d1022c4f39b9da5'
REL_HAS_PART = '94272e15b3535feab43867d3b374f608'
REL_PART_OF = '1df119c2ba785c688aafd35556f3fab6'
REL_CONSISTS_OF = '88c43b5be4eb5fe78b09872e9a9c3c70'
REL_CONSTITUTES = 'f5e289c3d13a5aaaa38b22448f7e38ab'
REL_HAS_TRADENAME = 'a42836a8c04757e1a995531b8ff3200b'
REL_TRADENAME_OF = 'dbc766b554f0579da4c7b7c29924d6a3'
REL_HAS_DOSE_FORM = '29f07e00f9d45f76aef7e6c03f00441b'
REL_DOSE_FORM_OF = 'cbf90e604bf458719df7ad10fd90c07f'
REL_HAS_FORM = 'd3077c62a9875bfbace8602b42872f43'
REL_FORM_OF = 'ee49f75185f25c79a1198d51cb922247'

BLOCKED_TTYS = {'TMSY', 'PSN', 'SY'}


def normalize_ndc(ndc_code):
    if not ndc_code:
        return None
    clean = str(ndc_code).replace('-', '').strip()
    if len(clean) == 10:
        return clean.zfill(11)
    if len(clean) == 11:
        return clean
    return clean.zfill(11) if len(clean) < 11 else clean[:11]


def format_ndc11_hyphens(ndc11):
    if not ndc11 or len(ndc11) != 11:
        return None
    return f"{ndc11[:5]}-{ndc11[5:9]}-{ndc11[9:11]}"


def load_pricing_data():
    print("Loading pricing data...")
    with open(PRICING_FILE) as f:
        data = json.load(f)
    pricing_by_ndc = {}
    for entry in data.get('pricing', []):
        ndc = entry.get('ndc11')
        if ndc:
            pricing_by_ndc[ndc] = entry
    print(f"  {len(pricing_by_ndc):,} priced NDCs loaded")
    return pricing_by_ndc


def load_rxnorm_entities():
    print("Loading RxNorm entities...")
    rxcui_to_entity = {}
    entity_id_to_entity = {}
    with open(RXNORM_ENTITIES_FILE) as f:
        for line in f:
            e = json.loads(line)
            eid = e.get('id')
            rxcui = name = tty = cid = smiles = inchikey = iupac = molweight = pmid = None
            for p in e.get('values', []):
                pid, val = p.get('property'), p.get('value')
                if pid == PROP_RXCUI: rxcui = val
                elif pid == PROP_NAME: name = val
                elif pid == PROP_TTY: tty = val
                elif pid == PROP_CID: cid = val
                elif pid == PROP_SMILES: smiles = val
                elif pid == PROP_INCHIKEY: inchikey = val
                elif pid == PROP_IUPAC: iupac = val
                elif pid == PROP_MOLWEIGHT: molweight = val
                elif pid == PROP_PMID: pmid = val
            if rxcui:
                entity_data = {
                    'id': eid, 'rxcui': rxcui, 'name': name or f"Unknown_{rxcui}",
                    'tty': tty, 'cid': cid, 'smiles': smiles, 'inchikey': inchikey,
                    'iupac_name': iupac, 'mol_weight': molweight, 'pmid': pmid
                }
                rxcui_to_entity[rxcui] = entity_data
                entity_id_to_entity[eid] = entity_data
    print(f"  {len(rxcui_to_entity):,} entities loaded")
    return rxcui_to_entity, entity_id_to_entity


def load_rxnorm_relations():
    print("Loading RxNorm relations...")
    forward = defaultdict(list)
    reverse = defaultdict(list)
    with open(RXNORM_RELATIONS_FILE) as f:
        for line in f:
            r = json.loads(line)
            fid, tid, rt = r.get('from'), r.get('to'), r.get('type')
            if fid and tid and rt:
                forward[fid].append((rt, tid))
                reverse[tid].append((rt, fid))
    print(f"  {sum(len(v) for v in forward.values()):,} relations")
    return dict(forward), dict(reverse)


def load_ndc_mappings():
    print("Loading NDC mappings...")
    with open(NDC_MERGED_FILE) as f:
        data = json.load(f)
    rxcui_to_ndcs = defaultdict(list)
    for entry in data.get('ndc_entries', []):
        rxcui = entry.get('rxcui')
        if rxcui:
            rxcui_to_ndcs[rxcui].append(entry)
    print(f"  {len(rxcui_to_ndcs):,} RxCUIs with NDCs")
    return dict(rxcui_to_ndcs)


def load_ndc_to_setid():
    with open(NDC_TO_SETID_FILE) as f:
        data = json.load(f)
    return data.get('ndc_to_setid', {})


def load_cid_mapping():
    with open(CID_MAPPING_FILE) as f:
        data = json.load(f)
    return data.get('cid_mapping', {})


def get_ingredients_from_min(min_id, forward, entity_id_to_entity):
    """Get ingredients from MIN via has_part -> IN"""
    ingredients = []
    for rel, ing_id in forward.get(min_id, []):
        if rel == REL_HAS_PART:
            ing_entity = entity_id_to_entity.get(ing_id)
            if ing_entity:
                ingredients.append({'rxcui': ing_entity['rxcui'], 'name': ing_entity['name']})
    return ingredients


def get_ingredients_from_scd(scd_id, forward, reverse, entity_id_to_entity):
    """Get ingredients for SCD via has_ingredients -> MIN -> has_part"""
    ingredients = []
    for rel, min_id in forward.get(scd_id, []):
        if rel == REL_HAS_INGREDIENTS:
            min_entity = entity_id_to_entity.get(min_id)
            if min_entity:
                for rel2, ing_id in forward.get(min_id, []):
                    if rel2 == REL_HAS_PART:
                        ing_entity = entity_id_to_entity.get(ing_id)
                        if ing_entity:
                            ingredients.append({'rxcui': ing_entity['rxcui'], 'name': ing_entity['name']})
    return ingredients


def is_combo_scd(scd_id, forward, reverse, entity_id_to_entity):
    """Check if SCD has multiple ingredients (combo)"""
    ingredients = get_ingredients_from_scd(scd_id, forward, reverse, entity_id_to_entity)
    return len(ingredients) > 1, ingredients


def find_pin_groups(in_entity_id, found_pins, found_scds, found_sbds, found_bns, found_dfs,
                    found_mins, entity_id_to_entity, forward, reverse):
    """
    Build PIN -> {scd, bn, sbd, df, min} groupings.
    For combo PINs (multiple PINs in one IN), creates MIN-style combo structure.
    """
    pin_groups = {}
    
    if not found_pins:
        return pin_groups, found_scds, found_sbds, found_bns, found_dfs
    
    for pin_rxcui, pin_entity in found_pins.items():
        pin_id = pin_entity['id']
        pin_groups[pin_rxcui] = {
            'entity': pin_entity,
            'scd': {},
            'bn': {},
            'sbd': {},
            'df': {},
            'min': {},
            'sbd_to_bn': {}
        }
        
        # Find SCDCs and BNs that point to this PIN via has_precise_ingredient
        for rel_type, child_id in reverse.get(pin_id, []):
            if rel_type != REL_HAS_PRECISE_INGREDIENT:
                continue
            
            child_entity = entity_id_to_entity.get(child_id)
            if not child_entity:
                continue
            
            child_rxcui = child_entity['rxcui']
            child_tty = child_entity['tty']
            
            # SCDC Path: SCDC -> constitutes -> SCD
            if child_tty == 'SCDC':
                scdc_id = child_entity['id']
                
                for rel2, target_id in forward.get(scdc_id, []):
                    if rel2 != REL_CONSTITUTES:
                        continue
                    
                    target_entity = entity_id_to_entity.get(target_id)
                    if not target_entity or target_entity['tty'] not in ('SCD', 'SBD'):
                        continue
                    
                    target_rxcui = target_entity['rxcui']
                    target_tty = target_entity['tty']
                    
                    # Handle SCD
                    if target_tty == 'SCD' and target_rxcui in found_scds:
                        is_combo, ingredients = is_combo_scd(target_entity['id'], forward, reverse, entity_id_to_entity)
                        
                        if is_combo:
                            for mid, ment in found_mins.items():
                                min_ings = {i['rxcui'] for i in get_ingredients_from_min(ment['id'], forward, entity_id_to_entity)}
                                scd_ings = {i['rxcui'] for i in ingredients}
                                if min_ings == scd_ings:
                                    pin_groups[pin_rxcui]['min'][mid] = ment
                                    break
                        
                        pin_groups[pin_rxcui]['scd'][target_rxcui] = target_entity
                        del found_scds[target_rxcui]
                        
                        for rel3, df_id in reverse.get(target_entity['id'], []):
                            if rel3 != REL_HAS_DOSE_FORM:
                                continue
                            df_entity = entity_id_to_entity.get(df_id)
                            if df_entity and df_entity['tty'] == 'DF' and df_entity['rxcui'] in found_dfs:
                                pin_groups[pin_rxcui]['df'][df_entity['rxcui']] = df_entity
                    
                    # Handle SBD (from SCDC -> constitutes -> SBD path)
                    elif target_tty == 'SBD' and target_rxcui in found_sbds:
                        pin_groups[pin_rxcui]['sbd'][target_rxcui] = target_entity
                        # Find the BN for this SBD to set brand_name
                        for rel3, bn_id in reverse.get(target_id, []):
                            if rel3 != REL_TRADENAME_OF:
                                continue
                            bn_entity = entity_id_to_entity.get(bn_id)
                            if bn_entity and bn_entity['tty'] == 'BN':
                                pin_groups[pin_rxcui]['bn'][bn_entity['rxcui']] = bn_entity
                                pin_groups[pin_rxcui]['sbd_to_bn'][target_rxcui] = bn_entity['rxcui']
                                break
                        del found_sbds[target_rxcui]
            
            # BN Path: BN discovered via PIN (biosimilar brands)
            # Don't check "in found_bns" - these are discovered via PIN, not IN
            elif child_tty == 'BN':
                bn_id = child_entity['id']
                bn_rxcui = child_rxcui
                pin_groups[pin_rxcui]['bn'][child_rxcui] = child_entity
                
                # Find SBDs via has_tradename
                for rel2, target_id in forward.get(bn_id, []):
                    if rel2 != REL_HAS_TRADENAME:
                        continue
                    
                    target_entity = entity_id_to_entity.get(target_id)
                    if not target_entity or target_entity['tty'] != 'SBD':
                        continue
                    
                    target_rxcui = target_entity['rxcui']
                    if target_rxcui in found_sbds:
                        pin_groups[pin_rxcui]['sbd'][target_rxcui] = target_entity
                        pin_groups[pin_rxcui]['sbd_to_bn'][target_rxcui] = bn_rxcui
                        del found_sbds[target_rxcui]
                
                # Also remove from found_bns if present
                if child_rxcui in found_bns:
                    del found_bns[child_rxcui]
    
    return pin_groups, found_scds, found_sbds, found_bns, found_dfs

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
    
    bn_to_sbd = defaultdict(list)
    brand_is_combo = {}
    
    # IN <- parents
    for rel_type, source_id in reverse.get(in_entity_id, []):
        source_entity = entity_id_to_entity.get(source_id)
        if not source_entity or source_entity['tty'] in BLOCKED_TTYS:
            continue
        
        source_rxcui = source_entity['rxcui']
        source_tty = source_entity['tty']
        
        if source_tty == 'PIN':
            found_pins[source_rxcui] = source_entity
        elif source_tty == 'MIN':
            found_mins[source_rxcui] = source_entity
        elif source_tty == 'BN':
            found_bns[source_rxcui] = source_entity
            brand_is_combo[source_rxcui] = False
        elif source_tty in ('SCDC', 'SCDF', 'SCDG'):
            for rel2, target_id in forward.get(source_id, []):
                if rel2 == REL_CONSTITUTES:
                    target_entity = entity_id_to_entity.get(target_id)
                    if target_entity and target_entity['tty'] == 'SCD':
                        found_scds[target_entity['rxcui']] = target_entity
                    elif target_entity and target_entity['tty'] == 'SBD':
                        found_sbds[target_entity['rxcui']] = target_entity
    
    # BN -> SBD
    for bn_rxcui, bn_entity in found_bns.items():
        bn_id = bn_entity['id']
        for rel_type, target_id in forward.get(bn_id, []):
            target_entity = entity_id_to_entity.get(target_id)
            if target_entity and target_entity['tty'] == 'SBD':
                found_sbds[target_entity['rxcui']] = target_entity
                bn_to_sbd[bn_rxcui].append(target_entity['rxcui'])
    
    # DFs from SCDs
    for scd_entity in list(found_scds.values()):
        for rel_type, df_id in reverse.get(scd_entity['id'], []):
            df_entity = entity_id_to_entity.get(df_id)
            if df_entity and df_entity['tty'] == 'DF':
                found_dfs[df_entity['rxcui']] = df_entity
    
    # PIN groups
    pin_groups, found_scds, found_sbds, found_bns, found_dfs = find_pin_groups(
        in_entity_id, found_pins, found_scds, found_sbds, found_bns, found_dfs,
        found_mins, entity_id_to_entity, forward, reverse
    )
    
    # MIN processing (existing logic, unchanged)
    min_data = {}
    for min_rxcui, min_entity in found_mins.items():
        min_id = min_entity['id']
        ingredients = get_ingredients_from_min(min_id, forward, entity_id_to_entity)
        min_data[min_rxcui] = {
            'entity': min_entity,
            'ingredients': ingredients,
            'is_combo': len(ingredients) > 1,
            'combo_scds': [],
            'combo_sbds': []
        }
    
    # Combo MIN -> SCD/SBD via ingredients_of
    for min_rxcui, min_info in min_data.items():
        if not min_info['is_combo']:
            continue
        min_entity = min_info['entity']
        min_id = min_entity['id']
        
        for rel_type, scd_id in forward.get(min_id, []):
            if rel_type != REL_INGREDIENTS_OF:
                continue
            
            scd_entity = entity_id_to_entity.get(scd_id)
            if not scd_entity or scd_entity['tty'] != 'SCD':
                continue
            
            # Check if this SCD already moved to a PIN
            already_moved = False
            for pg in pin_groups.values():
                if scd_entity['rxcui'] in pg['scd']:
                    already_moved = True
                    break
            
            if not already_moved and scd_entity['rxcui'] in found_scds:
                min_info['combo_scds'].append({
                    'rxcui': scd_entity['rxcui'],
                    'name': scd_entity['name'],
                    'tty': 'SCD',
                    'ingredients': min_info['ingredients'],
                    'ndcs': []
                })
                del found_scds[scd_entity['rxcui']]
            
            for rel2, sbd_id in forward.get(scd_id, []):
                if rel2 != REL_HAS_TRADENAME:
                    continue
                sbd_entity = entity_id_to_entity.get(sbd_id)
                if not sbd_entity or sbd_entity['tty'] != 'SBD':
                    continue
                
                # Check if SBD already moved to PIN
                already_moved = False
                for pg in pin_groups.values():
                    if sbd_entity['rxcui'] in pg['sbd']:
                        already_moved = True
                        break
                
                if already_moved or sbd_entity['rxcui'] not in found_sbds:
                    continue
                
                bn_rxc = bn_name = None
                for r, bid in reverse.get(sbd_id, []):
                    bnent = entity_id_to_entity.get(bid)
                    if bnent and bnent['tty'] == 'BN':
                        bn_rxc = bnent['rxcui']
                        bn_name = bnent['name']
                        break
                
                sbd_obj = {
                    'rxcui': sbd_entity['rxcui'],
                    'name': sbd_entity['name'],
                    'tty': 'SBD',
                    'ingredients': min_info['ingredients'],
                    'ndcs': []
                }
                if bn_rxc:
                    sbd_obj['brand_name'] = {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'}
                    if bn_rxc in brand_is_combo:
                        brand_is_combo[bn_rxc] = True
                
                min_info['combo_sbds'].append(sbd_obj)
                del found_sbds[sbd_entity['rxcui']]
    
    # Check remaining for combos
    scds_to_remove = []
    for scd_rxcui, scd_entity in list(found_scds.items()):
        is_combo, ingredients = is_combo_scd(scd_entity['id'], forward, reverse, entity_id_to_entity)
        if not is_combo:
            continue
        
        scds_to_remove.append(scd_rxcui)
        for min_rxcui, min_info in min_data.items():
            if not min_info['is_combo']:
                continue
            min_ing_rxcuis = {i['rxcui'] for i in min_info['ingredients']}
            scd_ing_rxcuis = {i['rxcui'] for i in ingredients}
            if min_ing_rxcuis == scd_ing_rxcuis:
                min_info['combo_scds'].append({
                    'rxcui': scd_rxcui,
                    'name': scd_entity['name'],
                    'tty': 'SCD',
                    'ingredients': ingredients,
                    'ndcs': []
                })
                break
    
    for rxcui in scds_to_remove:
        if rxcui in found_scds:
            del found_scds[rxcui]
    
    sbds_to_remove = []
    for sbd_rxcui, sbd_entity in list(found_sbds.items()):
        ingredients = []
        for rel, source_id in reverse.get(sbd_entity['id'], []):
            source_entity = entity_id_to_entity.get(source_id)
            if source_entity and source_entity['tty'] == 'SCD':
                ingredients = get_ingredients_from_scd(source_id, forward, reverse, entity_id_to_entity)
                break
        
        if len(ingredients) <= 1:
            continue
        
        sbds_to_remove.append(sbd_rxcui)
        bn_rxc = bn_name = None
        for r, bid in reverse.get(sbd_entity['id'], []):
            bnent = entity_id_to_entity.get(bid)
            if bnent and bnent['tty'] == 'BN':
                bn_rxc = bnent['rxcui']
                bn_name = bnent['name']
                break
        
        for min_rxcui, min_info in min_data.items():
            if not min_info['is_combo']:
                continue
            min_ing_rxcuis = {i['rxcui'] for i in min_info['ingredients']}
            sbd_ing_rxcuis = {i['rxcui'] for i in ingredients}
            if min_ing_rxcuis == sbd_ing_rxcuis:
                sbd_obj = {
                    'rxcui': sbd_rxcui,
                    'name': sbd_entity['name'],
                    'tty': 'SBD',
                    'ingredients': ingredients,
                    'ndcs': []
                }
                if bn_rxc:
                    sbd_obj['brand_name'] = {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'}
                    if bn_rxc in brand_is_combo:
                        brand_is_combo[bn_rxc] = True
                min_info['combo_sbds'].append(sbd_obj)
                break
    
    for rxcui in sbds_to_remove:
        if rxcui in found_sbds:
            del found_sbds[rxcui]
    
    # Build pin output (V22.2 - FIXED brand_name on nested SBDs)
    for pin_rxcui, pin_data in pin_groups.items():
        # Build SBD list with brand_name from sbd_to_bn mapping
        sbd_list = []
        for rxc, ent in pin_data['sbd'].items():
            sbd_obj = {'rxcui': rxc, 'name': ent['name'], 'tty': 'SBD', 'ndcs': []}
            # Look up which BN this SBD belongs to
            bn_rxcui = pin_data['sbd_to_bn'].get(rxc)
            if bn_rxcui and bn_rxcui in pin_data['bn']:
                bn_ent = pin_data['bn'][bn_rxcui]
                sbd_obj['brand_name'] = {'rxcui': bn_ent['rxcui'], 'name': bn_ent['name'], 'tty': 'BN'}
            sbd_list.append(sbd_obj)
        
        pin_obj = {
            'rxcui': pin_rxcui,
            'name': pin_data['entity']['name'],
            'tty': 'PIN',
            'scd': [{'rxcui': rxc, 'name': ent['name'], 'tty': 'SCD', 'ndcs': []} 
                    for rxc, ent in pin_data['scd'].items()],
            'bn': [{'rxcui': rxc, 'name': ent['name'], 'tty': 'BN'} 
                   for rxc, ent in pin_data['bn'].items()],
            'sbd': sbd_list,
            'df': [{'rxcui': rxc, 'name': ent['name'], 'tty': 'DF'} 
                   for rxc, ent in pin_data['df'].items()]
        }
        result['pin'].append(pin_obj)
    
    # Flat SCDs/SBDs/BNs/DFs
    for rxcui, entity in found_scds.items():
        result['scd'].append({'rxcui': rxcui, 'name': entity['name'], 'tty': 'SCD', 'ndcs': []})
    
    for rxcui, entity in found_sbds.items():
        brand_name = None
        for bn_rxc, sbd_list in bn_to_sbd.items():
            if rxcui in sbd_list and bn_rxc in found_bns:
                brand_name = {'rxcui': found_bns[bn_rxc]['rxcui'], 
                             'name': found_bns[bn_rxc]['name'], 'tty': 'BN'}
        sbd_obj = {'rxcui': rxcui, 'name': entity['name'], 'tty': 'SBD', 'ndcs': []}
        if brand_name:
            sbd_obj['brand_name'] = brand_name
        result['sbd'].append(sbd_obj)
    
    for rxcui, entity in found_bns.items():
        result['bn'].append({
            'rxcui': rxcui, 
            'name': entity['name'], 
            'tty': 'BN', 
            'is_combo': brand_is_combo.get(rxcui, False)
        })
    
    for min_rxcui, min_info in min_data.items():
        min_obj = {
            'rxcui': min_rxcui,
            'name': min_info['entity']['name'],
            'tty': 'MIN',
            'ingredients': min_info['ingredients']
        }
        if min_info['combo_scds']:
            min_obj['combo_scds'] = min_info['combo_scds']
        if min_info['combo_sbds']:
            min_obj['combo_sbds'] = min_info['combo_sbds']
        result['min'].append(min_obj)
    
    for rxcui, entity in found_dfs.items():
        result['df'].append({'rxcui': rxcui, 'name': entity['name'], 'tty': 'DF'})
    
    return result


def add_ndcs_with_pricing(connections, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc):
    extracted_priced = set()
    
    def process_ndc_entry(entry):
        formats = entry.get('ndc_formats', {})
        raw_ndc = formats.get('ndc11_hyphens') or entry.get('ndc', '')
        ndc11 = formats.get('ndc11_no_hyphens') or normalize_ndc(raw_ndc)
        if not ndc11:
            return None, False
        
        ndc11_hyphens = format_ndc11_hyphens(ndc11)
        ndc10 = formats.get('ndc10_hyphens')
        
        output = {'ndc': ndc11_hyphens}
        set_id = ndc_to_setid.get(ndc11_hyphens)
        if set_id:
            output['spl_set_id'] = set_id
        if ndc10:
            output['ndc10'] = ndc10
        if ndc11:
            output['ndc11_no_hyphens'] = ndc11
        
        pricing = pricing_by_ndc.get(ndc11)
        has_price = False
        if pricing:
            if pricing.get('has_nadac'):
                output['nadac_unit_price'] = pricing['nadac_unit_price']
                has_price = True
            if pricing.get('has_costplus'):
                output['costplus_unit_billing_price'] = pricing['costplus_unit_billing_price']
                has_price = True
        
        return output, has_price
    
    # Flat SCDs/SBDs
    for scd in connections.get('scd', []):
        scd_rxcui = scd.get('rxcui')
        if not scd_rxcui:
            continue
        for entry in rxcui_to_ndcs.get(scd_rxcui, []):
            ndc_obj, has_price = process_ndc_entry(entry)
            if ndc_obj:
                scd['ndcs'].append(ndc_obj)
                if has_price:
                    extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    for sbd in connections.get('sbd', []):
        sbd_rxcui = sbd.get('rxcui')
        if not sbd_rxcui:
            continue
        for entry in rxcui_to_ndcs.get(sbd_rxcui, []):
            ndc_obj, has_price = process_ndc_entry(entry)
            if ndc_obj:
                sbd['ndcs'].append(ndc_obj)
                if has_price:
                    extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    # V22.2: PIN-nested with explicit rxcui check
    for pin in connections.get('pin', []):
        for scd in pin.get('scd', []):
            scd_rxcui = scd.get('rxcui')
            if not scd_rxcui:
                continue
            for entry in rxcui_to_ndcs.get(scd_rxcui, []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    scd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
        
        for sbd in pin.get('sbd', []):
            sbd_rxcui = sbd.get('rxcui')
            if not sbd_rxcui:
                continue
            for entry in rxcui_to_ndcs.get(sbd_rxcui, []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    sbd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    # MIN combos
    for min_data in connections.get('min', []):
        for combo_scd in min_data.get('combo_scds', []):
            combo_rxcui = combo_scd.get('rxcui')
            if not combo_rxcui:
                continue
            for entry in rxcui_to_ndcs.get(combo_rxcui, []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    combo_scd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
        
        for combo_sbd in min_data.get('combo_sbds', []):
            combo_rxcui = combo_sbd.get('rxcui')
            if not combo_rxcui:
                continue
            for entry in rxcui_to_ndcs.get(combo_rxcui, []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    combo_sbd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    return connections, extracted_priced


def has_drug_connections(connections):
    return (len(connections.get('scd', [])) > 0 or 
            len(connections.get('sbd', [])) > 0 or 
            len(connections.get('min', [])) > 0 or
            len(connections.get('pin', [])) > 0)


def has_ndcs_anywhere(connections):
    for conn_type in ['scd', 'sbd']:
        for item in connections.get(conn_type, []):
            if item.get('ndcs'):
                return True
    
    for pin in connections.get('pin', []):
        for conn_type in ['scd', 'sbd']:
            for item in pin.get(conn_type, []):
                if item.get('ndcs'):
                    return True
    
    for min_data in connections.get('min', []):
        for combo_type in ['combo_scds', 'combo_sbds']:
            for combo in min_data.get(combo_type, []):
                if combo.get('ndcs'):
                    return True
    
    return False


def process_ingredient(name, rxcui, cid_mapping, rxcui_to_entity, entity_id_to_entity,
                       forward, reverse, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc):
    entity = rxcui_to_entity.get(rxcui, {})
    mapping = cid_mapping.get(rxcui, {})
    
    connections = find_connected_entities(rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse)
    
    if not has_drug_connections(connections):
        return None, set(), "no_connections"
    
    connections, extracted = add_ndcs_with_pricing(connections, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc)
    
    if not has_ndcs_anywhere(connections):
        return None, extracted, "no_ndcs"
    
    record = {
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
    
    for k in list(record.keys()):
        if record[k] is None:
            del record[k]
    
    return record, extracted, None


def main():
    parser = argparse.ArgumentParser(description='Extract GEO v22.2 - PIN Nesting with Combos (FIXED)')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    
    print("=" * 80)
    print("EXTRACT GEO V22.2 - PIN Nesting with Combo Support (FIXED)")
    print("  PINs now have nested SCDs/SBDs/BNs/DFs/NDCs")
    print("  SBDs nested under PIN get brand_name from BN")
    print("  Combo PINs get MIN-style treatment")
    print("=" * 80)
    
    pricing_by_ndc = load_pricing_data()
    rxcui_to_entity, entity_id_to_entity = load_rxnorm_entities()
    forward, reverse = load_rxnorm_relations()
    rxcui_to_ndcs = load_ndc_mappings()
    ndc_to_setid = load_ndc_to_setid()
    cid_mapping = load_cid_mapping()
    
    all_ingredients = [(e['name'], rxcui) for rxcui, e in rxcui_to_entity.items() if e['tty'] == 'IN']
    print(f"\nFound {len(all_ingredients):,} total IN entities")
    
    if args.debug:
        all_ingredients = all_ingredients[:5]
    
    print(f"\nProcessing {len(all_ingredients):,} ingredients...")
    
    stats = {'total': 0, 'passed': 0, 'no_connections': 0, 'no_ndcs': 0, 'with_pins': 0}
    all_priced = set()
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(OUTPUT_FILE, 'w') as f:
        for idx, (name, rxcui) in enumerate(all_ingredients):
            if (idx + 1) % 100 == 0:
                print(f"  {idx + 1:,} / {len(all_ingredients):,} (passed: {stats['passed']:,}, with PINs: {stats['with_pins']:,})")
            
            stats['total'] += 1
            
            result, extracted, fail_reason = process_ingredient(
                name, rxcui, cid_mapping, rxcui_to_entity, entity_id_to_entity,
                forward, reverse, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc
            )
            
            all_priced.update(extracted)
            
            if result is None:
                if fail_reason == "no_ndcs":
                    stats['no_ndcs'] = stats.get('no_ndcs', 0) + 1
                elif fail_reason == "no_connections":
                    stats['no_connections'] += 1
                else:
                    stats['other'] = stats.get('other', 0) + 1
                continue
            
            if result['connections'].get('pin'):
                stats['with_pins'] += 1
            
            stats['passed'] += 1
            f.write(json.dumps(result, separators=(',', ':')) + '\n')
    
    print(f"\n{'=' * 80}")
    print("EXTRACTION COMPLETE")
    print(f"{'=' * 80}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Total: {stats['passed']:,} / {stats['total']:,}")
    print(f"With PIN groups: {stats['with_pins']:,}")
    print(f"Priced NDCs extracted: {len(all_priced):,} / {len(pricing_by_ndc):,}")
    print(f"Coverage: {len(all_priced)/len(pricing_by_ndc)*100:.1f}%" if pricing_by_ndc else "N/A")
    print(f"\nFilters:")
    print(f"  No connections: {stats.get('no_connections', 0):,}")
    print(f"  No NDCs: {stats.get('no_ndcs', 0):,}")
    print(f"\nV22.2: PIN nesting with brand_name on SBDs")
    print("=" * 80)


if __name__ == "__main__":
    main()
