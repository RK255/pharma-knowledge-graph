#!/usr/bin/env python3
"""
quarterback.py — Geo Extract v25
=================================
Modular refactor of extract_geo_v24.py.

Usage:
  python3 quarterback.py [--debug]
"""
import json
import argparse
import sys
from pathlib import Path

# Make sure the package directory is on the path when called from outside
sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR, OUTPUT_FILE
from loaders import (
    load_pricing_data, load_rxnorm_entities, load_rxnorm_relations,
    load_ndc_mappings, load_ndc_to_setid, load_cid_mapping
)
from pack_resolver import build_pack_index
from connections import find_connected_entities
from ndc_enricher import add_ndcs_with_pricing
from filters import has_drug_connections, has_ndcs_anywhere


def process_ingredient(name, rxcui, cid_mapping, rxcui_to_entity, entity_id_to_entity,
                       forward, reverse, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc,
                       drug_to_packs):
    entity  = rxcui_to_entity.get(rxcui, {})
    mapping = cid_mapping.get(rxcui, {})

    connections = find_connected_entities(
        rxcui, rxcui_to_entity, entity_id_to_entity, forward, reverse
    )

    if not has_drug_connections(connections):
        return None, set(), "no_connections"

    connections, extracted = add_ndcs_with_pricing(
        connections, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc, drug_to_packs
    )

    if not has_ndcs_anywhere(connections):
        return None, extracted, "no_ndcs"

    record = {
        'rxcui':      rxcui,
        'name':       name,
        'cid':        entity.get('cid') or mapping.get('cid'),
        'smiles':     entity.get('smiles'),
        'inchi_key':  entity.get('inchikey'),
        'iupac_name': entity.get('iupac_name'),
        'mol_weight': entity.get('mol_weight'),
        'pmid':       entity.get('pmid'),
        'connections': connections
    }

    return record, extracted, None


def main():
    parser = argparse.ArgumentParser(description='Geo Extract v23')
    parser.add_argument('--debug', action='store_true',
                        help='Process only first 5 IN entities')
    args = parser.parse_args()

    print("=" * 80)
    print("EXTRACT GEO V25")
    print("  [v23]   GPCK/BPCK packs with NDCs nested inside SCD/SBD objects")
    print("  [v24]   Correct Set ID Mapping and improve active NDC extraction")
    print("  [v25]   Add new NDC properties for dosage form and labeler")
    print("=" * 80)

    # ── Load all data ─────────────────────────────────────────────────────────
    pricing_by_ndc                       = load_pricing_data()
    rxcui_to_entity, entity_id_to_entity = load_rxnorm_entities()
    forward, reverse                     = load_rxnorm_relations()
    rxcui_to_ndcs                        = load_ndc_mappings()
    ndc_to_setid                         = load_ndc_to_setid()
    cid_mapping                          = load_cid_mapping()

    # ── Build pack index (one-time) ───────────────────────────────────────────
    print("\nBuilding pack index...")
    drug_to_packs = build_pack_index(rxcui_to_entity, entity_id_to_entity, forward, reverse)

    # ── Collect IN entities ───────────────────────────────────────────────────
    all_ingredients = [
        (e['name'], rxcui)
        for rxcui, e in rxcui_to_entity.items()
        if e['tty'] == 'IN'
    ]
    print(f"\nFound {len(all_ingredients):,} total IN entities")

    if args.debug:
        all_ingredients = all_ingredients[:5]
        print("  [DEBUG MODE] Processing 5 entities only")

    print(f"\nProcessing {len(all_ingredients):,} ingredients...")

    stats = {
        'total':          0,
        'passed':         0,
        'no_connections': 0,
        'no_ndcs':        0,
        'with_pins':      0,
        'with_packs':     0,
    }
    all_priced = set()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, 'w') as f:
        for idx, (name, rxcui) in enumerate(all_ingredients):
            if (idx + 1) % 100 == 0:
                print(f"  {idx + 1:,} / {len(all_ingredients):,} "
                      f"(passed: {stats['passed']:,}, "
                      f"with PINs: {stats['with_pins']:,}, "
                      f"with packs: {stats['with_packs']:,})")

            stats['total'] += 1

            result, extracted, fail_reason = process_ingredient(
                name, rxcui, cid_mapping, rxcui_to_entity, entity_id_to_entity,
                forward, reverse, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc,
                drug_to_packs
            )

            all_priced.update(extracted)

            if result is None:
                if fail_reason == "no_ndcs":
                    stats['no_ndcs'] += 1
                elif fail_reason == "no_connections":
                    stats['no_connections'] += 1
                continue

            if result['connections'].get('pin'):
                stats['with_pins'] += 1

            # Count records that have at least one pack somewhere
            conns = result['connections']
            has_packs = any(
                drug_obj.get('gpck') or drug_obj.get('bpck')
                for level in ['scd', 'sbd']
                for drug_obj in conns.get(level, [])
            ) or any(
                drug_obj.get('gpck') or drug_obj.get('bpck')
                for pin in conns.get('pin', [])
                for level in ['scd', 'sbd']
                for drug_obj in pin.get(level, [])
            ) or any(
                drug_obj.get('gpck') or drug_obj.get('bpck')
                for min_d in conns.get('min', [])
                for level in ['combo_scds', 'combo_sbds']
                for drug_obj in min_d.get(level, [])
            )
            if has_packs:
                stats['with_packs'] += 1

            stats['passed'] += 1
            f.write(json.dumps(result, separators=(',', ':')) + '\n')

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("EXTRACTION COMPLETE")
    print(f"{'=' * 80}")
    print(f"Output:          {OUTPUT_FILE}")
    print(f"Total:           {stats['passed']:,} / {stats['total']:,}")
    print(f"With PIN groups: {stats['with_pins']:,}")
    print(f"With packs:      {stats['with_packs']:,}")
    print(f"Priced NDCs:     {len(all_priced):,} / {len(pricing_by_ndc):,}")
    if pricing_by_ndc:
        print(f"Coverage:        {len(all_priced)/len(pricing_by_ndc)*100:.1f}%")
    print(f"\nFilters:")
    print(f"  No connections: {stats['no_connections']:,}")
    print(f"  No NDCs:        {stats['no_ndcs']:,}")
    print("=" * 80)


if __name__ == '__main__':
    main()
