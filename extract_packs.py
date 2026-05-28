#!/usr/bin/env python3
"""
extract_packs.py
Extracts BPCK/GPCK entities and wires them to their parent SCDs/SBDs
using Geo ontology UUIDs.
"""
import json
import uuid
from collections import defaultdict
from pathlib import Path

# ── Pipeline UUIDs (pharma_schema / what's in the JSONL files) ──────────────
P_SCD_TYPE     = '02ee5c381f55585485547fbed6b47a79'
P_SBD_TYPE     = 'ab53698cdc9b59ae9b48b6f8131254b3'
P_GPCK_TYPE    = 'fe41d17b4cc653bdb2df66c60050470d'
P_BPCK_TYPE    = '613d979f295a56e89d32a4238e7902dd'
P_CONTAINS     = 'ab9a31412f9e547b8029497eb30628c0'
P_CONTAINED_IN = '987c2a6519b55e89b56eb4c83eb1465b'
P_NAME_PROP    = 'a126ca530c8e48d5b88882c734c38935'
P_RXCUI_PROP   = 'c6f36f8a8e22546ea7618ac008d2f91e'

# ── Geo ontology UUIDs (constants.ts) ────────────────────────────────────────
G_GPCK_TYPE        = 'c71ac4f342354c1d82da3ccfae274786'
G_BPCK_TYPE        = '78adf4017a5745e5a024771ae123d77b'
G_NAME_PROP        = 'a126ca530c8e48d5b88882c734c38935'  # same
G_RXCUI_PROP       = 'e6c50e227460442cab646a48f235459a'  # different!
G_GENERIC_PACKS_REL = '3490c0442f3e49819cde4293356d89e2'
G_BRAND_PACKS_REL   = '80913eb0c104490391bfbfe25ef71e7c'

DATA_DIR = Path('/mnt/fast_raid/server_projects/Geo/graph_workshop/data/grc20_v2')


def gen_id(seed: str) -> str:
    ns = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
    return str(uuid.uuid5(ns, seed)).replace('-', '')


def get_prop(entity: dict, prop_id: str) -> str:
    for v in entity.get('values', []):
        if v.get('property') == prop_id:
            return v.get('value', '')
    return ''


def load_entities() -> dict:
    entities = {}
    with open(DATA_DIR / 'grc20_merged_entities.jsonl') as f:
        for line in f:
            e = json.loads(line)
            entities[e['id']] = e
    print(f"  Loaded {len(entities):,} entities")
    return entities


def load_pack_relations() -> tuple[dict, dict]:
    """Returns (pack_id -> [drug_ids], drug_id -> [pack_ids])"""
    pack_contains = defaultdict(set)
    drug_in_pack  = defaultdict(set)

    with open(DATA_DIR / 'grc20_merged_relations.jsonl') as f:
        for line in f:
            r = json.loads(line)
            t = r.get('type')
            if t == P_CONTAINS:
                pack_contains[r['from']].add(r['to'])
                drug_in_pack[r['to']].add(r['from'])
            elif t == P_CONTAINED_IN:
                drug_in_pack[r['from']].add(r['to'])
                pack_contains[r['to']].add(r['from'])

    return (
        {k: list(v) for k, v in pack_contains.items()},
        {k: list(v) for k, v in drug_in_pack.items()},
    )


def build_pack_entities(entities: dict) -> list[dict]:
    """
    Convert BPCK/GPCK pipeline entities to Geo ontology format.
    Entity IDs are preserved (same UUID, just re-typed).
    """
    out = []
    for eid, e in entities.items():
        types = e.get('types', [])
        if P_GPCK_TYPE in types:
            geo_type = G_GPCK_TYPE
        elif P_BPCK_TYPE in types:
            geo_type = G_BPCK_TYPE
        else:
            continue

        name  = get_prop(e, P_NAME_PROP)
        rxcui = get_prop(e, P_RXCUI_PROP)

        out.append({
            "id": eid,
            "name": name,
            "types": [geo_type],
            "values": [
                {"property": G_NAME_PROP,  "value": name},
                {"property": G_RXCUI_PROP, "value": rxcui},
            ]
        })

    print(f"  Built {len(out):,} pack entities (BPCK+GPCK)")
    return out


