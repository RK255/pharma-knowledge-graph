#!/usr/bin/env python3
"""
pack_name_formatter.py — GPCK / BPCK name formatter

  --test          Run hardcoded test suite
  --test <file>   Walk JSONL (including nested connections) → bake real samples
                  into HARDCODED_TESTS → run suite
"""

import sys
import json
import re
import argparse
from pathlib import Path
from typing import Optional

PICK = 12   # samples per type to bake into the test suite


# =============================================================================
# FORMATTER
# =============================================================================

def format_gpck(raw: str) -> str:
    return raw.strip()


def format_bpck(raw: str) -> str:
    """
    {… } Pack [Brand Name]  →  Brand Name {… } Pack
    Returns input unchanged if no valid trailing [Brand Name] found.
    """
    name       = raw.strip()
    last_open  = name.rfind('[')
    last_close = name.rfind(']')
    if last_open == -1 or last_close != len(name) - 1:
        return name
    brand = name[last_open + 1 : last_close].strip()
    pack  = name[:last_open].strip()
    return f"{brand} {pack}" if brand else name


def format_pack(raw: str, tty: str) -> str:
    t = tty.upper().strip()
    if t == 'GPCK': return format_gpck(raw)
    if t == 'BPCK': return format_bpck(raw)
    return raw


# =============================================================================
# TTY INFERENCE FROM NAME PATTERN
# =============================================================================

_BPCK_RE = re.compile(r'^\{.+\}\s*Pack\s*\[.+\]\s*$', re.DOTALL)
_GPCK_RE = re.compile(r'^\{.+\}\s*Pack\s*$',           re.DOTALL)


def infer_tty(name: str) -> Optional[str]:
    s = name.strip()
    if _BPCK_RE.match(s): return 'BPCK'
    if _GPCK_RE.match(s): return 'GPCK'
    return None


# =============================================================================
# HARDCODED_TESTS
# — run  --test <path/to/full_geo_extraction_v23.jsonl>  to replace with real data
# =============================================================================

