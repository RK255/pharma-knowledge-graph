# connections.py
# Graph traversal — lifted verbatim from v22.6. Zero structural changes.
from collections import defaultdict
from config import (
    REL_HAS_PRECISE_INGREDIENT, REL_CONSTITUTES, REL_HAS_TRADENAME,
    REL_TRADENAME_OF, REL_HAS_DOSE_FORM, REL_HAS_PART, REL_INGREDIENTS_OF,
    REL_HAS_INGREDIENTS, BLOCKED_TTYS,
    REL_INGREDIENT_OF
)
from name_formatter import reformat_scd_name, reformat_sbd_name


def get_ingredients_from_min(min_id, forward, entity_id_to_entity):
    ingredients = []
    for rel, ing_id in forward.get(min_id, []):
        if rel == REL_HAS_PART:
            ing_entity = entity_id_to_entity.get(ing_id)
            if ing_entity:
                ingredients.append({'rxcui': ing_entity['rxcui'], 'name': ing_entity['name']})
    return ingredients


def get_ingredients_from_scd(scd_id, forward, reverse, entity_id_to_entity):
    ingredients = []
    for rel, min_id in forward.get(scd_id, []):
        if rel == REL_HAS_INGREDIENTS:
            for rel2, ing_id in forward.get(min_id, []):
                if rel2 == REL_HAS_PART:
                    ing_entity = entity_id_to_entity.get(ing_id)
                    if ing_entity:
                        ingredients.append({'rxcui': ing_entity['rxcui'], 'name': ing_entity['name']})
    return ingredients


def is_combo_scd(scd_id, forward, reverse, entity_id_to_entity):
    ingredients = get_ingredients_from_scd(scd_id, forward, reverse, entity_id_to_entity)
    return len(ingredients) > 1, ingredients


