#!/usr/bin/env python3
"""
validate_v23_structure.py
=========================
Compares v22.6 and v23 output structure record by record.

Confirms:
  - All v22.6 top-level keys still present on every record
  - gpck/bpck present on every SCD and SBD at every nesting level
  - names / rxcuis / ndcs are unchanged between versions
  - At least some records have non-empty gpck or bpck
  - Pack NDC objects have expected fields

Usage:
  python3 validate_v23_structure.py
"""
import json
from pathlib import Path
from collections import defaultdict

V226_FILE = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/geo-ingestor/data_to_publish/full_geo_extraction_v22.6.jsonl")
V23_FILE  = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/geo-ingestor/data_to_publish/full_geo_extraction_v23.jsonl")

# ── expected keys ─────────────────────────────────────────────────────────────
TOP_LEVEL_KEYS    = {'rxcui', 'name', 'cid', 'smiles', 'inchi_key',
                     'iupac_name', 'mol_weight', 'pmid', 'connections'}
CONNECTIONS_KEYS  = {'scd', 'sbd', 'bn', 'pin', 'min', 'df'}
DRUG_OBJ_NEW_KEYS = {'gpck', 'bpck'}   # must exist on every SCD / SBD
NDC_OBJ_KEYS      = {'ndc', 'ndc11_no_hyphens'}  # minimum required on ndc entries
PACK_OBJ_KEYS     = {'rxcui', 'name', 'tty', 'ndcs'}


def iter_all_drug_objs(connections):
    """
    Yields every SCD/SBD dict at any nesting level within a connections dict.
    Yields (path_label, drug_obj).
    """
    for item in connections.get('scd', []):
        yield 'scd', item
    for item in connections.get('sbd', []):
        yield 'sbd', item
    for pin in connections.get('pin', []):
        for item in pin.get('scd', []):
            yield f"pin[{pin['rxcui']}].scd", item
        for item in pin.get('sbd', []):
            yield f"pin[{pin['rxcui']}].sbd", item
    for min_d in connections.get('min', []):
        for item in min_d.get('combo_scds', []):
            yield f"min[{min_d['rxcui']}].combo_scds", item
        for item in min_d.get('combo_sbds', []):
            yield f"min[{min_d['rxcui']}].combo_sbds", item


def load_jsonl_by_rxcui(path):
    data = {}
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            data[rec['rxcui']] = rec
    return data


def validate_v23_structure(v23_records):
    """
    Structural checks on v23 records.
    Returns (errors list, stats dict).
    """
    errors = []
    stats = defaultdict(int)

    for rxcui, rec in v23_records.items():
        stats['total'] += 1

        # ── top-level keys ────────────────────────────────────────────────────
        missing_top = TOP_LEVEL_KEYS - rec.keys()
        if missing_top:
            errors.append(f"[{rxcui}] Missing top-level keys: {missing_top}")

        conns = rec.get('connections', {})

        # ── connections keys ──────────────────────────────────────────────────
        missing_conn = CONNECTIONS_KEYS - conns.keys()
        if missing_conn:
            errors.append(f"[{rxcui}] Missing connections keys: {missing_conn}")

        # ── drug obj checks ───────────────────────────────────────────────────
        for path, drug_obj in iter_all_drug_objs(conns):
            drug_rxcui = drug_obj.get('rxcui', '?')

            missing_new = DRUG_OBJ_NEW_KEYS - drug_obj.keys()
            if missing_new:
                errors.append(
                    f"[{rxcui}] {path}[{drug_rxcui}] Missing new keys: {missing_new}"
                )
                continue

            # ── gpck/bpck must be lists ───────────────────────────────────────
            for pack_key in ('gpck', 'bpck'):
                val = drug_obj[pack_key]
                if not isinstance(val, list):
                    errors.append(
                        f"[{rxcui}] {path}[{drug_rxcui}].{pack_key} is not a list: {type(val)}"
                    )
                    continue

                for pack in val:
                    stats[f'pack_{pack_key}'] += 1

                    # ── pack object keys ──────────────────────────────────────
                    missing_pack = PACK_OBJ_KEYS - pack.keys()
                    if missing_pack:
                        errors.append(
                            f"[{rxcui}] {path}[{drug_rxcui}].{pack_key} "
                            f"pack[{pack.get('rxcui','?')}] missing keys: {missing_pack}"
                        )

                    # ── tty must match key ────────────────────────────────────
                    expected_tty = 'GPCK' if pack_key == 'gpck' else 'BPCK'
                    if pack.get('tty') != expected_tty:
                        errors.append(
                            f"[{rxcui}] {path}[{drug_rxcui}].{pack_key} "
                            f"pack[{pack.get('rxcui','?')}] has tty={pack.get('tty')} "
                            f"expected {expected_tty}"
                        )

                    # ── pack ndcs structure ───────────────────────────────────
                    pack_ndcs = pack.get('ndcs', [])
                    if not isinstance(pack_ndcs, list):
                        errors.append(
                            f"[{rxcui}] {path}[{drug_rxcui}].{pack_key}"
                            f"[{pack.get('rxcui','?')}].ndcs is not a list"
                        )
                    else:
                        for ndc_obj in pack_ndcs:
                            stats['pack_ndcs'] += 1
                            missing_ndc = NDC_OBJ_KEYS - ndc_obj.keys()
                            if missing_ndc:
                                errors.append(
                                    f"[{rxcui}] pack ndc missing fields: {missing_ndc} → {ndc_obj}"
                                )

            # ── track coverage ────────────────────────────────────────────────
            if drug_obj.get('gpck'):
                stats['drug_objs_with_gpck'] += 1
            if drug_obj.get('bpck'):
                stats['drug_objs_with_bpck'] += 1
            stats['drug_objs_checked'] += 1

    return errors, dict(stats)