HARDCODED_TESTS = [

    # ── GPCK — real data ─────────────────────────────────────────────────────
    {
        'tty':   'GPCK',
        'label': 'single-component GPCK',
        'raw':   '{3 (bupivacaine hydrochloride 100 MG Drug Implant) } Pack',
        'want':  '{3 (bupivacaine hydrochloride 100 MG Drug Implant) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '2-component GPCK',
        'raw':   '{1 (acetaminophen 500 MG / chlorpheniramine maleate 2 MG / dextromethorphan hydrobromide 15 MG Oral Tablet) / 1 (acetaminophen 500 MG / dextromethorphan hydrobromide 15 MG Oral Tablet) } Pack',
        'want':  '{1 (acetaminophen 500 MG / chlorpheniramine maleate 2 MG / dextromethorphan hydrobromide 15 MG Oral Tablet) / 1 (acetaminophen 500 MG / dextromethorphan hydrobromide 15 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '3-component GPCK',
        'raw':   '{4 (amoxicillin 500 MG Oral Capsule) / 2 (clarithromycin 500 MG Oral Tablet) / 2 (lansoprazole 30 MG Delayed Release Oral Capsule) } Pack',
        'want':  '{4 (amoxicillin 500 MG Oral Capsule) / 2 (clarithromycin 500 MG Oral Tablet) / 2 (lansoprazole 30 MG Delayed Release Oral Capsule) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '5-component GPCK',
        'raw':   '{2 (apomorphine hydrochloride 10 MG Sublingual Film) / 2 (apomorphine hydrochloride 15 MG Sublingual Film) / 2 (apomorphine hydrochloride 20 MG Sublingual Film) / 2 (apomorphine hydrochloride 25 MG Sublingual Film) / 2 (apomorphine hydrochloride 30 MG Sublingual Film) } Pack',
        'want':  '{2 (apomorphine hydrochloride 10 MG Sublingual Film) / 2 (apomorphine hydrochloride 15 MG Sublingual Film) / 2 (apomorphine hydrochloride 20 MG Sublingual Film) / 2 (apomorphine hydrochloride 25 MG Sublingual Film) / 2 (apomorphine hydrochloride 30 MG Sublingual Film) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': 'single-component GPCK',
        'raw':   '{51 (dexamethasone 1.5 MG Oral Tablet) } Pack',
        'want':  '{51 (dexamethasone 1.5 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '2-component GPCK',
        'raw':   '{1 (acetaminophen 33.3 MG/ML / chlorpheniramine maleate 0.133 MG/ML / dextromethorphan hydrobromide 1 MG/ML Oral Solution) / 1 (acetaminophen 33.3 MG/ML / dextromethorphan hydrobromide 1 MG/ML Oral Solution) } Pack',
        'want':  '{1 (acetaminophen 33.3 MG/ML / chlorpheniramine maleate 0.133 MG/ML / dextromethorphan hydrobromide 1 MG/ML Oral Solution) / 1 (acetaminophen 33.3 MG/ML / dextromethorphan hydrobromide 1 MG/ML Oral Solution) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '3-component GPCK',
        'raw':   '{4 (amoxicillin 500 MG Oral Capsule) / 2 (clarithromycin 500 MG Oral Tablet) / 2 (omeprazole 20 MG Delayed Release Oral Capsule) } Pack',
        'want':  '{4 (amoxicillin 500 MG Oral Capsule) / 2 (clarithromycin 500 MG Oral Tablet) / 2 (omeprazole 20 MG Delayed Release Oral Capsule) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '5-component GPCK',
        'raw':   '{5 (dienogest 2 MG / estradiol valerate 2 MG Oral Tablet) / 17 (dienogest 3 MG / estradiol valerate 2 MG Oral Tablet) / 2 (estradiol valerate 1 MG Oral Tablet) / 2 (estradiol valerate 3 MG Oral Tablet) / 2 (inert ingredients 1 MG Oral Tablet) } Pack',
        'want':  '{5 (dienogest 2 MG / estradiol valerate 2 MG Oral Tablet) / 17 (dienogest 3 MG / estradiol valerate 2 MG Oral Tablet) / 2 (estradiol valerate 1 MG Oral Tablet) / 2 (estradiol valerate 3 MG Oral Tablet) / 2 (inert ingredients 1 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': 'single-component GPCK',
        'raw':   '{35 (dexamethasone 1.5 MG Oral Tablet) } Pack',
        'want':  '{35 (dexamethasone 1.5 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '2-component GPCK',
        'raw':   '{1 (acetaminophen 1000 MG / chlorpheniramine maleate 4 MG / dextromethorphan hydrobromide 30 MG Powder for Oral Solution) / 1 (acetaminophen 1000 MG / dextromethorphan hydrobromide 30 MG Powder for Oral Solution) } Pack',
        'want':  '{1 (acetaminophen 1000 MG / chlorpheniramine maleate 4 MG / dextromethorphan hydrobromide 30 MG Powder for Oral Solution) / 1 (acetaminophen 1000 MG / dextromethorphan hydrobromide 30 MG Powder for Oral Solution) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '3-component GPCK',
        'raw':   '{56 (amoxicillin 500 MG Oral Capsule) / 28 (clarithromycin 500 MG Oral Tablet) / 28 (vonoprazan 20 MG Oral Tablet) } Pack',
        'want':  '{56 (amoxicillin 500 MG Oral Capsule) / 28 (clarithromycin 500 MG Oral Tablet) / 28 (vonoprazan 20 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'GPCK',
        'label': '4-component GPCK',
        'raw':   '{7 (ethinyl estradiol 0.01 MG Oral Tablet) / 42 (ethinyl estradiol 0.02 MG / levonorgestrel 0.15 MG Oral Tablet) / 21 (ethinyl estradiol 0.025 MG / levonorgestrel 0.15 MG Oral Tablet) / 21 (ethinyl estradiol 0.03 MG / levonorgestrel 0.15 MG Oral Tablet) } Pack',
        'want':  '{7 (ethinyl estradiol 0.01 MG Oral Tablet) / 42 (ethinyl estradiol 0.02 MG / levonorgestrel 0.15 MG Oral Tablet) / 21 (ethinyl estradiol 0.025 MG / levonorgestrel 0.15 MG Oral Tablet) / 21 (ethinyl estradiol 0.03 MG / levonorgestrel 0.15 MG Oral Tablet) } Pack',
    },

    # ── BPCK — real data ─────────────────────────────────────────────────────
    {
        'tty':   'BPCK',
        'label': 'single-component BPCK [Xaracoll 3 Implant Dose] — brand with number',
        'raw':   '{3 (bupivacaine hydrochloride 100 MG Drug Implant [Xaracoll]) } Pack [Xaracoll 3 Implant Dose]',
        'want':  'Xaracoll 3 Implant Dose {3 (bupivacaine hydrochloride 100 MG Drug Implant [Xaracoll]) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': "single-component BPCK [Humira Pen - Crohn's Disease Starter Pack] — hyphenated brand",
        'raw':   "{6 (0.8 ML adalimumab 50 MG/ML Auto-Injector [Humira]) } Pack [Humira Pen - Crohn's Disease Starter Pack]",
        'want':  "Humira Pen - Crohn's Disease Starter Pack {6 (0.8 ML adalimumab 50 MG/ML Auto-Injector [Humira]) } Pack",
    },
    {
        'tty':   'BPCK',
        'label': 'single-component BPCK [Suprep Bowel Prep Kit] — multi-word brand',
        'raw':   '{2 (480 ML) (magnesium sulfate 0.0277 MEQ/ML / potassium sulfate 0.0374 MEQ/ML / sodium sulfate 0.257 MEQ/ML Oral Solution) } Pack [Suprep Bowel Prep Kit]',
        'want':  'Suprep Bowel Prep Kit {2 (480 ML) (magnesium sulfate 0.0277 MEQ/ML / potassium sulfate 0.0374 MEQ/ML / sodium sulfate 0.257 MEQ/ML Oral Solution) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': 'single-component BPCK [LymePak] — single-word brand',
        'raw':   '{42 (doxycycline hyclate 100 MG Oral Tablet) } Pack [LymePak]',
        'want':  'LymePak {42 (doxycycline hyclate 100 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '2-component BPCK [Osmolex 322 MG Daily Dosing] — brand with number',
        'raw':   '{30 (24 HR amantadine 129 MG Extended Release Oral Tablet [Osmolex]) / 30 (24 HR amantadine 193 MG Extended Release Oral Tablet [Osmolex]) } Pack [Osmolex 322 MG Daily Dosing]',
        'want':  'Osmolex 322 MG Daily Dosing {30 (24 HR amantadine 129 MG Extended Release Oral Tablet [Osmolex]) / 30 (24 HR amantadine 193 MG Extended Release Oral Tablet [Osmolex]) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '2-component BPCK [CitraNatal B-Calm Kit] — hyphenated brand',
        'raw':   '{30 (ascorbic acid 120 MG / calcium citrate 125 MG / cholecalciferol 400 UNT / folic acid 1 MG / iron carbonyl 20 MG / pyridoxine hydrochloride 25 MG Oral Tablet) / 10 (pyridoxine hydrochloride 25 MG Oral Tablet) } Pack [CitraNatal B-Calm Kit]',
        'want':  'CitraNatal B-Calm Kit {30 (ascorbic acid 120 MG / calcium citrate 125 MG / cholecalciferol 400 UNT / folic acid 1 MG / iron carbonyl 20 MG / pyridoxine hydrochloride 25 MG Oral Tablet) / 10 (pyridoxine hydrochloride 25 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '2-component BPCK [Pronto Plus Complete Lice Remover System] — multi-word brand',
        'raw':   '{1 (60 ML) (benzalkonium chloride 1 MG/ML Topical Solution [Pronto Plus Lice Egg Remover]) / 1 (60 ML) (piperonyl butoxide 40 MG/ML / pyrethrins 3.3 MG/ML Medicated Shampoo [Pronto Plus]) } Pack [Pronto Plus Complete Lice Remover System]',
        'want':  'Pronto Plus Complete Lice Remover System {1 (60 ML) (benzalkonium chloride 1 MG/ML Topical Solution [Pronto Plus Lice Egg Remover]) / 1 (60 ML) (piperonyl butoxide 40 MG/ML / pyrethrins 3.3 MG/ML Medicated Shampoo [Pronto Plus]) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '2-component BPCK [Plenvu] — single-word brand',
        'raw':   '{1 (ascorbic acid 7540 MG / polyethylene glycol 3350 40000 MG / potassium chloride 1200 MG / sodium ascorbate 48110 MG / sodium chloride 3200 MG Powder for Oral Solution) / 1 (polyethylene glycol 3350 100000 MG / potassium chloride 1000 MG / sodium chloride 2000 MG / sodium sulfate 9000 MG Powder for Oral Solution) } Pack [Plenvu]',
        'want':  'Plenvu {1 (ascorbic acid 7540 MG / polyethylene glycol 3350 40000 MG / potassium chloride 1200 MG / sodium ascorbate 48110 MG / sodium chloride 3200 MG Powder for Oral Solution) / 1 (polyethylene glycol 3350 100000 MG / potassium chloride 1000 MG / sodium chloride 2000 MG / sodium sulfate 9000 MG Powder for Oral Solution) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '3-component BPCK [Voquezna 14 Day TriplePak 20;500;500] — brand with number',
        'raw':   '{56 (amoxicillin 500 MG Oral Capsule) / 28 (clarithromycin 500 MG Oral Tablet) / 28 (vonoprazan 20 MG Oral Tablet) } Pack [Voquezna 14 Day TriplePak 20;500;500]',
        'want':  'Voquezna 14 Day TriplePak 20;500;500 {56 (amoxicillin 500 MG Oral Capsule) / 28 (clarithromycin 500 MG Oral Tablet) / 28 (vonoprazan 20 MG Oral Tablet) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '3-component BPCK [Lamictal ODT Orange Patient Titration Kit (For Patients Not Taking Enzyme-Inducing Drugs or Valproate)] — hyphenated brand',
        'raw':   '{7 (lamotrigine 100 MG Disintegrating Oral Tablet [Lamictal]) / 14 (lamotrigine 25 MG Disintegrating Oral Tablet [Lamictal]) / 14 (lamotrigine 50 MG Disintegrating Oral Tablet [Lamictal]) } Pack [Lamictal ODT Orange Patient Titration Kit (For Patients Not Taking Enzyme-Inducing Drugs or Valproate)]',
        'want':  'Lamictal ODT Orange Patient Titration Kit (For Patients Not Taking Enzyme-Inducing Drugs or Valproate) {7 (lamotrigine 100 MG Disintegrating Oral Tablet [Lamictal]) / 14 (lamotrigine 25 MG Disintegrating Oral Tablet [Lamictal]) / 14 (lamotrigine 50 MG Disintegrating Oral Tablet [Lamictal]) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '5-component BPCK [Kynmobi Titration Kit] — multi-word brand',
        'raw':   '{2 (apomorphine hydrochloride 10 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 15 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 20 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 25 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 30 MG Sublingual Film [Kynmobi]) } Pack [Kynmobi Titration Kit]',
        'want':  'Kynmobi Titration Kit {2 (apomorphine hydrochloride 10 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 15 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 20 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 25 MG Sublingual Film [Kynmobi]) / 2 (apomorphine hydrochloride 30 MG Sublingual Film [Kynmobi]) } Pack',
    },
    {
        'tty':   'BPCK',
        'label': '3-component BPCK [Omeclamox] — single-word brand',
        'raw':   '{4 (amoxicillin 500 MG Oral Capsule) / 2 (clarithromycin 500 MG Oral Tablet) / 2 (omeprazole 20 MG Delayed Release Oral Capsule) } Pack [Omeclamox]',
        'want':  'Omeclamox {4 (amoxicillin 500 MG Oral Capsule) / 2 (clarithromycin 500 MG Oral Tablet) / 2 (omeprazole 20 MG Delayed Release Oral Capsule) } Pack',
    },

]


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_suite() -> bool:
    W = 72
    print('\n' + '=' * W)
    print('GPCK / BPCK NAME FORMATTER  —  Test Suite')
    synth = sum(1 for t in HARDCODED_TESTS if 'synthetic' in t.get('label', '').lower())
    if synth:
        print(f'  ⚠️   {synth}/{len(HARDCODED_TESTS)} tests are synthetic placeholders')
        print('  Run:  --test <path/to/full_geo_extraction_v23.jsonl>  to replace')
    print('=' * W)

    passed = failed = 0
    for i, tc in enumerate(HARDCODED_TESTS, 1):
        got  = format_pack(tc['raw'], tc['tty'])
        ok   = got == tc['want']
        icon = '✅' if ok else '❌'
        print(f"\n[{i:02d}] {icon}  [{tc['tty']}]  {tc['label']}")
        if ok:
            disp = got if len(got) <= 88 else got[:85] + '...'
            print(f"       OUT : {disp}")
            passed += 1
        else:
            print(f"       RAW : {tc['raw']}")
            print(f"       WANT: {tc['want']}")
            print(f"       GOT : {got}")
            failed += 1

    print('\n' + '=' * W)
    print(f"  {'✅  ALL PASSED' if not failed else f'❌  {failed} FAILED'}  ({passed}/{len(HARDCODED_TESTS)})")
    print('=' * W + '\n')
    return failed == 0


