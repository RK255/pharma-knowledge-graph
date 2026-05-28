#!/usr/bin/env python3
"""
Extract GEO with Pricing v22.5 - SBD Name Reformatting
======================================================
- SCDs, SBDs, BNs, DFs, NDCs nest under PINs
- SBDs nested under PIN get brand_name from their BN
- PIN combos (multiple ingredients) get MIN-style combo treatment
- SBD names reformatted: 'Brand [ingredient] dose form'
- NDA/ANDA numbers stripped from SBD names
- Duration modifiers (21 DAY, 28 DAY) moved to end
- Ingredient prefixes (Preservative-Free) moved after dose form
"""
import json
import argparse
import re
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
OUTPUT_FILE = OUTPUT_DIR / "full_geo_extraction_v22.5.jsonl"

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

BLOCKED_TTYS = {'TMSY', 'PSN', 'SY'}
INJECTABLE_DOSE_FORMS = ['Auto-Injector', 'Prefilled Syringe']


def apply_injectable_dose_calculation(name):
    """
    For Prefilled Syringe / Auto-Injector forms only, transform:
        "<prefix> CONC MG/ML <FORM> <VOL> ML <suffix>"
    into:
        "<prefix> TOTAL MG (CONC MG/ML) <FORM> <VOL> ML <suffix>"
    where TOTAL = CONC × VOL.

    Intentionally narrow: skips combos and powder-for-reconstitution forms.
    """
    # Skip if already transformed
    if re.search(r'\d+(?:\.\d+)?\s*MG\s*\(', name, re.IGNORECASE):
        return name

    forms_pattern = '|'.join(
        f.replace('-', r'[-\s]').replace(' ', r'[-\s]') for f in INJECTABLE_DOSE_FORMS
    )
    pattern = (
        r'^(.*?\s)(\d+(?:\.\d+)?)\s*MG/ML\s+(' + forms_pattern + r')\s+'
        r'(\d+(?:\.\d+)?)\s*ML\b(.*)$'
    )
    m = re.match(pattern, name, re.IGNORECASE)
    if not m:
        return name

    before = m.group(1)
    # Skip combos (multiple MG/ML in prefix, or " / " separator)
    if re.search(r'MG/ML', before, re.IGNORECASE) or ' / ' in before:
        return name

    conc_str = m.group(2)
    form = m.group(3)
    vol_str = m.group(4)
    after = m.group(5)

    total = round(float(conc_str) * float(vol_str), 6)
    # Strip trailing zeros: 80.0 -> "80", 0.0012 -> "0.0012"
    total_str = f"{total:.6f}".rstrip('0').rstrip('.')

    return f"{before}{total_str} MG ({conc_str} MG/ML) {form} {vol_str} ML{after}"

# =============================================================================
# SBD NAME REFORMATTING
# =============================================================================

DOSE_UNITS = [
    'MG/MG', 'MCG/MCG', 'UNT/UNT', 'U/U',
    'MG', 'MCG', 'ML', 'UNT', 'Unit', 'Units', 'IU', 'U', 'MEQ',
    'MG/ML', 'MCG/ML', 'MG/ACTUAT', 'MCG/ACTUAT',
    '%', 'MG/G', 'MCG/G',
    'CELLS/ML', 'CELLS', 'ACTUAT', 'BAU', 'SQCM', 'Amb a 1-U',
    'SQ-HDM', 'CM', 'IR', 'VIRAL-PARTICLES/ML',
    'VECTOR-GENOMES/ML', 'EIN/ML', 'VIRAL-PARTICLES/ML', 'UNT/ML',
]

RELEASE_MODIFIERS = [
    '9 HR', '12 HR', '24 HR', '72 HR', '84 HR', '168 HR',
    '8 HR',
    'SR', 'ER', 'XR', 'CR', 'LA', 'SA', 'XL',
    '3-Bead',
]

# Duration/quantity modifiers at START of name (move to end)
DURATION_MODIFIERS = [
    '21 DAY', '28 DAY', '30 DAY', '60 DAY', '90 DAY',
    '1 DAY', '2 DAY', '3 DAY', '7 DAY', '14 DAY',
]

# Prefixes in ingredient name (strip and append to dose form)
INGREDIENT_PREFIXES = [
    'Preservative-Free',
    'Once-Daily',
    'Twice-Daily',
    'Three-Times-Daily',
    'Immediate-Release',
    'Sustained-Release',
]


