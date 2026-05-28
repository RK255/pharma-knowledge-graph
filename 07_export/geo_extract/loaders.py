# loaders.py
import json
from collections import defaultdict
from config import (
    RXNORM_ENTITIES_FILE, RXNORM_RELATIONS_FILE, CID_MAPPING_FILE,
    NDC_MERGED_FILE, NDC_TO_SETID_FILE, PRICING_FILE,
    PROP_RXCUI, PROP_NAME, PROP_TTY, PROP_CID, PROP_SMILES,
    PROP_INCHIKEY, PROP_IUPAC, PROP_MOLWEIGHT, PROP_PMID
)


def load_pricing_data():
    print("Loading pricing data...")
    with open(PRICING_FILE) as f:
        data = json.load(f)
    pricing_by_ndc = {
        e.get('ndc11'): e
        for e in data.get('pricing', [])
        if e.get('ndc11')
    }
    print(f"  {len(pricing_by_ndc):,} priced NDCs loaded")
    return pricing_by_ndc


def load_rxnorm_entities():
    print("Loading RxNorm entities...")
    rxcui_to_entity     = {}
    entity_id_to_entity = {}

    with open(RXNORM_ENTITIES_FILE) as f:
        for line in f:
            e     = json.loads(line)
            props = {p['property']: p['value'] for p in e.get('values', [])}
            entity_data = {
                'id':         e.get('id'),
                'rxcui':      props.get(PROP_RXCUI),
                'name':       props.get(PROP_NAME),
                'tty':        props.get(PROP_TTY),
                'cid':        props.get(PROP_CID),
                'smiles':     props.get(PROP_SMILES),
                'inchikey':   props.get(PROP_INCHIKEY),
                'iupac_name': props.get(PROP_IUPAC),
                'mol_weight': props.get(PROP_MOLWEIGHT),
                'pmid':       props.get(PROP_PMID),
            }
            if entity_data['rxcui']:
                rxcui_to_entity[entity_data['rxcui']]  = entity_data
                entity_id_to_entity[entity_data['id']] = entity_data

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
        if entry.get('rxcui'):
            rxcui_to_ndcs[entry['rxcui']].append(entry)

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