# =============================================================================
# DIVERSITY SELECTION
# =============================================================================

def _component_count(name: str) -> int:
    inner = re.search(r'\{(.+?)\}\s*Pack', name, re.DOTALL)
    if not inner:
        return 1
    depth = slashes = 0
    for ch in inner.group(1):
        if ch == '(':              depth   += 1
        elif ch == ')':            depth   -= 1
        elif ch == '/' and depth == 0: slashes += 1
    return slashes + 1


def _brand_bucket(name: str) -> str:
    m = re.search(r'\[([^\]]+)\]\s*$', name.strip())
    if not m:
        return 'no_brand'
    b = m.group(1).strip()
    if len(b.split()) == 1:          return 'single_word'
    if any(c.isdigit() for c in b):  return 'has_number'
    if '-' in b:                     return 'hyphenated'
    return 'multi_word'


def select_diverse(samples: list[str], tty: str, target: int) -> list[str]:
    if len(samples) <= target:
        return samples
    buckets: dict[str, list[str]] = {}
    for s in samples:
        key = (
            str(min(_component_count(s), 4))
            if tty == 'GPCK'
            else f"{min(_component_count(s), 3)}_{_brand_bucket(s)}"
        )
        buckets.setdefault(key, []).append(s)
    out: list[str] = []
    keys = sorted(buckets)
    while len(out) < target:
        progress = False
        for k in keys:
            if buckets[k] and len(out) < target:
                out.append(buckets[k].pop(0))
                progress = True
        if not progress:
            break
    return out[:target]


