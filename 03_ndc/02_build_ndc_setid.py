#!/usr/bin/env python3
"""
NDC to Set ID Mapping Builder — v2.3
====================================
Fixes v2.2 regression: deduplication guard was too aggressive.
Same NDC11 can appear under multiple RXCUIs in RXNSAT. The old guard
skipped any NDC already in the dict, causing matched entries to be
blocked by earlier no_mthspl/multi_miss entries for the same NDC11.

Fix: only skip if the existing entry already has has_spl=True.
     A has_spl=False entry is always upgradeable if a better RXCUI
     for the same NDC11 appears later in the file.

Counters are computed from the final dict after Pass 2 (not during)
to avoid double-counting across duplicate NDC rows.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR
RAW_DATA_DIR  = BASE_DIR / "data" / "raw_data"
EXTRACTED_DIR = RAW_DATA_DIR / "extracted_rrf"

# Change MTHSPL_ATTRS to add ANDA and BLA:
MTHSPL_ATTRS = {
    "SPL_SET_ID", "DM_SPL_ID", "LABELER", "MARKETING_STATUS",
    "MARKETING_CATEGORY", "MARKETING_EFFECTIVE_TIME_LOW",
    "NDA", "ANDA", "BLA",                  # ← add ANDA, BLA
    "COLOR", "COLORTEXT", "SHAPE", "SIZE",
    "IMPRINT_CODE", "SCORE", "LABEL_TYPE",
    "NDC",
}

# In the entry dict, change approval_number line from:
# "approval_number":    block.get("nda"),
# to:
# "approval_number":    block.get("nda") or block.get("anda") or block.get("bla"),

APPROVAL_TYPE_MAP = {
    "NDA":                                      "NDA",
    "ANDA":                                     "ANDA",
    "BLA":                                      "BLA",
    "NDA authorized generic":                   "NDA_AG",
    "OTC Monograph Drug":                       "OTC_MONOGRAPH",
    "OTC monograph not final":                  "OTC_MONOGRAPH",
    "OTC monograph final":                      "OTC_MONOGRAPH",
    "NADA":                                     "NADA",
    "ANADA":                                    "ANADA",
    "Dietary Supplement":                       "DIETARY_SUPPLEMENT",
    "Unapproved drug other":                    "UNAPPROVED",
    "Unapproved drug for use in drug shortage": "UNAPPROVED",
    "Export only":                              "EXPORT_ONLY",
    "Exempt device":                            "EXEMPT_DEVICE",
}

def find_rxnsat(source_date: str = None) -> Path:
    candidates = sorted(EXTRACTED_DIR.iterdir(), reverse=True)
    for subdir in candidates:
        path = subdir / "rrf" / "RXNSAT.RRF"
        if path.exists():
            if source_date is None or source_date in subdir.name:
                return path
    raise FileNotFoundError("No RXNSAT.RRF found")


def ndc11_to_542(raw: str) -> str | None:
    """Convert 11-digit no-hyphen NDC to 5-4-2 hyphenated."""
    d = raw.strip().replace("-", "").replace(" ", "")
    if len(d) == 11:
        return f"{d[:5]}-{d[5:9]}-{d[9:]}"
    return None


def labeler_prefix_from_hyphenated(ndc_or_metaui: str) -> str | None:
    """
    Extract 5-digit labeler prefix from a hyphenated NDC or METAUI.
    Takes the segment before the first hyphen and zero-pads to 5 digits.

      "0363-0268-32"  → "00363"
      "12745-202-03"  → "12745"
      "0395-1113-94"  → "00395"
      "0363-0268"     → "00363"
    """
    if not ndc_or_metaui:
        return None
    parts = ndc_or_metaui.split("-")
    labeler_seg = parts[0]
    if not labeler_seg.isdigit():
        return None
    return labeler_seg.zfill(5)


def match_block_by_labeler(blocks: list, labeler_prefix: str) -> dict | None:
    """
    Find the MTHSPL block whose labeler matches the given 5-digit prefix.
    Tries METAUI first, then falls back to stored ATN=NDC attribute.
    """
    for b in blocks:
        if labeler_prefix_from_hyphenated(b.get("metaui", "")) == labeler_prefix:
            return b
    for b in blocks:
        if labeler_prefix_from_hyphenated(b.get("ndc", "")) == labeler_prefix:
            return b
    return None


def build_mapping(rxnsat_file: Path) -> dict:
    print(f"  Streaming {rxnsat_file} ...")

    # ------------------------------------------------------------------ #
    # Pass 1: collect MTHSPL blocks per RXCUI                            #
    # ------------------------------------------------------------------ #
    rxcui_blocks = defaultdict(list)

    with open(rxnsat_file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) < 11:
                continue
            if p[9] != "MTHSPL" or p[11] == "Y" or not p[10]:
                continue
            if p[8] not in MTHSPL_ATTRS:
                continue

            rxcui  = p[0]
            metaui = p[5]
            atn    = p[8]
            atv    = p[10]

            block = next(
                (b for b in rxcui_blocks[rxcui] if b["metaui"] == metaui),
                None
            )
            if block is None:
                block = {"metaui": metaui}
                rxcui_blocks[rxcui].append(block)

            if atn == "SPL_SET_ID":
                block["set_id"] = atv
            else:
                block[atn.lower()] = atv

    # Keep only blocks that have a set_id
    for rxcui in list(rxcui_blocks):
        rxcui_blocks[rxcui] = [b for b in rxcui_blocks[rxcui] if "set_id" in b]
        if not rxcui_blocks[rxcui]:
            del rxcui_blocks[rxcui]

    print(f"  Pass 1: {len(rxcui_blocks):,} RXCUIs with MTHSPL set_ids")

    # ------------------------------------------------------------------ #
    # Pass 2: ALL RXNORM NDC11s → emit entry for every unique NDC        #
    #                                                                      #
    # Dedup rule: only skip if we already have has_spl=True.              #
    # A has_spl=False entry is always upgradeable if a better RXCUI       #
    # for the same NDC11 appears later in the file.                       #
    # ------------------------------------------------------------------ #
    ndc_to_setid = {}

    with open(rxnsat_file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) < 11:
                continue
            if p[9] != "RXNORM" or p[8] != "NDC" or not p[10]:
                continue

            rxcui  = p[0]
            ndc542 = ndc11_to_542(p[10])
            if not ndc542:
                continue

            # Skip only if already matched — a False entry can be upgraded
            existing = ndc_to_setid.get(ndc542)
            if existing and existing.get("has_spl"):
                continue

            blocks = rxcui_blocks.get(rxcui)

            # --- Case 1: no MTHSPL data for this RXCUI ---
            if not blocks:
                if not existing:   # don't overwrite a multi_miss with no_mthspl
                    ndc_to_setid[ndc542] = {
                        "has_spl":     False,
                        "rxcui":       rxcui,
                        "miss_reason": "no_mthspl",
                    }
                continue

            # --- Case 2: single block — unambiguous ---
            if len(blocks) == 1:
                block = blocks[0]

            # --- Case 3: multi-labeler — disambiguate by labeler prefix ---
            else:
                labeler_prefix = ndc542[:5]
                block = match_block_by_labeler(blocks, labeler_prefix)
                if block is None:
                    if not existing:   # don't overwrite a no_mthspl with multi_miss
                        ndc_to_setid[ndc542] = {
                            "has_spl":     False,
                            "rxcui":       rxcui,
                            "miss_reason": "multi_labeler_miss",
                        }
                    continue

            # --- Matched: emit full entry (always overwrites any False entry) ---
            raw_category = block.get("marketing_category")
            entry = {
                "has_spl":            True,
                "rxcui":              rxcui,
                "set_id":             block.get("set_id"),
                "dm_spl_id":          block.get("dm_spl_id"),
                "labeler":            block.get("labeler"),
                "marketing_status":   block.get("marketing_status"),
                "marketing_category": raw_category,
                "approval_type":      APPROVAL_TYPE_MAP.get(raw_category) if raw_category else None,
                "marketing_start":    block.get("marketing_effective_time_low"),
                "approval_number":    block.get("nda") or block.get("anda") or block.get("bla"),
                "label_type":         block.get("label_type"),
                "color":              block.get("color"),
                "colortext":          block.get("colortext"),
                "shape":              block.get("shape"),
                "size":               block.get("size"),
                "imprint":            block.get("imprint_code"),
                "score":              block.get("score"),
            }
            ndc_to_setid[ndc542] = {k: v for k, v in entry.items() if v is not None}

    # Compute final stats from dict (correct regardless of duplicate NDC rows)
    n_mapped     = sum(1 for v in ndc_to_setid.values() if v.get("has_spl"))
    n_no_mthspl  = sum(1 for v in ndc_to_setid.values() if v.get("miss_reason") == "no_mthspl")
    n_multi_miss = sum(1 for v in ndc_to_setid.values() if v.get("miss_reason") == "multi_labeler_miss")

    print(f"  Total RxNorm NDCs:      {len(ndc_to_setid):,}")
    print(f"    → has set_id:         {n_mapped:,}")
    print(f"    → no_mthspl:          {n_no_mthspl:,}")
    print(f"    → multi_labeler_miss: {n_multi_miss:,}")
    return ndc_to_setid


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-date")
    args = parser.parse_args()

    print("=" * 70)
    print("NDC TO SET ID MAPPING BUILDER v2.3")
    print("=" * 70)

    rxnsat_file = find_rxnsat(args.source_date)
    print(f"\nUsing: {rxnsat_file}\n")

    ndc_to_setid = build_mapping(rxnsat_file)

    output_file = RAW_DATA_DIR / "ndc_to_setid.json"
    out = {
        "ndc_to_setid": ndc_to_setid,
        "stats": {
            "total_ndc_count":  len(ndc_to_setid),
            "mapped_count":     sum(1 for v in ndc_to_setid.values() if v.get("has_spl")),
            "no_mthspl_count":  sum(1 for v in ndc_to_setid.values() if v.get("miss_reason") == "no_mthspl"),
            "multi_miss_count": sum(1 for v in ndc_to_setid.values() if v.get("miss_reason") == "multi_labeler_miss"),
            "source":           str(rxnsat_file),
            "method":           "rxnorm_ndc11_linked_to_mthspl_block_v2.3",
            "created":          datetime.now().isoformat(),
        }
    }
    with open(output_file, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    print(f"\n✅ Saved {len(ndc_to_setid):,} entries to {output_file}")


if __name__ == "__main__":
    main()