def extract_brand(name, fallback_brand=None):
    """Extract brand from [Brand] at end of name, with validation and fallback."""
    # Strip NDA/ANDA prefix from the name START
    name = re.sub(r'^(NDA\d+|ANDA\d+)\s+', '', name, flags=re.IGNORECASE).strip()
    
    last_open = name.rfind('[')
    if last_open == -1:
        return fallback_brand, None, name if fallback_brand else (None, None, name)
    
    close = name.find(']', last_open)
    if close == -1:
        return fallback_brand, None, name if fallback_brand else (None, None, name)
    
    brand_text = name[last_open + 1:close].strip()
    before_bracket = name[:last_open].strip()
    after_bracket = name[close + 1:].strip()
    
    # Check if this is brand-first format (no dose before bracket)
    dose_before_bracket = find_first_dose_position(before_bracket) != -1
    
    if not dose_before_bracket:
        # Brand-first format: before_bracket is brand, brand_text is ingredient
        brand, extra_dose = clean_brand_content(brand_text)
        if not brand:
            return fallback_brand, None, before_bracket if fallback_brand else (None, None, name)
        clean_name = brand + ' ' + after_bracket if after_bracket else brand
        return brand, extra_dose, clean_name
    
    # Traditional format: brand is in brackets
    clean_name = before_bracket
    brand, extra_dose = clean_brand_content(brand_text)
    
    if not brand:
        return fallback_brand, None, clean_name if fallback_brand else (None, None, name)
    
    return brand, extra_dose, clean_name


def clean_brand_content(brand_text):
    """
    Clean brand content from brackets, removing NDA/ANDA numbers
    and extracting any dose info that should move to end.
    
    Returns: (cleaned_brand, extra_dose_info)
    """
    if not brand_text:
        return None, None
    
    text = brand_text.strip()
    
    # Check if this is JUST an NDA/ANDA number (invalid brand)
    if re.match(r'^(NDA|ANDA)\d+$', text, re.IGNORECASE):
        return None, None
    
    # Remove NDA/ANDA prefix if present
    text = re.sub(r'^(NDA|ANDA)\d+\s*', '', text, flags=re.IGNORECASE).strip()
    
    if not text:
        return None, None
    
    # Try to extract dose info pattern from the text (e.g., "200 ACTUAT albuterol")
    dose_pattern = r'^(\d+(?:\.\d+)?)\s*(ACTUAT|CELLS(?:/ML)?)\s+'
    match = re.match(dose_pattern, text, re.IGNORECASE)
    
    extra_dose = None
    if match:
        extra_dose = f"{match.group(1)} {match.group(2).upper()}"
        text = text[match.end():].strip()
    
    if not text or re.match(r'^\d', text):
        return None, None
    
    return text, extra_dose


def extract_duration_modifier(name):
    """Extract duration modifier from start of name (e.g., '21 DAY', '28 DAY')."""
    for mod in DURATION_MODIFIERS:
        pattern = r'^' + r'\s+'.join(mod.split()) + r'\s+'
        if re.match(pattern, name, re.IGNORECASE):
            clean = re.sub(pattern, '', name, count=1, flags=re.IGNORECASE).strip()
            return mod, clean
    return None, name


def extract_ingredient_prefix(ingredient):
    """Extract ingredient prefix like 'Preservative-Free', 'Once-Daily'."""
    for prefix in INGREDIENT_PREFIXES:
        # Match with flexible hyphen/spacing
        pattern = r'^' + prefix.replace('-', r'\s*-\s*') + r'\s+'
        if re.match(pattern, ingredient, re.IGNORECASE):
            clean = re.sub(pattern, '', ingredient, count=1, flags=re.IGNORECASE).strip()
            return prefix, clean
    return None, ingredient


def extract_container_size(name):
    """Extract container size from start (e.g., '0.1 ML', '250 ML', '750 MG')."""
    # Match container with another dose pattern later in the name
    match = re.match(r'^(\d+(?:\.\d+)?)\s*(ML|L|MG)\s+(.+)$', name, re.IGNORECASE)
    if match:
        rest = match.group(3)
        # Only extract if there's another dose pattern in the rest
        if find_first_dose_position(rest) != -1:
            container = f"{match.group(1)} {match.group(2).upper()}"
            return container, rest.strip()
    return None, name