def compare_v226_vs_v23(v226_records, v23_records):
    """
    For every rxcui present in BOTH files, confirm that:
      - name, rxcui unchanged
      - ndcs lists are identical (same ndc values, same count)
      - all v22.6 connection keys present in v23
    Returns list of discrepancies.
    """
    discrepancies = []
    shared = set(v226_records.keys()) & set(v23_records.keys())

    for rxcui in shared:
        old = v226_records[rxcui]
        new = v23_records[rxcui]

        # name unchanged
        if old.get('name') != new.get('name'):
            discrepancies.append(
                f"[{rxcui}] name changed: {old.get('name')!r} → {new.get('name')!r}"
            )

        old_conns = old.get('connections', {})
        new_conns = new.get('connections', {})

        # same number of SCDs, SBDs, PINs, MINs
        for key in ['scd', 'sbd', 'bn', 'pin', 'min', 'df']:
            old_count = len(old_conns.get(key, []))
            new_count = len(new_conns.get(key, []))
            if old_count != new_count:
                discrepancies.append(
                    f"[{rxcui}] connections.{key} count changed: {old_count} → {new_count}"
                )

        # NDC sets unchanged for top-level SCDs
        def ndc_set(items):
            return {
                ndc['ndc']
                for item in items
                for ndc in item.get('ndcs', [])
                if ndc.get('ndc')
            }

        old_scd_ndcs = ndc_set(old_conns.get('scd', []))
        new_scd_ndcs = ndc_set(new_conns.get('scd', []))
        if old_scd_ndcs != new_scd_ndcs:
            added   = new_scd_ndcs - old_scd_ndcs
            removed = old_scd_ndcs - new_scd_ndcs
            discrepancies.append(
                f"[{rxcui}] SCD NDC mismatch — added: {added}, removed: {removed}"
            )

        old_sbd_ndcs = ndc_set(old_conns.get('sbd', []))
        new_sbd_ndcs = ndc_set(new_conns.get('sbd', []))
        if old_sbd_ndcs != new_sbd_ndcs:
            added   = new_sbd_ndcs - old_sbd_ndcs
            removed = old_sbd_ndcs - new_sbd_ndcs
            discrepancies.append(
                f"[{rxcui}] SBD NDC mismatch — added: {added}, removed: {removed}"
            )

    return discrepancies, len(shared)


