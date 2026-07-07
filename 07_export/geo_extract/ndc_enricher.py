# ndc_enricher.py
"""
NDC + pricing enrichment.
Adds ndcs[], gpck[], bpck[] to every SCD and SBD in a connections dict.

v2: reads new dict-format ndc_to_setid (values are dicts, not plain strings).
    Attaches full metadata per NDC: labeler, marketing_status, approval_type,
    marketing_start, label_type, color, colortext, shape, size, imprint, score.
    Filters out NDCs whose label_type is in EXCLUDED_LABEL_TYPES.

NOTE: caller must pass the inner mapping dict, not the full JSON file:
    raw = json.loads(path.read_text())
    ndc_to_setid = raw["ndc_to_setid"]   ← pass this, not raw
"""

# NDC label types that are out of scope for this pipeline.
# Applied per-NDC at enrichment time — ndc_to_setid.json remains comprehensive.
EXCLUDED_LABEL_TYPES = {
    "PRESCRIPTION ANIMAL DRUG LABEL",
    "OTC ANIMAL DRUG LABEL",
    "ANIMAL COMPOUNDED DRUG",
}


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


def add_ndcs_with_pricing(connections, rxcui_to_ndcs, ndc_to_setid, pricing_by_ndc,
                          drug_to_packs=None):
    """
    Mutates connections in-place.
    Adds ndcs[], gpck[], bpck[] to every SCD/SBD at every nesting level.
    Returns (connections, set_of_priced_ndc11s).

    ndc_to_setid must be the inner mapping dict from ndc_to_setid.json:
        { "67108-3565-09": { "has_spl": true, "set_id": "...", ... }, ... }
    """
    extracted_priced = set()

    # ── inner helpers ────────────────────────────────────────────────────────

    def process_ndc_entry(entry):
        formats       = entry.get('ndc_formats', {})
        raw_ndc       = formats.get('ndc11_hyphens') or entry.get('ndc', '')
        ndc11         = formats.get('ndc11_no_hyphens') or normalize_ndc(raw_ndc)
        if not ndc11:
            return None, False

        ndc11_hyphens = format_ndc11_hyphens(ndc11)
        ndc10         = formats.get('ndc10_hyphens')

        # ── metadata lookup ──────────────────────────────────────────────────
        meta = ndc_to_setid.get(ndc11_hyphens) if ndc11_hyphens else None

        if meta and isinstance(meta, dict):
            # New dict format — apply label_type filter first
            label_type = meta.get('label_type')
            if label_type in EXCLUDED_LABEL_TYPES:
                return None, False          # drop this NDC entirely

        elif meta and isinstance(meta, str):
            # Old plain-string format (backward compat) — treat as set_id only
            meta = {'has_spl': True, 'set_id': meta}

        # ── build NDC object ─────────────────────────────────────────────────
        output = {'ndc': ndc11_hyphens}

        if ndc10:   output['ndc10']            = ndc10
        if ndc11:   output['ndc11_no_hyphens'] = ndc11

        if meta and meta.get('has_spl'):
            _set(output, 'spl_set_id',        meta.get('set_id'))
            _set(output, 'labeler',            meta.get('labeler'))
            _set(output, 'marketing_status',   meta.get('marketing_status'))
            _set(output, 'approval_type',      meta.get('approval_type'))
            _set(output, 'marketing_start',    meta.get('marketing_start'))
            _set(output, 'label_type',         meta.get('label_type'))
            _set(output, 'color',              meta.get('color'))
            _set(output, 'colortext',          meta.get('colortext'))
            _set(output, 'shape',              meta.get('shape'))
            _set(output, 'size',               meta.get('size'))
            _set(output, 'imprint',            meta.get('imprint'))
            _set(output, 'score',              meta.get('score'))
            _set(output, 'approval_number',    meta.get('approval_number'))

        # ── pricing ──────────────────────────────────────────────────────────
        pricing   = pricing_by_ndc.get(ndc11)
        has_price = False
        if pricing:
            if pricing.get('has_nadac'):
                output['nadac_unit_price'] = pricing['nadac_unit_price']
                has_price = True
            if pricing.get('has_costplus'):
                output['costplus_unit_price'] = pricing['costplus_unit_billing_price']
                has_price = True

        return output, has_price

    def enrich_ndc_list(rxcui):
        """Return (ndcs_list, priced_set) for a given rxcui."""
        ndcs   = []
        priced = set()
        for entry in rxcui_to_ndcs.get(rxcui, []):
            ndc_obj, has_price = process_ndc_entry(entry)
            if ndc_obj:
                ndcs.append(ndc_obj)
                if has_price:
                    priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
        return ndcs, priced

    def get_pack_lists(drug_rxcui):
        """
        Returns (gpck_list, bpck_list) for a drug rxcui.
        Each pack object: {rxcui, name, tty, ndcs[]}
        """
        if not drug_to_packs:
            return [], []

        gpck = []
        bpck = []

        for pack_entity in drug_to_packs.get(drug_rxcui, []):
            pack_rxcui = pack_entity['rxcui']
            pack_tty   = pack_entity.get('tty')

            pack_ndcs = []
            for entry in rxcui_to_ndcs.get(pack_rxcui, []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    pack_ndcs.append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))

            pack_obj = {
                'rxcui': pack_rxcui,
                'name':  pack_entity.get('name', ''),
                'tty':   pack_tty,
                'ndcs':  pack_ndcs,
            }

            if pack_tty == 'GPCK':
                gpck.append(pack_obj)
            elif pack_tty == 'BPCK':
                bpck.append(pack_obj)

        return gpck, bpck

    def enrich_drug(drug_obj):
        """Add ndcs, gpck, bpck to a single SCD or SBD dict in-place."""
        rxcui = drug_obj.get('rxcui')

        ndcs, priced = enrich_ndc_list(rxcui)
        drug_obj['ndcs'] = ndcs
        extracted_priced.update(priced)

        gpck, bpck = get_pack_lists(rxcui)
        drug_obj['gpck'] = gpck
        drug_obj['bpck'] = bpck

        # [v2] Flag drugs with no NDCs, GPCKs, or BPCKs as placeholders
        if not (drug_obj['ndcs'] or drug_obj['gpck'] or drug_obj['bpck']):
            drug_obj['placeholder'] = True

    # ── top-level SCDs ────────────────────────────────────────────────────────
    for scd in connections.get('scd', []):
        enrich_drug(scd)

    # ── top-level SBDs ────────────────────────────────────────────────────────
    for sbd in connections.get('sbd', []):
        enrich_drug(sbd)

    # ── PIN groups ────────────────────────────────────────────────────────────
    for pin in connections.get('pin', []):
        for scd in pin.get('scd', []):
            enrich_drug(scd)
        for sbd in pin.get('sbd', []):
            enrich_drug(sbd)

# ── MIN combo SCDs/SBDs ───────────────────────────────────────────────────
    for min_data in connections.get('min', []):
        _seen_pack_rxcuis = set()

        for combo_scd in min_data.get('combo_scds', []):
            enrich_drug(combo_scd)
            for key in ('gpck', 'bpck'):
                deduped = []
                for p in combo_scd.get(key, []):
                    if p['rxcui'] not in _seen_pack_rxcuis:
                        deduped.append(p)
                        _seen_pack_rxcuis.add(p['rxcui'])
                combo_scd[key] = deduped

        for combo_sbd in min_data.get('combo_sbds', []):
            enrich_drug(combo_sbd)
            for key in ('gpck', 'bpck'):
                deduped = []
                for p in combo_sbd.get(key, []):
                    if p['rxcui'] not in _seen_pack_rxcuis:
                        deduped.append(p)
                        _seen_pack_rxcuis.add(p['rxcui'])
                combo_sbd[key] = deduped

    return connections, extracted_priced

def _set(d, key, val):
    """Add key to dict only if val is truthy."""
    if val:
        d[key] = val