def extract_release_modifier(ingredient):
    """Extract release modifier from start of ingredient (e.g., '12 HR', '24 HR')."""
    for mod in RELEASE_MODIFIERS:
        pattern = '^' + r'\s+'.join(mod.split()) + r'\s+'
        if re.match(pattern, ingredient, re.IGNORECASE):
            clean = re.sub(pattern, '', ingredient, count=1, flags=re.IGNORECASE).strip()
            return mod, clean
    return None, ingredient


def find_first_dose_position(name):
    """Find position of first dose pattern (NUMBER + UNIT)."""
    earliest_pos = -1
    
    for unit in sorted(DOSE_UNITS, key=len, reverse=True):
        escaped = unit.replace('/', r'\/')
        pattern = rf'(\d+(?:\.\d+)?)\s*{escaped}(?:\s|/|$)'
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            if earliest_pos == -1 or match.start() < earliest_pos:
                earliest_pos = match.start()
    
    return earliest_pos


def parse_combo_product(clean_name):
    """Parse combo product with ' / ' separator."""
    parts = clean_name.split(' / ')
    if len(parts) < 2:
        return None
    
    ingredients = []
    doses = []
    dose_form = ''
    
    for i, part in enumerate(parts):
        part = part.strip()
        
        dose_match = None
        dose_unit_matched = None
        
        for unit in sorted(DOSE_UNITS, key=len, reverse=True):
            escaped = unit.replace('/', r'\/')
            pattern = rf'(\d+(?:\.\d+)?)\s*({escaped})(?:\s|$)'
            m = re.search(pattern, part, re.IGNORECASE)
            if m:
                dose_match = m
                dose_unit_matched = unit
                break
        
        if not dose_match:
            return None
        
        ingredient = part[:dose_match.start()].strip()
        base_unit = dose_unit_matched.upper()
        if '/' in base_unit:
            parts_list = base_unit.split('/')
            if len(parts_list) == 2 and parts_list[0] == parts_list[1]:
                base_unit = parts_list[0]
        
        dose = f"{dose_match.group(1)} {base_unit}"
        ingredients.append(ingredient)
        doses.append(dose)
        
        if i == len(parts) - 1:
            dose_form = part[dose_match.end():].strip()
    
    return {
        'ingredients': ' / '.join(ingredients),
        'doses': ' / '.join(doses),
        'dose_form': dose_form
    }