def find_pin_groups(in_entity_id, found_pins, found_scds, found_sbds, found_bns, found_dfs,
                    found_mins, entity_id_to_entity, forward, reverse):
    pin_groups = {}

    if not found_pins:
        return pin_groups, found_scds, found_sbds, found_bns, found_dfs

    for pin_rxcui, pin_entity in found_pins.items():
        pin_id = pin_entity['id']
        for rel_type, candidate_id in reverse.get(pin_id, []):
            if rel_type != REL_HAS_PART:
                continue
            candidate = entity_id_to_entity.get(candidate_id)
            if not candidate or candidate.get('tty') != 'MIN':
                continue
            min_rxcui = candidate['rxcui']
            if min_rxcui not in found_mins:
                found_mins[min_rxcui] = candidate

    combo_scd_to_min = {}
    for scd_rxcui, scd_entity in list(found_scds.items()):
        is_combo, ingredients = is_combo_scd(scd_entity['id'], forward, reverse, entity_id_to_entity)
        if not is_combo:
            continue
        ing_set = {i['rxcui'] for i in ingredients}
        for mid, ment in found_mins.items():
            min_ings = {
                i['rxcui']
                for i in get_ingredients_from_min(ment['id'], forward, entity_id_to_entity)
            }
            if min_ings == ing_set:
                combo_scd_to_min[scd_rxcui] = mid
                break

    combo_sbd_rxcuis = set()
    for scd_rxcui in combo_scd_to_min:
        scd_entity = found_scds.get(scd_rxcui)
        if not scd_entity:
            continue
        for rel3, sbd_id in forward.get(scd_entity['id'], []):
            if rel3 != REL_HAS_TRADENAME:
                continue
            sbd_entity = entity_id_to_entity.get(sbd_id)
            if sbd_entity and sbd_entity.get('tty') == 'SBD':
                combo_sbd_rxcuis.add(sbd_entity['rxcui'])

    for pin_rxcui, pin_entity in found_pins.items():
        pin_id = pin_entity['id']
        pin_groups[pin_rxcui] = {
            'entity':        pin_entity,
            'scd':           {},
            'bn':            {},
            'sbd':           {},
            'df':            {},
            'min':           {},
            'sbd_to_bn':     {},
            '_bn_confirmed': set(),
        }

        for rel_type, child_id in reverse.get(pin_id, []):
            if rel_type != REL_HAS_PRECISE_INGREDIENT:
                continue
            child_entity = entity_id_to_entity.get(child_id)
            if not child_entity:
                continue
            child_rxcui = child_entity['rxcui']
            child_tty   = child_entity['tty']

            if child_tty == 'SCDC':
                for rel2, target_id in forward.get(child_id, []):
                    if rel2 != REL_CONSTITUTES:
                        continue
                    target_entity = entity_id_to_entity.get(target_id)
                    if not target_entity:
                        continue
                    target_rxcui = target_entity['rxcui']
                    target_tty   = target_entity['tty']

                    if target_tty == 'SCD' and target_rxcui in found_scds:
                        if target_rxcui in combo_scd_to_min:
                            owning_min = combo_scd_to_min[target_rxcui]
                            pin_groups[pin_rxcui]['min'][owning_min] = found_mins[owning_min]
                            continue
                        pin_groups[pin_rxcui]['scd'][target_rxcui] = target_entity
                        del found_scds[target_rxcui]
                        for rel3, df_id in forward.get(target_id, []):
                            if rel3 == REL_HAS_DOSE_FORM:
                                df_entity = entity_id_to_entity.get(df_id)
                                if df_entity and df_entity['tty'] == 'DF' and df_entity['rxcui'] in found_dfs:
                                    pin_groups[pin_rxcui]['df'][df_entity['rxcui']] = df_entity
                        for rel3, sbd_id in forward.get(target_id, []):
                            if rel3 != REL_HAS_TRADENAME:
                                continue
                            sbd_entity = entity_id_to_entity.get(sbd_id)
                            if not sbd_entity or sbd_entity.get('tty') != 'SBD':
                                continue
                            sbd_rxcui = sbd_entity['rxcui']
                            already_placed = any(sbd_rxcui in pg['sbd'] for pg in pin_groups.values())
                            if already_placed or sbd_rxcui in combo_sbd_rxcuis:
                                continue
                            pin_groups[pin_rxcui]['sbd'][sbd_rxcui] = sbd_entity
                            for rel4, bn_id in reverse.get(sbd_id, []):
                                if rel4 not in (REL_TRADENAME_OF, REL_INGREDIENT_OF):
                                    continue
                                bn_entity = entity_id_to_entity.get(bn_id)
                                if bn_entity and bn_entity.get('tty') == 'BN':
                                    bn_rxcui_local = bn_entity['rxcui']
                                    pin_groups[pin_rxcui]['bn'][bn_rxcui_local]       = bn_entity
                                    pin_groups[pin_rxcui]['sbd_to_bn'][sbd_rxcui]     = bn_rxcui_local
                                    pin_groups[pin_rxcui]['_bn_confirmed'].add(bn_rxcui_local)
                                    if bn_rxcui_local in found_bns:
                                        del found_bns[bn_rxcui_local]
                                    break
                            found_sbds.pop(sbd_rxcui, None)

                    elif target_tty == 'SBD' and target_rxcui in found_sbds:
                        if target_rxcui in combo_sbd_rxcuis:
                            continue
                        pin_groups[pin_rxcui]['sbd'][target_rxcui] = target_entity
                        for rel3, bn_id in reverse.get(target_id, []):
                            if rel3 not in (REL_TRADENAME_OF, REL_INGREDIENT_OF):
                                continue
                            bn_entity = entity_id_to_entity.get(bn_id)
                            if bn_entity and bn_entity.get('tty') == 'BN':
                                bn_rxcui_local = bn_entity['rxcui']
                                pin_groups[pin_rxcui]['bn'][bn_rxcui_local]        = bn_entity
                                pin_groups[pin_rxcui]['sbd_to_bn'][target_rxcui]   = bn_rxcui_local
                                pin_groups[pin_rxcui]['_bn_confirmed'].add(bn_rxcui_local)
                                break
                        del found_sbds[target_rxcui]

            elif child_tty == 'BN':
                bn_id    = child_entity['id']
                bn_rxcui = child_rxcui
                
                staged_sbds = []
                for rel2, target_id in forward.get(bn_id, []):
                    if rel2 != REL_HAS_TRADENAME:
                        continue
                    target_entity = entity_id_to_entity.get(target_id)
                    if not target_entity or target_entity.get('tty') != 'SBD':
                        continue
                    target_rxcui = target_entity['rxcui']
                    if target_rxcui not in found_sbds:
                        continue
                    if target_rxcui in combo_sbd_rxcuis:
                        continue
                    staged_sbds.append((target_rxcui, target_entity))
                if staged_sbds:
                    pin_groups[pin_rxcui]['bn'][bn_rxcui] = child_entity
                    pin_groups[pin_rxcui]['_bn_confirmed'].add(bn_rxcui)
                    for sbd_rxcui, sbd_entity in staged_sbds:
                        pin_groups[pin_rxcui]['sbd'][sbd_rxcui]       = sbd_entity
                        pin_groups[pin_rxcui]['sbd_to_bn'][sbd_rxcui] = bn_rxcui
                        del found_sbds[sbd_rxcui]
                if bn_rxcui in found_bns:
                    del found_bns[bn_rxcui]
                
                
                staged_sbds = []
                for rel2, target_id in forward.get(bn_id, []):
                    if rel2 != REL_HAS_TRADENAME:
                        continue
                    target_entity = entity_id_to_entity.get(target_id)
                    if not target_entity or target_entity.get('tty') != 'SBD':
                        continue
                    target_rxcui = target_entity['rxcui']
                    if target_rxcui not in found_sbds:
                         continue
                    if target_rxcui in combo_sbd_rxcuis:
                        continue
                # FIX 2: belt-and-suspenders — reject combo SBDs whose parent SCD
                # has multiple SCDC constituents, regardless of combo_sbd_rxcuis
                    _parent_is_combo = False
                    for _r, _sid in reverse.get(target_id, []):
                        _se = entity_id_to_entity.get(_sid, {})
                        if _se.get('tty') == 'SCD':
                            _scdc_count = sum(
                                1 for _r2, _cid in reverse.get(_sid, [])
                                if _r2 == REL_CONSTITUTES
                                and entity_id_to_entity.get(_cid, {}).get('tty') == 'SCDC'
                            )
                            _parent_is_combo = _scdc_count > 1
                            break
                        if _parent_is_combo:
                            continue
                        staged_sbds.append((target_rxcui, target_entity))

    for pg in pin_groups.values():
        pg.pop('_bn_confirmed', None)

    return pin_groups, found_scds, found_sbds, found_bns, found_dfs


