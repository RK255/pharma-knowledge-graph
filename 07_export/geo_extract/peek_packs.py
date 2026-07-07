#!/usr/bin/env python3
"""
peek_packs.py — print GPCK / BPCK names found in an extraction JSONL
Usage: python3 peek_packs.py <path/to/full_geo_extraction_v23.jsonl>
"""
import json, re, sys
from pathlib import Path

RAW_BPCK = re.compile(r'^\{.+\}\s*Pack\s*\[.+\]\s*$', re.DOTALL)  # unformatted
FMT_BPCK = re.compile(r'^[^\{].+\{.+\}\s*Pack\s*$',   re.DOTALL)  # brand at front
GPCK     = re.compile(r'^\{.+\}\s*Pack\s*$',           re.DOTALL)

path = Path(sys.argv[1])
seen = set()
raw_bpck, fmt_bpck, gpck = [], [], []

def walk(obj):
    if isinstance(obj, str):
        s = obj.strip()
        if s and s not in seen:
            seen.add(s)
            if   RAW_BPCK.match(s): raw_bpck.append(s)
            elif FMT_BPCK.match(s): fmt_bpck.append(s)
            elif GPCK.match(s):     gpck.append(s)
    elif isinstance(obj, dict):
        for v in obj.values(): walk(v)
    elif isinstance(obj, list):
        for i in obj: walk(i)

for line in path.open():
    try: walk(json.loads(line))
    except: pass

for label, items in [
    ('GPCK',                    gpck),
    ('BPCK — formatted ✅',    fmt_bpck),
    ('BPCK — raw/unformatted ❌', raw_bpck),
]:
    print(f"\n── {label} ({len(items)}) " + '─' * 40)
    for s in items[:20]:
        print(f"  {s[:110]}")
    if len(items) > 20:
        print(f"  … {len(items) - 20} more")