def reformat_sbd_name(name, brand_name_from_bn=None):
    """
    Reformat SBD name to put brand first.
    
    Examples:
      'mesna 100 MG/ML Injectable Solution [Mesnex]'
      -> 'Mesnex [mesna] 100 MG/ML Injectable Solution'
      
      'NDA020983 200 ACTUAT albuterol 0.09 MG/ACTUAT Metered Dose Inhaler [Ventolin]'
      -> 'Ventolin [albuterol] 0.09 MG/ACTUAT Metered Dose Inhaler 200 ACTUAT'
      
      '250 ML sipuleucel-T 200000 CELLS/ML Injection [Provenge]'
      -> 'Provenge [sipuleucel-T] 200000 CELLS/ML Injection 250 ML'
      
      '21 DAY ethinyl estradiol 0.000625 MG/HR / etonogestrel 0.005 MG/HR Vaginal System [NuvaRing]'
      -> 'NuvaRing [ethinyl estradiol / etonogestrel] 0.000625 MG/HR / 0.005 MG/HR Vaginal System 21 DAY'
      
      'Preservative-Free timolol 5 MG/ML Ophthalmic Solution [Timoptic]'
      -> 'Timoptic [timolol] 5 MG/ML Ophthalmic Solution Preservative-Free'
    """
    # Step 1: Extract duration modifier from START (21 DAY, 28 DAY, etc.)
    duration_mod, name = extract_duration_modifier(name)
    
    # Step 2: Extract brand (with fallback from BN relationship)
    fallback = brand_name_from_bn.get('name') if brand_name_from_bn else None
    brand, extra_dose, name_after_brand = extract_brand(name, fallback_brand=fallback)
    
    if not brand:
        return name
    
    # Step 3: Extract container size if present at START
    container, name_after_container = extract_container_size(name_after_brand)
    
    # Step 4: Check if combo product
    if ' / ' in name_after_container:
        parsed = parse_combo_product(name_after_container)
        if parsed:
            # Extract ingredient prefixes from combo ingredients
            clean_ingredients = []
            ingredient_prefixes = []
            
            for ing in parsed['ingredients'].split(' / '):
                prefix, clean_ing = extract_ingredient_prefix(ing)
                clean_ingredients.append(clean_ing)
                if prefix:
                    ingredient_prefixes.append(prefix)
            
            dose_form = parsed['dose_form']
            if ingredient_prefixes:
                dose_form = dose_form + ' ' + ' '.join(ingredient_prefixes)
            
            result = f"{brand} [{' / '.join(clean_ingredients)}] {parsed['doses']} {dose_form}"
            if container:
                result += f" {container}"
            if duration_mod:
                result += f" {duration_mod}"
            if extra_dose:
                result += f" {extra_dose}"
            return apply_injectable_dose_calculation(result) 
    # Step 5: Find first dose position
    dose_pos = find_first_dose_position(name_after_container)
    if dose_pos == -1:
        return name
    
    ingredient_part = name_after_container[:dose_pos].strip()
    
    # Step 6: Extract release modifiers from ingredient (loop to handle chains
    # like "3-Bead 24 HR ingredient")
    release_mods = []
    while True:
        mod, ingredient_part = extract_release_modifier(ingredient_part)
        if not mod:
            break
        release_mods.append(mod)

    # Step 7: Extract ingredient prefix (Preservative-Free, Once-Daily, etc.)
    ingredient_prefix, ingredient_part = extract_ingredient_prefix(ingredient_part)
    
    after_ingredient = name_after_container[dose_pos:]
    
    dose_match = re.match(r'^(\d+(?:\.\d+)?)\s*([A-Za-z/]+)\s*(.*)$', after_ingredient)
    if not dose_match:
        return name
    
    dose = f"{dose_match.group(1)} {dose_match.group(2).upper()}"
    dose_form = dose_match.group(3).strip()
    
    # Append ingredient prefix to dose form
    if ingredient_prefix:
        dose_form = dose_form + ' ' + ingredient_prefix
    
    # Build result
    result = f"{brand} [{ingredient_part}] {dose} {dose_form}"
    if release_mods:
        result += ' ' + ' '.join(release_mods)
    if container:
        result += f" {container}"
    if duration_mod:
        result += f" {duration_mod}"
    if extra_dose:
        result += f" {extra_dose}"

    return apply_injectable_dose_calculation(result)

def reformat_scd_name(name):
    """
    Reformat SCD name to move leading modifiers/container sizes to the end,
    and apply injectable dose calculation for PFS/Auto-Injector forms.

    Examples:
      '0.8 ML adalimumab-aaty 100 MG/ML Auto-Injector'
      -> 'adalimumab-aaty 80 MG (100 MG/ML) Auto-Injector 0.8 ML'

      '3-Bead 24 HR amphetamine aspartate 3.125 MG Extended Release Oral Capsule'
      -> 'amphetamine aspartate 3.125 MG Extended Release Oral Capsule 3-Bead 24 HR'

      '21 DAY ethinyl estradiol 0.000625 MG/HR / etonogestrel 0.005 MG/HR Vaginal System'
      -> 'ethinyl estradiol / etonogestrel 0.000625 MG/HR / 0.005 MG/HR Vaginal System 21 DAY'
    """
    if not name:
        return name

    working = name
    trailing = []

    # Extract leading duration modifiers (loop)
    while True:
        mod, working = extract_duration_modifier(working)
        if not mod:
            break
        trailing.append(mod)

    # Extract leading release modifiers (loop)
    while True:
        mod, working = extract_release_modifier(working)
        if not mod:
            break
        trailing.append(mod)

    # Extract leading container size (loop)
    while True:
        container, working = extract_container_size(working)
        if not container:
            break
        trailing.append(container)

    # One more pass of release modifiers (handles "0.1 ML 12 HR ..." pattern)
    while True:
        mod, working = extract_release_modifier(working)
        if not mod:
            break
        trailing.append(mod)

    # Find dose position; if none, return as-is with trailing parts
    dose_pos = find_first_dose_position(working)
    if dose_pos == -1:
        result = working
        if trailing:
            result = working + ' ' + ' '.join(trailing)
        return apply_injectable_dose_calculation(result)

    # Combo: leave the ingredients/doses/form as-is, just append trailing
    if ' / ' in working:
        parsed = parse_combo_product(working)
        if parsed:
            result = f"{parsed['ingredients']} {parsed['doses']} {parsed['dose_form']}"
            if trailing:
                result += ' ' + ' '.join(trailing)
            return apply_injectable_dose_calculation(result)

    # Single-ingredient: keep structure, just append trailing parts
    result = working
    if trailing:
        result += ' ' + ' '.join(trailing)
    return apply_injectable_dose_calculation(result)