def _auto_label(raw: str, tty: str) -> str:
    n    = _component_count(raw)
    comp = f"{n}-component" if n > 1 else "single-component"
    rate = bool(re.search(r'MG/(HR|24HR|ACTUAT)', raw, re.IGNORECASE))

    if tty == 'GPCK':
        return f"{comp} GPCK" + (" — rate dose form" if rate else "")

    m     = re.search(r'\[([^\]]+)\]\s*$', raw.strip())
    brand = m.group(1).strip() if m else '(no brand)'
    words = brand.split()
    if len(words) == 1:                   bdesc = "single-word brand"
    elif any(c.isdigit() for c in brand): bdesc = "brand with number"
    elif '-' in brand:                    bdesc = "hyphenated brand"
    elif 'Pack' in brand:                 bdesc = "brand containing 'Pack'"
    else:                                 bdesc = "multi-word brand"
    return f"{comp} BPCK [{brand}] — {bdesc}" + (" + rate dose" if rate else "")


# =============================================================================
# RECURSIVE JSON WALKER
# =============================================================================

def _walk(obj: any, gpck: list[str], bpck: list[str], seen: set[str], max_each: int) -> None:
    """
    Depth-first walk of any JSON value (dict / list / str / other).
    Harvests every string that matches the GPCK or BPCK name pattern.
    Handles arbitrary nesting depth — IN → MIN/PIN → SBD/SCD → GPCK/BPCK etc.
    """
    if len(gpck) >= max_each and len(bpck) >= max_each:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if s and s not in seen:
            tty = infer_tty(s)
            if tty == 'GPCK' and len(gpck) < max_each:
                gpck.append(s)
                seen.add(s)
            elif tty == 'BPCK' and len(bpck) < max_each:
                bpck.append(s)
                seen.add(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk(v, gpck, bpck, seen, max_each)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, gpck, bpck, seen, max_each)