def build_pack_relations(entities: dict, drug_in_pack: dict) -> list[dict]:
    """
    For each SCD/SBD that lives in a pack, emit:
      SCD → GENERIC_PACKS  → GPCK
      SBD → BRAND_PACKS    → BPCK
    """
    out = []
    for drug_id, pack_ids in drug_in_pack.items():
        if drug_id not in entities:
            continue
        drug = entities[drug_id]
        drug_types = drug.get('types', [])

        is_scd = P_SCD_TYPE in drug_types
        is_sbd = P_SBD_TYPE in drug_types
        if not (is_scd or is_sbd):
            continue

        for pack_id in pack_ids:
            if pack_id not in entities:
                continue
            pack = entities[pack_id]
            pack_types = pack.get('types', [])

            # SCD → Generic Pack
            if is_scd and P_GPCK_TYPE in pack_types:
                out.append({
                    "id": gen_id(f"geo_pack_rel_{drug_id}_{pack_id}"),
                    "type": G_GENERIC_PACKS_REL,
                    "from": drug_id,
                    "to":   pack_id,
                    "values": []
                })

            # SBD → Brand Pack
            elif is_sbd and P_BPCK_TYPE in pack_types:
                out.append({
                    "id": gen_id(f"geo_pack_rel_{drug_id}_{pack_id}"),
                    "type": G_BRAND_PACKS_REL,
                    "from": drug_id,
                    "to":   pack_id,
                    "values": []
                })

            # Edge case: SCD in a BPCK (e.g. clarithromycin in Omeclamox)
            elif is_scd and P_BPCK_TYPE in pack_types:
                out.append({
                    "id": gen_id(f"geo_pack_rel_{drug_id}_{pack_id}"),
                    "type": G_BRAND_PACKS_REL,
                    "from": drug_id,
                    "to":   pack_id,
                    "values": []
                })

    print(f"  Built {len(out):,} pack relations")
    return out


def main():
    print("Loading pipeline data...")
    entities = load_entities()
    pack_contains, drug_in_pack = load_pack_relations()
    print(f"  Packs: {len(pack_contains):,}  |  Drugs in packs: {len(drug_in_pack):,}")

    print("\nBuilding Geo pack entities...")
    pack_entities = build_pack_entities(entities)

    print("\nBuilding Geo pack relations...")
    pack_relations = build_pack_relations(entities, drug_in_pack)

    # Write output
    out_entities = DATA_DIR / 'geo_pack_entities.jsonl'
    out_relations = DATA_DIR / 'geo_pack_relations.jsonl'

    with open(out_entities, 'w') as f:
        for e in pack_entities:
            f.write(json.dumps(e) + '\n')

    with open(out_relations, 'w') as f:
        for r in pack_relations:
            f.write(json.dumps(r) + '\n')

    print(f"\nWrote:")
    print(f"  {out_entities}  ({len(pack_entities):,} entities)")
    print(f"  {out_relations}  ({len(pack_relations):,} relations)")

    # Quick sanity check
    gpck_count = sum(1 for e in pack_entities if G_GPCK_TYPE in e['types'])
    bpck_count = sum(1 for e in pack_entities if G_BPCK_TYPE in e['types'])
    grel_count = sum(1 for r in pack_relations if r['type'] == G_GENERIC_PACKS_REL)
    brel_count = sum(1 for r in pack_relations if r['type'] == G_BRAND_PACKS_REL)
    print(f"\n  GPCK entities: {gpck_count}  |  BPCK entities: {bpck_count}")
    print(f"  GPCK relations: {grel_count}  |  BPCK relations: {brel_count}")


if __name__ == '__main__':
    main()