# =============================================================================
# DATA LOADING
# =============================================================================

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
    pricing_by_ndc = {e.get('ndc11'): e for e in data.get('pricing', []) if e.get('ndc11')}
    print(f"  {len(pricing_by_ndc):,} priced NDCs loaded")
    return pricing_by_ndc


def load_rxnorm_entities():
    print("Loading RxNorm entities...")
    rxcui_to_entity = {}
    entity_id_to_entity = {}
    
    with open(RXNORM_ENTITIES_FILE) as f:
        for line in f:
            e = json.loads(line)
            props = {p['property']: p['value'] for p in e.get('values', [])}
            
            entity_data = {
                'id': e.get('id'),
                'rxcui': props.get(PROP_RXCUI),
                'name': props.get(PROP_NAME),
                'tty': props.get(PROP_TTY),
                'cid': props.get(PROP_CID),
                'smiles': props.get(PROP_SMILES),
                'inchikey': props.get(PROP_INCHIKEY),
                'iupac_name': props.get(PROP_IUPAC),
                'mol_weight': props.get(PROP_MOLWEIGHT),
                'pmid': props.get(PROP_PMID),
            }
            
            if entity_data['rxcui']:
                rxcui_to_entity[entity_data['rxcui']] = entity_data
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


# =============================================================================
# ENTITY RELATIONSHIP HELPERS
# =============================================================================

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


# =============================================================================
# PIN GROUP BUILDING
# =============================================================================