# =============================================================================
# BAKE
# =============================================================================

def _render_block(gpck: list[str], bpck: list[str]) -> str:
    lines = ['HARDCODED_TESTS = [', '']
    lines.append("    # ── GPCK — real data ─────────────────────────────────────────────────────")
    for raw in gpck:
        lines += [
            '    {',
            f"        'tty':   'GPCK',",
            f"        'label': {repr(_auto_label(raw, 'GPCK'))},",
            f"        'raw':   {repr(raw)},",
            f"        'want':  {repr(format_pack(raw, 'GPCK'))},",
            '    },',
        ]
    lines += ['', "    # ── BPCK — real data ─────────────────────────────────────────────────────"]
    for raw in bpck:
        lines += [
            '    {',
            f"        'tty':   'BPCK',",
            f"        'label': {repr(_auto_label(raw, 'BPCK'))},",
            f"        'raw':   {repr(raw)},",
            f"        'want':  {repr(format_pack(raw, 'BPCK'))},",
            '    },',
        ]
    lines += ['', ']']
    return '\n'.join(lines)


def _write_in_place(new_block: str) -> None:
    sp    = Path(__file__).resolve()
    lines = sp.read_text(encoding='utf-8').splitlines(keepends=True)

    start = next(
        (i for i, l in enumerate(lines) if re.match(r'^HARDCODED_TESTS\s*=\s*\[', l)),
        None,
    )
    if start is None:
        sys.exit("❌  Cannot find HARDCODED_TESTS in script")

    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r'^]\s*$', lines[i])),
        None,
    )
    if end is None:
        sys.exit("❌  Cannot find closing ']' of HARDCODED_TESTS")

    bak = sp.with_suffix('.py.bak')
    bak.write_text(''.join(lines), encoding='utf-8')
    print(f"   💾  Backup : {bak}")

    new_lines = lines[:start] + (new_block + '\n').splitlines(keepends=True) + lines[end + 1:]
    sp.write_text(''.join(new_lines), encoding='utf-8')
    print(f"   ✅  Written : {sp}")


