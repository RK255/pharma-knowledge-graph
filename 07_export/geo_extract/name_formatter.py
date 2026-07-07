# name_formatter.py
# All name reformatting logic — lifted verbatim from v22.6, zero changes.
import re
from config import INJECTABLE_DOSE_FORMS, DEVICE_NAME_MAP

DEVICE_NAME_RE = re.compile(r'^(Sensor)\b\s*', re.IGNORECASE)

DOSE_UNITS = [
    'MG/MG', 'MCG/MCG', 'UNT/UNT', 'U/U',
    'MG', 'MCG', 'ML', 'UNT', 'Unit', 'Units', 'IU', 'U', 'MEQ',
    'MG/ML', 'MCG/ML', 'MG/ACTUAT', 'MCG/ACTUAT',
    '%', 'MG/G', 'MCG/G',
    'CELLS/ML', 'CELLS', 'ACTUAT', 'BAU', 'SQCM', 'Amb a 1-U',
    'SQ-HDM', 'CM', 'IR', 'VIRAL-PARTICLES/ML',
    'VECTOR-GENOMES/ML', 'EIN/ML', 'UNT/ML',
]

RELEASE_MODIFIERS = [
    '9 HR', '12 HR', '24 HR', '72 HR', '84 HR', '168 HR',
    '8 HR', 'SR', 'ER', 'XR', 'CR', 'LA', 'SA', 'XL', '3-Bead',
]

DURATION_MODIFIERS = [
    '21 DAY', '28 DAY', '30 DAY', '60 DAY', '90 DAY',
    '1 DAY', '2 DAY', '3 DAY', '7 DAY', '14 DAY',
]

INGREDIENT_PREFIXES = [
    'Preservative-Free', 'Once-Daily', 'Twice-Daily',
    'Three-Times-Daily', 'Immediate-Release', 'Sustained-Release',
]


def apply_injectable_dose_calculation(name):
    if re.search(r'\d+(?:\.\d+)?\s*MG\s*$', name, re.IGNORECASE):
        return name
    forms_pattern = '|'.join(
        f.replace('-', r'[-\s]').replace(' ', r'[-\s]') for f in INJECTABLE_DOSE_FORMS
    )
    pattern = (
        r'^(.*?\s)(\d+(?:\.\d+)?)\s*MG/ML\s+(' + forms_pattern + r')\s+'
        r'(\d+(?:\.\d+)?)\s*ML\b(.*)'
    )
    m = re.match(pattern, name, re.IGNORECASE)
    if not m:
        return name
    before = m.group(1)
    if re.search(r'MG/ML', before, re.IGNORECASE) or ' / ' in before:
        return name
    conc_str = m.group(2)
    form     = m.group(3)
    vol_str  = m.group(4)
    after    = m.group(5)
    total    = round(float(conc_str) * float(vol_str), 6)
    total_str = f"{total:.6f}".rstrip('0').rstrip('.')
    return f"{before}{total_str} MG ({conc_str} MG/ML) {form} {vol_str} ML{after}"


def extract_brand(name, fallback_brand=None):
    name = re.sub(r'^(NDA\d+|ANDA\d+)\s+', '', name, flags=re.IGNORECASE).strip()
    last_open = name.rfind('[')
    if last_open == -1:
        return (fallback_brand, None, name) if fallback_brand else (None, None, name)
    close = name.find(']', last_open)
    if close == -1:
        return (fallback_brand, None, name) if fallback_brand else (None, None, name)
    brand_text     = name[last_open + 1:close].strip()
    before_bracket = name[:last_open].strip()
    after_bracket  = name[close + 1:].strip()
    dose_before_bracket = find_first_dose_position(before_bracket) != -1
    if not dose_before_bracket:
        brand, extra_dose = clean_brand_content(brand_text)
        if not brand:
            return (fallback_brand, None, before_bracket) if fallback_brand else (None, None, name)
        clean_name = brand + ' ' + after_bracket if after_bracket else brand
        return brand, extra_dose, clean_name
    clean_name = before_bracket
    brand, extra_dose = clean_brand_content(brand_text)
    if not brand:
        return (fallback_brand, None, clean_name) if fallback_brand else (None, None, name)
    return brand, extra_dose, clean_name


def clean_brand_content(brand_text):
    if not brand_text:
        return None, None
    text = brand_text.strip()
    if re.match(r'^(NDA|ANDA)\d+$', text, re.IGNORECASE):
        return None, None
    text = re.sub(r'^(NDA|ANDA)\d+\s*', '', text, flags=re.IGNORECASE).strip()
    if not text:
        return None, None
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
    for mod in DURATION_MODIFIERS:
        pattern = r'^' + r'\s+'.join(mod.split()) + r'\s+'
        if re.match(pattern, name, re.IGNORECASE):
            clean = re.sub(pattern, '', name, count=1, flags=re.IGNORECASE).strip()
            return mod, clean
    return None, name


def extract_ingredient_prefix(ingredient):
    for prefix in INGREDIENT_PREFIXES:
        pattern = r'^' + prefix.replace('-', r'\s*-\s*') + r'\s+'
        if re.match(pattern, ingredient, re.IGNORECASE):
            clean = re.sub(pattern, '', ingredient, count=1, flags=re.IGNORECASE).strip()
            return prefix, clean
    return None, ingredient


def extract_container_size(name):
    match = re.match(r'^(\d+(?:\.\d+)?)\s*(ML|L|MG|ACTUAT)\s+(.+)', name, re.IGNORECASE)
    if match:
        rest = match.group(3)
        if find_first_dose_position(rest) != -1:
            container = f"{match.group(1)} {match.group(2).upper()}"
            return container, rest.strip()
    return None, name