def find_pin_groups(in_entity_id, found_pins, found_scds, found_sbds, found_bns, found_dfs,
                    found_mins, entity_id_to_entity, forward, reverse):
    pin_groups = {}

    if not found_pins:
        return pin_groups, found_scds, found_sbds, found_bns, found_dfs

    # =========================================================================
    # FIX 1 — PIN-to-MIN discovery pass
    # Walk reverse[pin_id] for REL_HAS_PART to discover combo MINs whose
    # HAS_PART edges point to PIN entities rather than base INs.
    # MIN 822929 (Adderall amphetamine salts) is the canonical example: its
    # HAS_PART edges target the dextroamphetamine and amphetamine PINs, so the
    # one-hop IN → MIN scan never sees it.  Any such MIN is injected into
    # found_mins here before any other work so the rest of the pipeline
    # (including Fix 2 below) operates on a complete MIN set.
    # =========================================================================
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

    # =========================================================================
    # FIX 2 — pre-pass: build exclusion sets for combo SCDs/SBDs
    # Any SCD whose ingredient set matches a known MIN is a combo SCD that
    # belongs to that MIN, not to any individual PIN.  The corresponding SBDs
    # must be excluded from PIN groups for the same reason.
    # Both sets are computed up-front so the main loop can do O(1) lookups.
    # =========================================================================

    # scd_rxcui → min_rxcui for every combo SCD that matches a known MIN
    combo_scd_to_min = {}
    for scd_rxcui, scd_entity in list(found_scds.items()):
        is_combo, ingredients = is_combo_scd(
            scd_entity['id'], forward, reverse, entity_id_to_entity
        )
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

    # Derive combo SBD rxcuis by walking combo SCD → SCDC (reverse CONSTITUTES)
    # → SBD (forward CONSTITUTES).  This catches SBDs via both the SCDC path
    # and the BN → HAS_TRADENAME path in the main loop below.
    combo_sbd_rxcuis = set()
    for scd_rxcui in combo_scd_to_min:
        scd_entity = found_scds.get(scd_rxcui)
        if not scd_entity:
            continue
        for rel3, scdc_id in reverse.get(scd_entity['id'], []):
            if rel3 != REL_CONSTITUTES:
                continue
            for rel4, sbd_id in forward.get(scdc_id, []):
                if rel4 != REL_CONSTITUTES:
                    continue
                sbd_entity = entity_id_to_entity.get(sbd_id)
                if sbd_entity and sbd_entity.get('tty') == 'SBD':
                    combo_sbd_rxcuis.add(sbd_entity['rxcui'])

    # =========================================================================
    # Main PIN group building loop — original logic with FIX 2 guards inserted
    # =========================================================================
    for pin_rxcui, pin_entity in found_pins.items():
        pin_id = pin_entity['id']
        pin_groups[pin_rxcui] = {
            'entity': pin_entity,
            'scd': {}, 'bn': {}, 'sbd': {}, 'df': {}, 'min': {},
            'sbd_to_bn': {}
        }

        for rel_type, child_id in reverse.get(pin_id, []):
            if rel_type != REL_HAS_PRECISE_INGREDIENT:
                continue

            child_entity = entity_id_to_entity.get(child_id)
            if not child_entity:
                continue

            child_rxcui = child_entity['rxcui']
            child_tty = child_entity['tty']

            if child_tty == 'SCDC':
                for rel2, target_id in forward.get(child_id, []):
                    if rel2 != REL_CONSTITUTES:
                        continue

                    target_entity = entity_id_to_entity.get(target_id)
                    if not target_entity:
                        continue

                    target_rxcui = target_entity['rxcui']
                    target_tty = target_entity['tty']

                    if target_tty == 'SCD' and target_rxcui in found_scds:
                        # FIX 2a — combo SCD belongs to its MIN, not this PIN.
                        # Record the MIN reference on the PIN group for graph
                        # linkage, but leave the SCD in found_scds so the MIN
                        # group builder can claim it later.
                        if target_rxcui in combo_scd_to_min:
                            owning_min = combo_scd_to_min[target_rxcui]
                            pin_groups[pin_rxcui]['min'][owning_min] = found_mins[owning_min]
                            continue  # do NOT del from found_scds

                        pin_groups[pin_rxcui]['scd'][target_rxcui] = target_entity
                        del found_scds[target_rxcui]

                        for rel3, df_id in forward.get(target_id, []):
                            if rel3 == REL_HAS_DOSE_FORM:
                                df_entity = entity_id_to_entity.get(df_id)
                                if df_entity and df_entity['tty'] == 'DF' and df_entity['rxcui'] in found_dfs:
                                    pin_groups[pin_rxcui]['df'][df_entity['rxcui']] = df_entity

                    elif target_tty == 'SBD' and target_rxcui in found_sbds:
                        # FIX 2b — combo SBD belongs to its MIN, not this PIN.
                        # Leave it in found_sbds for MIN group building.
                        if target_rxcui in combo_sbd_rxcuis:
                            continue  # do NOT del from found_sbds

                        pin_groups[pin_rxcui]['sbd'][target_rxcui] = target_entity
                        for rel3, bn_id in reverse.get(target_id, []):
                            if rel3 == REL_TRADENAME_OF:
                                bn_entity = entity_id_to_entity.get(bn_id)
                                if bn_entity and bn_entity['tty'] == 'BN':
                                    pin_groups[pin_rxcui]['bn'][bn_entity['rxcui']] = bn_entity
                                    pin_groups[pin_rxcui]['sbd_to_bn'][target_rxcui] = bn_entity['rxcui']
                                    break
                        del found_sbds[target_rxcui]

            elif child_tty == 'BN':
                bn_id = child_entity['id']
                pin_groups[pin_rxcui]['bn'][child_rxcui] = child_entity

                for rel2, target_id in forward.get(bn_id, []):
                    if rel2 == REL_HAS_TRADENAME:
                        target_entity = entity_id_to_entity.get(target_id)
                        if target_entity and target_entity['tty'] == 'SBD':
                            target_rxcui = target_entity['rxcui']
                            if target_rxcui in found_sbds:
                                # FIX 2b — same guard for the BN → SBD path
                                if target_rxcui in combo_sbd_rxcuis:
                                    continue  # do NOT del from found_sbds

                                pin_groups[pin_rxcui]['sbd'][target_rxcui] = target_entity
                                pin_groups[pin_rxcui]['sbd_to_bn'][target_rxcui] = child_rxcui
                                del found_sbds[target_rxcui]

                if child_rxcui in found_bns:
                    del found_bns[child_rxcui]

    return pin_groups, found_scds, found_sbds, found_bns, found_dfs

