#!/usr/bin/env python3
"""
Map every set_id seen in the output to its labeler name via RXNSAT.
Also flags the known-wrong GPCK set_id.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR

RXNSAT = str(
    BASE_DIR / "data/raw_data/"
    "extracted_rrf/RxNorm04062026_extracted/rrf/RXNSAT.RRF"
)
JSONL = str(
    BASE_DIR / "scripts/production/"
    "geo-ingestor/data_to_publish/full_geo_extraction_v23.jsonl"
)

TARGET_MIN = "214559"

# ── 1. Collect all set_ids seen for MIN 214559's packs ───────────────────────
def find_min(obj):
    for item in obj.get("connections", {}).get("min", []):
        if item.get("rxcui") == TARGET_MIN:
            return item
    return None

pack_setids = {}   # rxcui → {set_id, name, tty}
missing_ndcs = []  # (pack_rxcui, pack_name, ndc) tuples with no set_id

with open(JSONL) as f:
    for line in f:
        obj = json.loads(line)
        min_obj = find_min(obj)
        if not min_obj:
            continue
        for scd in min_obj.get("combo_scds", []):
            for tty in ("gpck", "bpck"):
                for pack in scd.get(tty, []):
                    prxcui = pack["rxcui"]
                    for n in pack.get("ndcs", []):
                        sid = n.get("spl_set_id")
                        if sid:
                            pack_setids[prxcui] = {
                                "set_id": sid,
                                "name":   pack.get("name","?")[:60],
                                "tty":    tty.upper(),
                            }
                        else:
                            missing_ndcs.append((prxcui, pack.get("name","?")[:50], n.get("ndc","?")))
        break

all_setids = {v["set_id"] for v in pack_setids.values()}
print(f"Collected {len(all_setids)} unique set_ids to resolve\n")

# ── 2. Scan RXNSAT for SPL_SET_ID + labeler name ─────────────────────────────
# RXNSAT cols: RXCUI|LUI|SUI|RXAUI|STYPE|CODE|ATUI|SATUI|ATN|SAB|ATV|SUPPRESS|CVF
ATN_COL = 8
ATV_COL = 10
SAB_COL = 9

setid_to_labeler = {}
setid_to_orgname = {}

with open(RXNSAT, encoding="utf-8") as f:
    for line in f:
        p = line.rstrip("\n").split("|")
        if len(p) < 11:
            continue
        if p[SAB_COL] != "MTHSPL":
            continue
        atv = p[ATV_COL]
        atn = p[ATN_COL]
        if atn == "SPL_SET_ID" and atv in all_setids:
            # Look for labeler on same RXCUI block — we'll join by RXCUI
            pass   # handled below via rxcui lookup

# Simpler approach: build setid → labeler from RXNSAT labeler blocks
rxcui_setid_labeler = defaultdict(dict)  # rxcui → {set_id → labeler}

with open(RXNSAT, encoding="utf-8") as f:
    current_rxcui  = None
    current_setid  = None
    current_dm_spl = None

    for line in f:
        p = line.rstrip("\n").split("|")
        if len(p) < 11 or p[SAB_COL] != "MTHSPL":
            continue
        rxcui = p[0]
        atn   = p[ATN_COL]
        atv   = p[ATV_COL]

        if atn == "SPL_SET_ID":
            current_rxcui = rxcui
            current_setid = atv
            current_dm_spl = p[5]   # CODE = DM_SPL_ID

        if atn == "LABELER" and current_rxcui == rxcui and current_setid in all_setids:
            rxcui_setid_labeler[current_rxcui][current_setid] = atv

# Build flat setid → labeler
setid_to_labeler = {}
for rxcui, mapping in rxcui_setid_labeler.items():
    for sid, labeler in mapping.items():
        setid_to_labeler[sid] = labeler

# ── 3. Print the mapping ─────────────────────────────────────────────────────
print(f"{'RXCUI':<10} {'TTY':<5} {'SET_ID':<38} {'LABELER':<35} NAME")
print("-" * 130)

GPCK_WRONG_SETID_PREFIX = "2385591b"

for rxcui, info in sorted(pack_setids.items(), key=lambda x: x[1]["tty"]):
    sid     = info["set_id"]
    labeler = setid_to_labeler.get(sid, "not found in RXNSAT")
    flag    = ""
    if sid.startswith(GPCK_WRONG_SETID_PREFIX) and info["tty"] == "GPCK":
        flag = "  ← ❌ Bug 3: PD-Rx set_id on GPCK"
    print(f"{rxcui:<10} {info['tty']:<5} {sid:<38} {labeler:<35} {info['name']}{flag}")

if missing_ndcs:
    print(f"\nNDCs with MISSING set_id:")
    for prxcui, pname, ndc in missing_ndcs:
        print(f"  {prxcui:<10} {ndc:<20} {pname}")