def extract_release_modifier(ingredient):
    for mod in RELEASE_MODIFIERS:
        pattern = '^' + r'\s+'.join(mod.split()) + r'\s+'
        if re.match(pattern, ingredient, re.IGNORECASE):
            clean = re.sub(pattern, '', ingredient, count=1, flags=re.IGNORECASE).strip()
            return mod, clean
    return None, ingredient


def find_first_dose_position(name):
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
    parts = clean_name.split(' / ')
    if len(parts) < 2:
        return None
    ingredients = []
    doses       = []
    dose_form   = ''
    for i, part in enumerate(parts):
        part = part.strip()
        dose_match         = None
        dose_unit_matched  = None
        for unit in sorted(DOSE_UNITS, key=len, reverse=True):
            escaped = unit.replace('/', r'\/')
            pattern = rf'(\d+(?:\.\d+)?)\s*({escaped})(?:\s|$)'
            m = re.search(pattern, part, re.IGNORECASE)
            if m:
                dose_match        = m
                dose_unit_matched = unit
                break
        if not dose_match:
            return None
        ingredient = part[:dose_match.start()].strip()
        base_unit  = dose_unit_matched.upper()
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
        'doses':       ' / '.join(doses),
        'dose_form':   dose_form
    }


def extract_device_name(name):
    m = DEVICE_NAME_RE.match(name)
    if not m:
        return None, name
    raw     = m.group(1)
    display = DEVICE_NAME_MAP.get(raw.upper(), raw)
    return display, name[m.end():].strip()


def reformat_sbd_name(name, brand_name_from_bn=None):
    duration_mod, name = extract_duration_modifier(name)
    fallback = brand_name_from_bn.get('name') if brand_name_from_bn else None
    brand, extra_dose, name_after_brand = extract_brand(name, fallback_brand=fallback)
    if not brand:
        return name
    device_name, name_after_brand = extract_device_name(name_after_brand)
    container, name_after_container = extract_container_size(name_after_brand)
    if ' / ' in name_after_container:
        parsed = parse_combo_product(name_after_container)
        if parsed:
            clean_ingredients   = []
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
            if device_name:  result += f" {device_name}"
            if container:    result += f" {container}"
            if duration_mod: result += f" {duration_mod}"
            if extra_dose:   result += f" {extra_dose}"
            return apply_injectable_dose_calculation(result)
    dose_pos = find_first_dose_position(name_after_container)
    if dose_pos == -1:
        return name
    ingredient_part = name_after_container[:dose_pos].strip()
    release_mods = []
    while True:
        mod, ingredient_part = extract_release_modifier(ingredient_part)
        if not mod:
            break
        release_mods.append(mod)
    ingredient_prefix, ingredient_part = extract_ingredient_prefix(ingredient_part)
    after_ingredient = name_after_container[dose_pos:]
    dose_match = re.match(r'^(\d+(?:\.\d+)?)\s*([A-Za-z/]+)\s*(.*)$', after_ingredient)
    if not dose_match:
        return name
    dose      = f"{dose_match.group(1)} {dose_match.group(2).upper()}"
    dose_form = dose_match.group(3).strip()
    if ingredient_prefix:
        dose_form = dose_form + ' ' + ingredient_prefix
    result = f"{brand} [{ingredient_part}] {dose} {dose_form}"
    if release_mods: result += ' ' + ' '.join(release_mods)
    if device_name:  result += f" {device_name}"
    if container:    result += f" {container}"
    if duration_mod: result += f" {duration_mod}"
    if extra_dose:   result += f" {extra_dose}"
    return apply_injectable_dose_calculation(result)


def reformat_scd_name(name):
    if not name:
        return name
    working  = name
    trailing = []
    while True:
        mod, working = extract_duration_modifier(working)
        if not mod: break
        trailing.append(mod)
    while True:
        mod, working = extract_release_modifier(working)
        if not mod: break
        trailing.append(mod)
    while True:
        container, working = extract_container_size(working)
        if not container: break
        trailing.append(container)
    while True:
        mod, working = extract_release_modifier(working)
        if not mod: break
        trailing.append(mod)
    device_name, working = extract_device_name(working)
    if device_name:
        trailing.append(device_name)
        while True:
            container, working = extract_container_size(working)
            if not container: break
            trailing.append(container)
    dose_pos = find_first_dose_position(working)
    if dose_pos == -1:
        result = working
        if trailing:
            result = working + ' ' + ' '.join(trailing)
        return apply_injectable_dose_calculation(result)
    if ' / ' in working:
        parsed = parse_combo_product(working)
        if parsed:
            result = f"{parsed['ingredients']} {parsed['doses']} {parsed['dose_form']}"
            if trailing:
                result += ' ' + ' '.join(trailing)
            return apply_injectable_dose_calculation(result)
    result = working
    if trailing:
        result += ' ' + ' '.join(trailing)
    return apply_injectable_dose_calculation(result)

# ── GPCK / BPCK pack name formatters ─────────────────────────────────────────

def reformat_gpck_name(name: str) -> str:
    """GPCK pack names need no structural change — strip whitespace only."""
    return name.strip()


def reformat_bpck_name(name: str) -> str:
    """
    Move the trailing [Brand Name] to the front, matching the SBD pattern.

      {12 (Drug A) / 9 (Drug B) } Pack [Brand]
      → Brand {12 (Drug A) / 9 (Drug B) } Pack

    Falls back to returning the input unchanged if no valid trailing
    [Brand Name] is found, so no data is silently lost on unexpected formats.
    """
    name       = name.strip()
    last_open  = name.rfind('[')
    last_close = name.rfind(']')
    if last_open == -1 or last_close != len(name) - 1:
        return name
    brand = name[last_open + 1 : last_close].strip()
    pack  = name[:last_open].strip()
    return f"{brand} {pack}" if brand else name