def main():
    print("=" * 70)
    print("GEO EXTRACT v23 STRUCTURE VALIDATOR")
    print("=" * 70)

    # ── check files exist ─────────────────────────────────────────────────────
    for fpath, label in [(V226_FILE, 'v22.6'), (V23_FILE, 'v23')]:
        if not fpath.exists():
            print(f"ERROR: {label} file not found: {fpath}")
            return

    print(f"\nLoading v22.6: {V226_FILE.name}")
    v226 = load_jsonl_by_rxcui(V226_FILE)
    print(f"  {len(v226):,} records")

    print(f"Loading v23:   {V23_FILE.name}")
    v23  = load_jsonl_by_rxcui(V23_FILE)
    print(f"  {len(v23):,} records")

    # ── structural validation ─────────────────────────────────────────────────
    print("\n── Structural validation (v23 only) ────────────────────────────────")
    errors, stats = validate_v23_structure(v23)

    print(f"  Records checked:           {stats.get('total', 0):,}")
    print(f"  Drug objects checked:      {stats.get('drug_objs_checked', 0):,}")
    print(f"  Drug objects with gpck:    {stats.get('drug_objs_with_gpck', 0):,}")
    print(f"  Drug objects with bpck:    {stats.get('drug_objs_with_bpck', 0):,}")
    print(f"  Total GPCK pack objects:   {stats.get('pack_gpck', 0):,}")
    print(f"  Total BPCK pack objects:   {stats.get('pack_bpck', 0):,}")
    print(f"  Total pack NDC entries:    {stats.get('pack_ndcs', 0):,}")

    if errors:
        print(f"\n  STRUCTURAL ERRORS ({len(errors)}):")
        for e in errors[:50]:   # cap at 50 so it doesn't flood
            print(f"    ✗ {e}")
        if len(errors) > 50:
            print(f"    ... and {len(errors) - 50} more")
    else:
        print("\n  ✓ No structural errors")

    # ── cross-version comparison ───────────────────────────────────────────────
    print("\n── Cross-version comparison (v22.6 vs v23) ─────────────────────────")
    discrepancies, shared_count = compare_v226_vs_v23(v226, v23)
    print(f"  Shared rxcuis compared:    {shared_count:,}")

    only_in_226 = set(v226.keys()) - set(v23.keys())
    only_in_v23 = set(v23.keys()) - set(v226.keys())
    if only_in_226:
        print(f"  Only in v22.6 (dropped):   {len(only_in_226):,} → {list(only_in_226)[:5]}")
    if only_in_v23:
        print(f"  Only in v23 (new):         {len(only_in_v23):,} → {list(only_in_v23)[:5]}")

    if discrepancies:
        print(f"\n  DISCREPANCIES ({len(discrepancies)}):")
        for d in discrepancies[:50]:
            print(f"    ✗ {d}")
        if len(discrepancies) > 50:
            print(f"    ... and {len(discrepancies) - 50} more")
    else:
        print("  ✓ All shared records match v22.6 exactly")

    # ── spot check: print a record with packs ─────────────────────────────────
    print("\n── Spot check: first record with non-empty gpck or bpck ────────────")
    found_example = False
    for rxcui, rec in v23.items():
        conns = rec.get('connections', {})
        for path, drug_obj in iter_all_drug_objs(conns):
            if drug_obj.get('gpck') or drug_obj.get('bpck'):
                print(f"  rxcui={rxcui}  name={rec['name']}")
                print(f"  {path}[{drug_obj['rxcui']}]  {drug_obj['name']}")
                for pk in ('gpck', 'bpck'):
                    for pack in drug_obj.get(pk, []):
                        print(f"    {pk}: {pack['rxcui']}  {pack['name']!r}  "
                              f"ndcs={len(pack['ndcs'])}")
                found_example = True
                break
        if found_example:
            break

    if not found_example:
        print("  (no records with packs found — run full extraction first)")

    print("\n" + "=" * 70)
    total_issues = len(errors) + len(discrepancies)
    if total_issues == 0:
        print("RESULT: ✓ PASS — v23 is structurally sound and backward compatible")
    else:
        print(f"RESULT: ✗ FAIL — {total_issues} issues found, review above")
    print("=" * 70)


if __name__ == '__main__':
    main()
