# filters.py


def has_drug_connections(connections):
    return (
        len(connections.get('scd', [])) > 0 or
        len(connections.get('sbd', [])) > 0 or
        len(connections.get('min', [])) > 0 or
        len(connections.get('pin', [])) > 0
    )


def _drug_obj_has_ndcs(drug_obj):
    """True if a SCD/SBD has direct NDCs OR any of its pack children do."""
    if drug_obj.get('ndcs'):
        return True
    for pack in drug_obj.get('gpck', []):
        if pack.get('ndcs'):
            return True
    for pack in drug_obj.get('bpck', []):
        if pack.get('ndcs'):
            return True
    return False


def has_ndcs_anywhere(connections):
    for conn_type in ['scd', 'sbd']:
        for item in connections.get(conn_type, []):
            if _drug_obj_has_ndcs(item):
                return True

    for pin in connections.get('pin', []):
        for conn_type in ['scd', 'sbd']:
            for item in pin.get(conn_type, []):
                if _drug_obj_has_ndcs(item):
                    return True

    for min_data in connections.get('min', []):
        for combo_type in ['combo_scds', 'combo_sbds']:
            for combo in min_data.get(combo_type, []):
                if _drug_obj_has_ndcs(combo):
                    return True

    return False
