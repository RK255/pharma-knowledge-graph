#!/usr/bin/env python3
"""
Dry-run: DailyMed-first NDC→set_id coverage check.
Simulates the new approach without modifying any files.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DIR  = BASE_DIR / "data" / "raw_data"

DAILYMED_DOCS = DATA_DIR / "dailymed_documents.json"
NDC_TO_SETID  = RAW_DIR  / "ndc_to_setid.json"

# From the previous bug investigation
BPCK_SETID = "2385591b-70ee-0577-e063-6394a90a9357"   # wrong — branded pack
GPCK_SETID = "a3ce752d-58df-363d-e053-2a95a90a5411"   # correct — generic pack


def norm(ndc: str) -> str:
    """Strip hyphens, zero-pad to 11 digits."""
    return ndc.replace("-", "").strip().zfill(11)


# ── 1. Build DailyMed ndc→set_id ──────────────────────────────────────────────
print("Loading dailymed_documents.json...")
docs = json.load(open(DAILYMED_DOCS))

dm_map = {}          # norm_ndc → fda_set_id
dm_conflicts = {}    # norm_ndc → list of set_ids (if more than one doc claims it)

for doc in docs:
    set_id   = doc.get("fda_set_id", "")
    ndc_list = doc.get("ndc_codes", [])
    if not set_id:
        continue
    for raw in ndc_list:
        n = norm(raw)
        if n in dm_map:
            if dm_map[n] != set_id:
                dm_conflicts.setdefault(n, {dm_map[n]}).add(set_id)
        else:
            dm_map[n] = set_id

print(f"  DailyMed covers     : {len(dm_map):,} unique NDCs")
print(f"  Multi-label NDCs    : {len(dm_conflicts):,}  (same NDC in >1 document)")


# ── 2. Load current ndc_to_setid.json ─────────────────────────────────────────
current_raw = json.load(open(NDC_TO_SETID)).get("ndc_to_setid", {})
# normalise existing keys for fair comparison
current     = {norm(k): v for k, v in current_raw.items()}
print(f"\n  Current ndc_to_setid: {len(current):,} NDCs")


# ── 3. Coverage stats ─────────────────────────────────────────────────────────
in_dm   = sum(1 for n in current if n in dm_map)
not_dm  = len(current) - in_dm
pct     = 100 * in_dm / max(len(current), 1)

agrees  = sum(1 for n, s in current.items() if dm_map.get(n) == s)
differs = sum(1 for n, s in current.items() if n in dm_map and dm_map[n] != s)

print(f"\n{'='*60}")
print(f"  COVERAGE SUMMARY")
print(f"{'='*60}")
print(f"  In DailyMed         : {in_dm:,} ({pct:.1f}%)")
print(f"  Not in DailyMed     : {not_dm:,}  ← RXNSAT fallback covers these")
print(f"  DailyMed agrees     : {agrees:,}")
print(f"  DailyMed disagrees  : {differs:,}  ← these are the wrong set_ids")


# ── 4. Birth control NDC spot-check ───────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  BIRTH CONTROL SET ID SPOT CHECK")
print(f"{'='*60}")
print(f"  BPCK set_id (WRONG)  : {BPCK_SETID}")
print(f"  GPCK set_id (CORRECT): {GPCK_SETID}")

# NDCs currently pointing at the BPCK set_id (the broken ones)
bpck_ndcs = [n for n, s in current.items() if s == BPCK_SETID]
print(f"\n  NDCs currently mapped to BPCK set_id: {len(bpck_ndcs)}")
print(f"  {'NDC (norm)':14}  {'DailyMed says':44}  Outcome")
print(f"  {'-'*14}  {'-'*44}  -------")
for n in sorted(bpck_ndcs):
    dm_sid = dm_map.get(n)
    if dm_sid is None:
        outcome = "❌ not in DailyMed — falls back to RXNSAT"
    elif dm_sid == GPCK_SETID:
        outcome = "✅ FIXED → GPCK set_id"
    elif dm_sid == BPCK_SETID:
        outcome = "⚠️  DailyMed also says BPCK — investigate"
    else:
        outcome = f"⚠️  DailyMed says different: {dm_sid[:20]}"
    print(f"  {n:14}  {(dm_sid or 'N/A'):44}  {outcome}")

# NDCs DailyMed assigns to the GPCK set_id
gpck_in_dm = [n for n, s in dm_map.items() if s == GPCK_SETID]
print(f"\n  NDCs DailyMed maps to GPCK set_id: {len(gpck_in_dm)}")
for n in sorted(gpck_in_dm):
    cur = current.get(n, "not in current file")
    tag = "✅ already correct" if cur == GPCK_SETID else f"❌ currently: {cur}"
    print(f"  {n:14}  {tag}")

print(f"\n{'='*60}")
print("  No files were modified. This was a dry run.")
print(f"{'='*60}")
