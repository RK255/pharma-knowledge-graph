# pack_resolver.py
"""
Builds a lookup index of drug RxCUI → connected pack entities (GPCK / BPCK).

Uses TTY-based scanning across all forward and reverse relations so we never
need to hardcode a specific relation UUID. If a GPCK/BPCK entity touches an
SCD/SBD via any relation in either direction, we capture it.
"""
from collections import defaultdict


def build_pack_index(rxcui_to_entity, entity_id_to_entity, forward, reverse):
    """
    Scans all GPCK/BPCK entities, finds connected SCD/SBD via any relation.

    Returns:
        drug_to_packs: {drug_rxcui: [pack_entity_dict, ...]}
            Each list may contain a mix of GPCK and BPCK entities.
            Callers filter by entity['tty'] to get gpck vs bpck separately.
    """
    # drug_rxcui -> {pack_rxcui: pack_entity}  (dict keyed by rxcui deduplicates)
    drug_to_pack_map = defaultdict(dict)

    pack_count = 0
    for rxcui, entity in rxcui_to_entity.items():
        tty = entity.get('tty')
        if tty not in ('GPCK', 'BPCK'):
            continue

        pack_count += 1
        eid = entity['id']

        # forward: pack ──rel──→ drug component
        for _rel, target_id in forward.get(eid, []):
            target = entity_id_to_entity.get(target_id)
            if not target:
                continue
            if target.get('tty') in ('SCD', 'SBD'):
                drug_rxcui = target.get('rxcui')
                if drug_rxcui:
                    drug_to_pack_map[drug_rxcui][rxcui] = entity

        # reverse: drug component ──rel──→ pack
        for _rel, source_id in reverse.get(eid, []):
            source = entity_id_to_entity.get(source_id)
            if not source:
                continue
            if source.get('tty') in ('SCD', 'SBD'):
                drug_rxcui = source.get('rxcui')
                if drug_rxcui:
                    drug_to_pack_map[drug_rxcui][rxcui] = entity

    drug_to_packs = {k: list(v.values()) for k, v in drug_to_pack_map.items()}

    gpck_count = sum(
        1 for packs in drug_to_packs.values()
        for p in packs if p.get('tty') == 'GPCK'
    )
    bpck_count = sum(
        1 for packs in drug_to_packs.values()
        for p in packs if p.get('tty') == 'BPCK'
    )
    print(f"  Pack index: {pack_count} pack entities → "
          f"{len(drug_to_packs)} drug RxCUIs "
          f"(GPCK refs: {gpck_count}, BPCK refs: {bpck_count})")

    return drug_to_packs