def run_bake(jsonl_path: str) -> None:
    path = Path(jsonl_path)
    if not path.exists():
        sys.exit(f"❌  File not found: {jsonl_path}")

    print(f"\n🔍  Scanning {path.name} …")
    print("   walking all nested connections for GPCK/BPCK …")

    gpck_all: list[str] = []
    bpck_all: list[str] = []
    seen:     set[str]  = set()
    total = 0

    with path.open('r', encoding='utf-8') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            _walk(rec, gpck_all, bpck_all, seen, 2000)

    print(f"   Records : {total:,}   GPCK : {len(gpck_all):,}   BPCK : {len(bpck_all):,}")

    if not gpck_all and not bpck_all:
        sys.exit(
            "❌  No GPCK or BPCK records found.\n"
            "   The file may not yet contain pack entities, or the name pattern\n"
            "   doesn't match.  Sample a record's 'connections' field to inspect."
        )

    gpck_sel = select_diverse(gpck_all, 'GPCK', PICK)
    bpck_sel = select_diverse(bpck_all, 'BPCK', PICK)

    W = 76
    print(f"\n{'━' * W}")
    print(f"  Selected  {len(gpck_sel)} GPCK  +  {len(bpck_sel)} BPCK  (PICK={PICK})")
    print(f"{'━' * W}\n")

    for tty, sel in [('GPCK', gpck_sel), ('BPCK', bpck_sel)]:
        icon = '📦' if tty == 'GPCK' else '🏷️ '
        print(f"{icon}  {tty}")
        print('-' * W)
        for i, raw in enumerate(sel, 1):
            fmt   = format_pack(raw, tty)
            raw_d = raw if len(raw) <= 72 else raw[:69] + '...'
            fmt_d = fmt if len(fmt) <= 72 else fmt[:69] + '...'
            print(f"  [{i:02d}]  {_auto_label(raw, tty)}")
            print(f"        RAW: {raw_d}")
            print(f"        FMT: {fmt_d if fmt != raw.strip() else '(unchanged)'}")
        print()

    print(f"{'━' * W}")
    print("  Writing HARDCODED_TESTS …\n")
    _write_in_place(_render_block(gpck_sel, bpck_sel))


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description='GPCK/BPCK pack name formatter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'examples:\n'
            '  %(prog)s --test\n'
            '  %(prog)s --test /path/to/full_geo_extraction_v23.jsonl\n'
        ),
    )
    parser.add_argument(
        '--test', nargs='?', const='__suite__', metavar='FILE',
        help='No arg: run test suite.  With FILE: bake real tests from JSONL then run suite.',
    )
    args = parser.parse_args()

    if args.test is None:
        parser.print_help()
        return

    if args.test == '__suite__':
        sys.exit(0 if run_suite() else 1)

    run_bake(args.test)
    print()
    sys.exit(0 if run_suite() else 1)


if __name__ == '__main__':
    main()