def find_connected_entities(in_rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse):
    from config import REL_INGREDIENT_OF, REL_PRECISE_INGREDIENT_OF

    result = {'scd': [], 'sbd': [], 'bn': [], 'pin': [], 'min': [], 'df': []}

    in_entity = rxcui_to_entity.get(in_rxcui)
    if not in_entity:
        return result

    in_entity_id = in_entity['id']

    found_scds = {}
    found_sbds = {}
    found_bns  = {}
    found_pins = {}
    found_mins = {}
    found_dfs  = {}
    bn_to_sbd  = defaultdict(list)
    brand_is_combo = {}

    for rel_type, source_id in reverse.get(in_entity_id, []):
        source_entity = entity_id_to_entity.get(source_id)
        if not source_entity or source_entity['tty'] in BLOCKED_TTYS:
            continue
        source_rxcui = source_entity['rxcui']
        source_tty   = source_entity['tty']
        if source_tty == 'PIN':
            found_pins[source_rxcui] = source_entity
        elif source_tty == 'MIN':
            found_mins[source_rxcui] = source_entity
        elif source_tty == 'BN':
            found_bns[source_rxcui]      = source_entity
            brand_is_combo[source_rxcui] = False
        elif source_tty in ('SCDC', 'SCDF', 'SCDG'):
            for rel2, target_id in forward.get(source_id, []):
                if rel2 == REL_CONSTITUTES:
                    target_entity = entity_id_to_entity.get(target_id)
                    if target_entity and target_entity['tty'] == 'SCD':
                        found_scds[target_entity['rxcui']] = target_entity
                    elif target_entity and target_entity['tty'] == 'SBD':
                        found_sbds[target_entity['rxcui']] = target_entity

    for bn_rxcui, bn_entity in found_bns.items():
        for rel_type, target_id in forward.get(bn_entity['id'], []):
            if rel_type == REL_HAS_TRADENAME:
                target_entity = entity_id_to_entity.get(target_id)
                if target_entity and target_entity['tty'] == 'SBD':
                    found_sbds[target_entity['rxcui']] = target_entity
                    bn_to_sbd[bn_rxcui].append(target_entity['rxcui'])

    for scd_entity in list(found_scds.values()):
        for rel_type, df_id in forward.get(scd_entity['id'], []):
            if rel_type == REL_HAS_DOSE_FORM:
                df_entity = entity_id_to_entity.get(df_id)
                if df_entity and df_entity['tty'] == 'DF':
                    found_dfs[df_entity['rxcui']] = df_entity

    for pin_entity in list(found_pins.values()):
        for _rel, source_id in reverse.get(pin_entity['id'], []):
            source_entity = entity_id_to_entity.get(source_id)
            if source_entity and source_entity['tty'] == 'MIN':
                if source_entity['rxcui'] not in found_mins:
                    found_mins[source_entity['rxcui']] = source_entity

    pin_groups, found_scds, found_sbds, found_bns, found_dfs = find_pin_groups(
        in_entity_id, found_pins, found_scds, found_sbds, found_bns, found_dfs,
        found_mins, entity_id_to_entity, forward, reverse
    )

    min_data = {}
    for min_rxcui, min_entity in found_mins.items():
        ingredients = get_ingredients_from_min(min_entity['id'], forward, entity_id_to_entity)
        min_data[min_rxcui] = {
            'entity':      min_entity,
            'ingredients': ingredients,
            'is_combo':    len(ingredients) > 1,
            'combo_scds':  [],
            'combo_sbds':  []
        }

    for min_rxcui, min_info in min_data.items():
        if not min_info['is_combo']:
            continue
        min_id = min_info['entity']['id']
        for rel_type, scd_id in forward.get(min_id, []):
            if rel_type != REL_INGREDIENTS_OF:
                continue
            scd_entity = entity_id_to_entity.get(scd_id)
            if not scd_entity or scd_entity['tty'] != 'SCD':
                continue
            already_moved = any(scd_entity['rxcui'] in pg['scd'] for pg in pin_groups.values())
            if not already_moved and scd_entity['rxcui'] in found_scds:
                min_info['combo_scds'].append({
                    'rxcui':       scd_entity['rxcui'],
                    'name':        reformat_scd_name(scd_entity['name']),
                    'tty':         'SCD',
                    'ingredients': min_info['ingredients'],
                    'ndcs':        []
                })
                del found_scds[scd_entity['rxcui']]
            for rel2, sbd_id in forward.get(scd_id, []):
                if rel2 != REL_HAS_TRADENAME:
                    continue
                sbd_entity = entity_id_to_entity.get(sbd_id)
                if not sbd_entity or sbd_entity['tty'] != 'SBD':
                    continue
                already_moved = any(sbd_entity['rxcui'] in pg['sbd'] for pg in pin_groups.values())
                if already_moved or sbd_entity['rxcui'] not in found_sbds:
                    continue
                bn_rxc = bn_name = None
                for r, bid in reverse.get(sbd_id, []):
                    bnent = entity_id_to_entity.get(bid)
                    if bnent and bnent['tty'] == 'BN':
                        bn_rxc  = bnent['rxcui']
                        bn_name = bnent['name']
                        break
                sbd_obj = {
                    'rxcui':       sbd_entity['rxcui'],
                    'name':        reformat_sbd_name(
                                       sbd_entity['name'],
                                       {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'} if bn_rxc else None
                                   ),
                    'tty':         'SBD',
                    'ingredients': min_info['ingredients'],
                    'ndcs':        []
                }
                if bn_rxc:
                    sbd_obj['brand_name'] = {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'}
                    brand_is_combo[bn_rxc] = True
                min_info['combo_sbds'].append(sbd_obj)
                del found_sbds[sbd_entity['rxcui']]

    scds_to_remove = []
    for scd_rxcui, scd_entity in list(found_scds.items()):
        is_combo, ingredients = is_combo_scd(scd_entity['id'], forward, reverse, entity_id_to_entity)
        if not is_combo:
            continue
        scds_to_remove.append(scd_rxcui)
        for min_info in min_data.values():
            if not min_info['is_combo']:
                continue
            if {i['rxcui'] for i in min_info['ingredients']} == {i['rxcui'] for i in ingredients}:
                min_info['combo_scds'].append({
                    'rxcui':       scd_rxcui,
                    'name':        reformat_scd_name(scd_entity['name']),
                    'tty':         'SCD',
                    'ingredients': ingredients,
                    'ndcs':        []
                })
                break
    for rxcui in scds_to_remove:
        found_scds.pop(rxcui, None)

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
                bn_rxc  = bnent['rxcui']
                bn_name = bnent['name']
                break
        for min_info in min_data.values():
            if not min_info['is_combo']:
                continue
            if {i['rxcui'] for i in min_info['ingredients']} == {i['rxcui'] for i in ingredients}:
                sbd_obj = {
                    'rxcui':       sbd_rxcui,
                    'name':        reformat_sbd_name(
                                       sbd_entity['name'],
                                       {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'} if bn_rxc else None
                                   ),
                    'tty':         'SBD',
                    'ingredients': ingredients,
                    'ndcs':        []
                }
                if bn_rxc:
                    sbd_obj['brand_name'] = {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'}
                    brand_is_combo[bn_rxc] = True
                min_info['combo_sbds'].append(sbd_obj)
                break
    for rxcui in sbds_to_remove:
        found_sbds.pop(rxcui, None)

    # ── Build output ─────────────────────────────────────────────────────────

    for pin_rxcui, pin_data in pin_groups.items():
        sbd_list = []
        for rxc, ent in pin_data['sbd'].items():
            bn_rxcui = pin_data['sbd_to_bn'].get(rxc)
            bn_info  = (
                {'rxcui': bn_rxcui, 'name': pin_data['bn'][bn_rxcui]['name'], 'tty': 'BN'}
                if bn_rxcui and bn_rxcui in pin_data['bn'] else None
            )
            sbd_obj = {
                'rxcui': rxc,
                'name':  reformat_sbd_name(ent['name'], bn_info),
                'tty':   'SBD',
                'ndcs':  []
            }
            if bn_info:
                sbd_obj['brand_name'] = bn_info
            sbd_list.append(sbd_obj)

        pin_obj = {
            'rxcui': pin_rxcui,
            'name':  pin_data['entity']['name'],
            'tty':   'PIN',
            'scd':   [{'rxcui': rxc, 'name': reformat_scd_name(ent['name']), 'tty': 'SCD', 'ndcs': []}
                      for rxc, ent in pin_data['scd'].items()],
            'bn':    [{'rxcui': rxc, 'name': ent['name'], 'tty': 'BN'}
                      for rxc, ent in pin_data['bn'].items()],
            'sbd':   sbd_list,
            'df':    [{'rxcui': rxc, 'name': ent['name'], 'tty': 'DF'}
                      for rxc, ent in pin_data['df'].items()]
        }
        result['pin'].append(pin_obj)

    for rxcui, entity in found_scds.items():
        result['scd'].append({
            'rxcui': rxcui,
            'name':  reformat_scd_name(entity['name']),
            'tty':   'SCD',
            'ndcs':  []
        })

    for rxcui, entity in found_sbds.items():
        brand_name = None
        for bn_rxc, sbd_list in bn_to_sbd.items():
            if rxcui in sbd_list and bn_rxc in found_bns:
                brand_name = {'rxcui': bn_rxc, 'name': found_bns[bn_rxc]['name'], 'tty': 'BN'}
        sbd_obj = {
            'rxcui': rxcui,
            'name':  reformat_sbd_name(entity['name'], brand_name),
            'tty':   'SBD',
            'ndcs':  []
        }
        if brand_name:
            sbd_obj['brand_name'] = brand_name
        result['sbd'].append(sbd_obj)

    for rxcui, entity in found_bns.items():
        result['bn'].append({
            'rxcui':    rxcui,
            'name':     entity['name'],
            'tty':      'BN',
            'is_combo': brand_is_combo.get(rxcui, False)
        })

    for min_rxcui, min_info in min_data.items():
        min_obj = {
            'rxcui':       min_rxcui,
            'name':        min_info['entity']['name'],
            'tty':         'MIN',
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