# =============================================================================
# MAIN CONNECTION FINDER
# =============================================================================

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
        for rel_type, target_id in forward.get(bn_entity['id'], []):
            if rel_type == REL_HAS_TRADENAME:
                target_entity = entity_id_to_entity.get(target_id)
                if target_entity and target_entity['tty'] == 'SBD':
                    found_sbds[target_entity['rxcui']] = target_entity
                    bn_to_sbd[bn_rxcui].append(target_entity['rxcui'])
    
    # DFs from SCDs
    for scd_entity in list(found_scds.values()):
        for rel_type, df_id in forward.get(scd_entity['id'], []):
            if rel_type == REL_HAS_DOSE_FORM:
                df_entity = entity_id_to_entity.get(df_id)
                if df_entity and df_entity['tty'] == 'DF':
                    found_dfs[df_entity['rxcui']] = df_entity

    # ── NEW: Discover combo MINs reachable via PINs (IN → PIN → MIN) ─────────
    # Some MINs (e.g. Adderall: amphetamine aspartate / sulfate / dextro-* salts)
    # have HAS_PART relations to PIN entities, not to base INs directly.
    # Walking reverse[pin_id] catches them.
    for pin_entity in list(found_pins.values()):
        for _rel, source_id in reverse.get(pin_entity['id'], []):
            source_entity = entity_id_to_entity.get(source_id)
            if source_entity and source_entity['tty'] == 'MIN':
                if source_entity['rxcui'] not in found_mins:
                    found_mins[source_entity['rxcui']] = source_entity
    # ─────────────────────────────────────────────────────────────────────────
    
    # PIN groups
    pin_groups, found_scds, found_sbds, found_bns, found_dfs = find_pin_groups(
        in_entity_id, found_pins, found_scds, found_sbds, found_bns, found_dfs,
        found_mins, entity_id_to_entity, forward, reverse
    )
    
    # MIN processing
    min_data = {}
    for min_rxcui, min_entity in found_mins.items():
        ingredients = get_ingredients_from_min(min_entity['id'], forward, entity_id_to_entity)
        min_data[min_rxcui] = {
            'entity': min_entity,
            'ingredients': ingredients,
            'is_combo': len(ingredients) > 1,
            'combo_scds': [],
            'combo_sbds': []
        }
    
    # Combo MIN -> SCD/SBD
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
                    'rxcui': scd_entity['rxcui'],
                    'name': reformat_scd_name(scd_entity['name']),
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
                
                already_moved = any(sbd_entity['rxcui'] in pg['sbd'] for pg in pin_groups.values())
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
                    'name': reformat_sbd_name(sbd_entity['name'], {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'} if bn_rxc else None),
                    'tty': 'SBD',
                    'ingredients': min_info['ingredients'],
                    'ndcs': []
                }
                if bn_rxc:
                    sbd_obj['brand_name'] = {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'}
                    brand_is_combo[bn_rxc] = True
                
                min_info['combo_sbds'].append(sbd_obj)
                del found_sbds[sbd_entity['rxcui']]
    
    # Check remaining SCDs for combos
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
                    'rxcui': scd_rxcui,
                    'name': reformat_scd_name(scd_entity['name']),
                    'tty': 'SCD',
                    'ingredients': ingredients,
                    'ndcs': []
                })
                break
    
    for rxcui in scds_to_remove:
        found_scds.pop(rxcui, None)
    
    # Check remaining SBDs for combos
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
        
        for min_info in min_data.values():
            if not min_info['is_combo']:
                continue
            if {i['rxcui'] for i in min_info['ingredients']} == {i['rxcui'] for i in ingredients}:
                sbd_obj = {
                    'rxcui': sbd_rxcui,
                    'name': reformat_sbd_name(sbd_entity['name'], {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'} if bn_rxc else None),
                    'tty': 'SBD',
                    'ingredients': ingredients,
                    'ndcs': []
                }
                if bn_rxc:
                    sbd_obj['brand_name'] = {'rxcui': bn_rxc, 'name': bn_name, 'tty': 'BN'}
                    brand_is_combo[bn_rxc] = True
                min_info['combo_sbds'].append(sbd_obj)
                break
    
    for rxcui in sbds_to_remove:
        found_sbds.pop(rxcui, None)
    
    # Build pin output
    for pin_rxcui, pin_data in pin_groups.items():
        sbd_list = []
        for rxc, ent in pin_data['sbd'].items():
            bn_rxcui = pin_data['sbd_to_bn'].get(rxc)
            bn_info = {'rxcui': bn_rxcui, 'name': pin_data['bn'][bn_rxcui]['name'], 'tty': 'BN'} if bn_rxcui and bn_rxcui in pin_data['bn'] else None
            sbd_obj = {
                'rxcui': rxc,
                'name': reformat_sbd_name(ent['name'], bn_info),
                'tty': 'SBD',
                'ndcs': []
            }
            if bn_rxcui and bn_rxcui in pin_data['bn']:
                sbd_obj['brand_name'] = {'rxcui': bn_rxcui, 'name': pin_data['bn'][bn_rxcui]['name'], 'tty': 'BN'}
            sbd_list.append(sbd_obj)
        
        pin_obj = {
            'rxcui': pin_rxcui,
            'name': pin_data['entity']['name'],
            'tty': 'PIN',
            'scd': [{'rxcui': rxc, 'name': reformat_scd_name(ent['name']), 'tty': 'SCD', 'ndcs': []} for rxc, ent in pin_data['scd'].items()],
            'bn': [{'rxcui': rxc, 'name': ent['name'], 'tty': 'BN'} for rxc, ent in pin_data['bn'].items()],
            'sbd': sbd_list,
            'df': [{'rxcui': rxc, 'name': ent['name'], 'tty': 'DF'} for rxc, ent in pin_data['df'].items()]
        }
        result['pin'].append(pin_obj)
    
    # Flat SCDs/SBDs/BNs/DFs
    for rxcui, entity in found_scds.items():
        result['scd'].append({'rxcui': rxcui, 'name': reformat_scd_name(entity['name']), 'tty': 'SCD', 'ndcs': []})
    
    for rxcui, entity in found_sbds.items():
        brand_name = None
        for bn_rxc, sbd_list in bn_to_sbd.items():
            if rxcui in sbd_list and bn_rxc in found_bns:
                brand_name = {'rxcui': bn_rxc, 'name': found_bns[bn_rxc]['name'], 'tty': 'BN'}
        
        sbd_obj = {
            'rxcui': rxcui,
            'name': reformat_sbd_name(entity['name'], brand_name),
            'tty': 'SBD',
            'ndcs': []
        }
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
                output['costplus_unit_price'] = pricing['costplus_unit_billing_price']
                has_price = True
        
        return output, has_price
    
    for scd in connections.get('scd', []):
        for entry in rxcui_to_ndcs.get(scd.get('rxcui'), []):
            ndc_obj, has_price = process_ndc_entry(entry)
            if ndc_obj:
                scd['ndcs'].append(ndc_obj)
                if has_price:
                    extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    for sbd in connections.get('sbd', []):
        for entry in rxcui_to_ndcs.get(sbd.get('rxcui'), []):
            ndc_obj, has_price = process_ndc_entry(entry)
            if ndc_obj:
                sbd['ndcs'].append(ndc_obj)
                if has_price:
                    extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    for pin in connections.get('pin', []):
        for scd in pin.get('scd', []):
            for entry in rxcui_to_ndcs.get(scd.get('rxcui'), []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    scd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
        
        for sbd in pin.get('sbd', []):
            for entry in rxcui_to_ndcs.get(sbd.get('rxcui'), []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    sbd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
    
    for min_data in connections.get('min', []):
        for combo_scd in min_data.get('combo_scds', []):
            for entry in rxcui_to_ndcs.get(combo_scd.get('rxcui'), []):
                ndc_obj, has_price = process_ndc_entry(entry)
                if ndc_obj:
                    combo_scd['ndcs'].append(ndc_obj)
                    if has_price:
                        extracted_priced.add(ndc_obj.get('ndc11_no_hyphens', ''))
        
        for combo_sbd in min_data.get('combo_sbds', []):
            for entry in rxcui_to_ndcs.get(combo_sbd.get('rxcui'), []):
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
    
    return record, extracted, None


def main():
    parser = argparse.ArgumentParser(description='Extract GEO v22.4 - SBD Name Reformatting')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    
    print("=" * 80)
    print("EXTRACT GEO V22.5 - SBD/SCD Name Reformatting")
    print("  SBD names reformatted: 'Brand [ingredient] dose form'")
    print("  NDA/ANDA numbers stripped from SBD names")
    print("  Duration modifiers (21 DAY, 28 DAY) moved to end")
    print("  Ingredient prefixes (Preservative-Free) moved after dose form")
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
    print(f"\nV22.4: SBD names reformatted with brand first, duration/prefix handling")
    print("=" * 80)


if __name__ == "__main__":
    main()
