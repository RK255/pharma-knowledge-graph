#!/usr/bin/env python3
"""
Query a specific drug and show the full output chain:
NDC → RxCUI → Set ID → Package Insert
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

def load_mappings():
    """Load all necessary mappings"""
    print("Loading mappings...")
    
    # Load NDC → Set ID mapping
    setid_file = RAW_DATA_DIR / "ndc_to_setid_final_v3.json"
    with open(setid_file, 'r') as f:
        setid_data = json.load(f)
    ndc_to_setid = setid_data['ndc_to_setid']
    print(f"  Loaded {len(ndc_to_setid):,} NDC → Set ID mappings")
    
    # Load NDC → RxCUI mapping
    rxcui_file = RAW_DATA_DIR / "ndc_to_rxcui.json"
    with open(rxcui_file, 'r') as f:
        rxcui_data = json.load(f)
    ndc_to_rxcui = rxcui_data['ndc_to_rxcui']
    print(f"  Loaded {len(ndc_to_rxcui):,} NDC → RxCUI mappings")
    
    # Load DailyMed documents
    dailymed_file = DATA_DIR / "dailymed_documents.json"
    with open(dailymed_file, 'r') as f:
        dailymed_docs = json.load(f)
    
    # Create Set ID → DailyMed doc mapping
    setid_to_dailymed = {}
    for doc in dailymed_docs:
        set_id = doc.get("fda_set_id")
        if set_id:
            setid_to_dailymed[set_id] = doc
    print(f"  Loaded {len(setid_to_dailymed):,} Set ID → DailyMed mappings")
    
    # Load RxNorm entities (for drug names)
    rxnorm_entities = {}
    rxnorm_file = DATA_DIR / "rxnorm_entities.jsonl"
    if Path(rxnorm_file).exists():
        with open(rxnorm_file, 'r') as f:
            for line in f:
                entity = json.loads(line)
                rxcui = None
                for val in entity.get('values', []):
                    if val.get('property') == 'c6f36f8a8e22546ea7618ac008d2f91e':  # RxCUI property
                        rxcui = val.get('value')
                        break
                if rxcui:
                    rxnorm_entities[str(rxcui)] = entity
        print(f"  Loaded {len(rxnorm_entities):,} RxNorm entities")
    
    return ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities

def get_drug_name(rxcui, rxnorm_entities):
    """Get drug name from RxNorm entity"""
    if str(rxcui) not in rxnorm_entities:
        return "Unknown"
    
    entity = rxnorm_entities[str(rxcui)]
    for val in entity.get('values', []):
        if val.get('property') == '5b451980-b6e7-4eb7-b3ba-7b6c961521b0':  # Name property
            return val.get('value')
    
    return "Unknown"

def query_by_ndc(ndc_to_query, ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities):
    """Query for a specific NDC and show full chain"""
    print("\n" + "=" * 80)
    print(f"QUERYING FOR NDC: {ndc_to_query}")
    print("=" * 80 + "\n")
    
    # Get RxCUI
    rxcui_val = ndc_to_rxcui.get(ndc_to_query)
    if not rxcui_val:
        print(f"❌ NDC {ndc_to_query} not found in NDC → RxCUI mapping")
        return
    
    # Get drug name
    drug_name = get_drug_name(rxcui_val, rxnorm_entities)
    
    print(f"Drug Name: {drug_name}")
    print(f"RxCUI: {rxcui_val}")
    
    # Get Set ID
    set_id = ndc_to_setid.get(ndc_to_query)
    print(f"\nNDC → Set ID:")
    if set_id:
        print(f"  Set ID: {set_id}")
        print(f"  Has Set ID: ✅ Yes")
    else:
        print(f"  Set ID: None")
        print(f"  Has Set ID: ❌ No")
        print(f"\nThis NDC does not have a Set ID mapping. Let's try to find another NDC for the same drug...")
        
        # Find other NDCs with the same RxCUI that have Set IDs
        print(f"\nOther NDCs with RxCUI {rxcui_val}:")
        other_ndcs = []
        for ndc, rxcui in ndc_to_rxcui.items():
            if str(rxcui) == str(rxcui_val) and ndc != ndc_to_query:
                other_ndcs.append(ndc)
        
        print(f"  Found {len(other_ndcs):,} other NDCs with this RxCUI")
        
        # Show first few with Set IDs
        for ndc in other_ndcs[:5]:
            other_setid = ndc_to_setid.get(ndc)
            if other_setid:
                print(f"    {ndc} -> Set ID: {other_setid} ✅")
        
        return
    
    # Get DailyMed document
    dailymed_doc = setid_to_dailymed.get(set_id)
    print(f"\nSet ID → Package Insert:")
    if dailymed_doc:
        print(f"  Package Insert Found: ✅ Yes")
        print(f"  Title: {dailymed_doc.get('title', 'N/A')}")
        print(f"  Set ID: {dailymed_doc.get('fda_set_id', 'N/A')}")
        print(f"  SPL Version: {dailymed_doc.get('spl_version', 'N/A')}")
        print(f"  Effective Date: {dailymed_doc.get('effective_time', 'N/A')}")
        
        # Show NDC codes in the PI
        ndcs_in_pi = dailymed_doc.get('ndc_codes', [])
        print(f"  NDCs in Package Insert: {len(ndcs_in_pi):,}")
        if len(ndcs_in_pi) <= 10:
            print(f"    {', '.join(ndcs_in_pi)}")
        else:
            print(f"    {', '.join(ndcs_in_pi[:10])} ... (and {len(ndcs_in_pi) - 10} more)")
        
        # Check which NDCs in the PI have Set IDs
        ndcs_with_setids = [ndc for ndc in ndcs_in_pi if ndc in ndc_to_setid]
        print(f"  NDCs in PI with Set IDs: {len(ndcs_with_setids):,} / {len(ndcs_in_pi):,}")
        
        if len(ndcs_with_setids) > 0:
            print(f"  Sample NDCs with Set IDs:")
            for ndc in ndcs_with_setids[:5]:
                print(f"    {ndc} -> {ndc_to_setid[ndc]}")
    else:
        print(f"  Package Insert Found: ❌ No")

def main():
    print("=" * 80)
    print("DRUG FULL CHAIN QUERY")
    print("=" * 80)
    
    # Load mappings
    ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities = load_mappings()
    
    # Query for specific NDCs - let's use some from the sample data we saw earlier
    test_ndcs = [
        "12745-0202-01",  # From earlier sample
        "12745-0202-02",  # From earlier sample
        "12745-0202-03",  # From earlier sample
        "59050-0268-00",  # From earlier sample
        "59779-0871-43",  # From earlier sample
    ]
    
    for ndc in test_ndcs:
        query_by_ndc(ndc, ndc_to_setid, ndc_to_rxcui, setid_to_dailymed, rxnorm_entities)
        print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    main()
