#!/usr/bin/env python3
"""
02_rxnorm/02_atc_enrich.py
"""

import json
from pathlib import Path
from collections import Counter
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_DATA_DIR
MRCONSO     = RAW_DATA_DIR / "extracted_rrf" / "UMLS2026AA_extracted" / "rrf" / "MRCONSO.RRF"
OUTPUT_JSON = RAW_DATA_DIR / "rxcui_to_atc.json"

COL_CUI  = 0
COL_SAB  = 11
COL_SCUI = 9
COL_STR  = 13
COL_NAME = 14   # ATC name lives here (e.g. "mesna", "All other therapeutic products")

ATC_L1_NAMES = {
    "A": "Alimentary tract and metabolism",
    "B": "Blood and blood forming organs",
    "C": "Cardiovascular system",
    "D": "Dermatologicals",
    "G": "Genito-urinary system and sex hormones",
    "H": "Systemic hormonal preparations",
    "J": "Antiinfectives for systemic use",
    "L": "Antineoplastic and immunomodulating agents",
    "M": "Musculo-skeletal system",
    "N": "Nervous system",
    "P": "Antiparasitic products",
    "R": "Respiratory system",
    "S": "Sensory organs",
    "V": "Various",
}


def build_rxcui_to_atc(mrconso_path: Path) -> dict:
    print(f"Scanning {mrconso_path.name} ...")

    cui_to_rxcui = {}
    cui_to_atc   = {}
    l2_name_map  = {}   # "A10" → "Drugs used in diabetes"  (built from 108 L2 rows)

    rxnorm_hits = atc_hits = total = 0

    with open(mrconso_path, encoding="utf-8") as f:
        for line in f:
            total += 1
            parts = line.rstrip("\n").split("|")
            if len(parts) < 14:
                continue

            cui = parts[COL_CUI]
            sab = parts[COL_SAB]

            if sab == "RXNORM":
                scui = parts[COL_SCUI].strip()
                if scui:
                    cui_to_rxcui[cui] = scui
                    rxnorm_hits += 1

            elif sab == "ATC":
                code = parts[COL_STR].strip()
                name = parts[COL_NAME].strip() if len(parts) > COL_NAME else ""

                if not code:
                    continue

                ln = len(code)
                atc_hits += 1

                if cui not in cui_to_atc:
                    cui_to_atc[cui] = {}
                entry = cui_to_atc[cui]

                if ln == 1:
                    entry["atc_l1_code"] = code
                    entry["atc_l1_name"] = ATC_L1_NAMES.get(code, name)

                elif ln == 3:
                    entry["atc_l2_code"] = code
                    entry["atc_l2_name"] = name.title()
                    entry.setdefault("atc_l1_code", code[0])
                    entry.setdefault("atc_l1_name", ATC_L1_NAMES.get(code[0], ""))
                    # Also add to global L2 lookup for use with L5-derived codes
                    if name:
                        l2_name_map[code] = name.title()

                elif ln == 7:
                    entry.setdefault("atc_l1_code", code[0])
                    entry.setdefault("atc_l1_name", ATC_L1_NAMES.get(code[0], ""))
                    entry.setdefault("atc_l2_code", code[:3])
                    entry["atc_l5_code"] = code

            if total % 1_000_000 == 0:
                print(f"  {total:,} lines ...")

    print(f"  RXNORM atoms : {rxnorm_hits:,}")
    print(f"  ATC atoms    : {atc_hits:,}")
    print(f"  L2 names     : {len(l2_name_map):,}")

    # Join on shared CUI
    result = {}
    for cui, rxcui in cui_to_rxcui.items():
        if cui in cui_to_atc:
            atc = cui_to_atc[cui]
            if not atc.get("atc_l1_code"):
                continue

            # Fill L2 name from global lookup if missing (common for L5-derived L2 codes)
            if atc.get("atc_l2_code") and not atc.get("atc_l2_name"):
                atc["atc_l2_name"] = l2_name_map.get(atc["atc_l2_code"], "")

            result[rxcui] = atc

    print(f"  Joined       : {len(result):,} rxcui→ATC mappings")

    # Coverage check
    with_l2_name = sum(1 for v in result.values() if v.get("atc_l2_name"))
    print(f"  With L2 name : {with_l2_name:,} / {len(result):,}")

    return result, l2_name_map


def main():
    result, l2_name_map = build_rxcui_to_atc(MRCONSO)

    with open(OUTPUT_JSON, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nOutput: {OUTPUT_JSON}  ({OUTPUT_JSON.stat().st_size / 1e6:.1f} MB)")

    # L1 distribution
    l1 = Counter()
    for atc in result.values():
        l1[f"{atc.get('atc_l1_code')} — {atc.get('atc_l1_name')}"] += 1

    print("\nATC L1 distribution:")
    for cat, count in sorted(l1.items()):
        print(f"  {cat}: {count:,}")

    # L2 preview
    print("\nSample L2 categories (first 10):")
    for code, name in sorted(l2_name_map.items())[:10]:
        print(f"  {code}: {name}")


if __name__ == "__main__":
    main()
