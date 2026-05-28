#!/usr/bin/env python3
"""
debug_pin_nesting.py  —  v2, uses correct forward/reverse structure
"""
import loaders
from config import REL_HAS_PRECISE_INGREDIENT, REL_CONSTITUTES, REL_HAS_TRADENAME, REL_TRADENAME_OF

FLUTICASONE_IN  = '41126'
PIN_PROPIONATE  = '50121'
PIN_FUROATE     = '705022'

PROBE_SBDS = {
    '895996':  'Flovent HFA 44mcg  [SHOULD NEST]',
    '896019':  'Flovent DPI 50mcg  [SHOULD NEST]',
    '1547660': 'Arnuity 100mcg 30A [SHOULD NEST]',
    '1797933': 'Flonase nasal      [SHOULD NEST]',
    '1869712': 'Flonase Sensimist  [SHOULD NEST]',
    '2395836': 'Armonair 113mcg    [SHOULD NEST]',
}


def main():
    rxcui_to_entity, entity_id_to_entity = loaders.load_rxnorm_entities()
    forward, reverse = loaders.load_rxnorm_relations()

    def entity(rxcui):
        return rxcui_to_entity.get(str(rxcui))

    def eid(rxcui):
        e = entity(rxcui)
        return e['id'] if e else None

    def name(rxcui):
        e = entity(rxcui)
        return f"[{rxcui}] {e['name']} ({e['tty']})" if e else f"[{rxcui}] NOT FOUND"

    # ── 1. Check IN reverse: what TTYs point to the IN? ──────────────────────
    in_id = eid(FLUTICASONE_IN)
    print(f"\n{'='*70}")
    print(f"IN {name(FLUTICASONE_IN)}")
    print(f"  Reverse index entries: {len(reverse.get(in_id, []))}")
    tty_counts = {}
    for rt, sid in reverse.get(in_id, []):
        se = entity_id_to_entity.get(sid, {})
        key = f"{rt}/{se.get('tty','?')}"
        tty_counts[key] = tty_counts.get(key, 0) + 1
    for k, v in sorted(tty_counts.items()):
        print(f"    {k}: {v}")

    # ── 2. For each probe SBD, trace path to IN and PIN ───────────────────────
    print(f"\n{'='*70}")
    print("SBD TRACE — can we reach IN and PIN?")
    for sbd_rxcui, label in PROBE_SBDS.items():
        e = entity(sbd_rxcui)
        if not e:
            print(f"\n  {label}: NOT IN ENTITIES"); continue
        print(f"\n  {label}")
        # reverse of SBD → find parent SCDC/SBDC/SCD
        for rt, pid in reverse.get(e['id'], []):
            pe = entity_id_to_entity.get(pid, {})
            ptty = pe.get('tty', '?')
            if ptty not in ('SCDC', 'SBDC', 'SCD', 'SCDF', 'SCDG'):
                continue
            print(f"    SBD <--{rt}-- [{pe.get('rxcui')}] {pe.get('name')} ({ptty})")
            # what does the parent link to?
            for rt2, tid2 in forward.get(pid, []):
                te = entity_id_to_entity.get(tid2, {})
                ttty = te.get('tty', '?')
                marker = ''
                if te.get('rxcui') == FLUTICASONE_IN:
                    marker = '  ◀ IN'
                elif te.get('rxcui') in (PIN_PROPIONATE, PIN_FUROATE):
                    marker = '  ◀ PIN'
                if ttty in ('IN', 'PIN', 'SCD', 'SBD') or marker:
                    print(f"      --{rt2}--> [{te.get('rxcui')}] {te.get('name')} ({ttty}){marker}")

    # ── 3. PIN reverse: what SCDCs point to each PIN? ─────────────────────────
    print(f"\n{'='*70}")
    print("PIN REVERSE INDEX — SCDCs/BNs linking to each PIN")
    for pin_rxcui, pin_label in [(PIN_PROPIONATE, 'fluticasone propionate'),
                                  (PIN_FUROATE,   'fluticasone furoate')]:
        pid = eid(pin_rxcui)
        entries = reverse.get(pid, [])
        print(f"\n  PIN [{pin_rxcui}] {pin_label}: {len(entries)} reverse entries")
        tty_counts = {}
        for rt, sid in entries:
            se = entity_id_to_entity.get(sid, {})
            key = f"{rt}/{se.get('tty','?')}"
            tty_counts[key] = tty_counts.get(key, 0) + 1
        for k, v in sorted(tty_counts.items()):
            print(f"    {k}: {v}")

    # ── 4. BN nesting check ───────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("BN NESTING CHECK — BNs in reverse[IN], do they also appear in reverse[PIN]?")
    pin_ids = {eid(PIN_PROPIONATE), eid(PIN_FUROATE)}
    bns_from_in = []
    for rt, sid in reverse.get(in_id, []):
        se = entity_id_to_entity.get(sid, {})
        if se.get('tty') == 'BN':
            bns_from_in.append((rt, se))
    print(f"  BNs in reverse[IN]: {len(bns_from_in)}")
    for rt, bn in bns_from_in:
        bn_id = bn['id']
        # check if this BN appears in reverse of any PIN
        pin_hits = []
        for pin_rxcui in (PIN_PROPIONATE, PIN_FUROATE):
            pid = eid(pin_rxcui)
            for rt2, sid2 in reverse.get(pid, []):
                if sid2 == bn_id:
                    pin_hits.append(f"PIN[{pin_rxcui}] via {rt2}")
        status = ', '.join(pin_hits) if pin_hits else '*** NOT IN ANY PIN REVERSE ***'
        print(f"    BN [{bn['rxcui']}] {bn['name']}  via {rt}  →  {status}")


if __name__ == '__main__':
    main()
