#!/usr/bin/env python3
"""
Complete NDC to Set ID Mapping Report

Generates a comprehensive list of all NDCs, their RxCUI codes, 
and associated SPL Set IDs with coverage statistics.

Output includes:
- Total NDCs in the system
- NDCs with Set IDs
- Unique Set IDs
- RxCUI coverage
- Complete mapping file with all NDCs and their associated data
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"

# Property IDs
NDC_CODE_PROP = "a126ca530c8e48d5b88882c734c38935"
RXCUI_PROP = "c6f36f8a8e22546ea7618ac008d2f91e"
FDA_SET_ID_PROP = "78d0af3db973513e8be0cb76afa5e9c4"

def normalize_ndc(ndc: str) -> str:
    """Normalize NDC to 11-digit format."""
    return ndc.replace("-", "").zfill(11)

def load_ndc_bridge() -> dict:
    """Load NDC → RxCUI mappings from ndc_to_rxcui.json."""
    print("Loading NDC to RxCui mappings...")
    with open(RAW_DATA_DIR / "ndc_to_rxcui.json", 'r') as f:
        ndc_data = json.load(f)
    
    ndc_to_rxcui = ndc_data["ndc_to_rxcui"]
    rxcui_to_ndcs = ndc_data["rxcui_to_ndcs"]
    
    print(f"  Loaded {len(ndc_to_rxcui):,} NDCs")
    print(f"  Loaded {len(rxcui_to_ndcs):,} RxCUIs")
    return ndc_to_rxcui, rxcui_to_ndcs

def load_rxcui_to_setid() -> dict:
    """Load RxCUI → Set ID mappings from RXNSAT data."""
    print("Loading RxCUI to Set ID mappings...")
    
    rxcui_to_setids = defaultdict(list)
    
    # Try to load from the previously generated RXNSAT data
    try:
        with open(RAW_DATA_DIR / "rxnorm_rxcui_to_setid.json", 'r') as f:
            data = json.load(f)
            for rxcui, setids in data.items():
                # Convert to list if it's not already
                if isinstance(setids, list):
                    rxcui_to_setids[rxcui] = setids
                else:
                    rxcui_to_setids[rxcui] = [setids]
        
        print(f"  Loaded {len(rxcui_to_setids):,} RxCUIs with Set IDs")
        return dict(rxcui_to_setids)
    except FileNotFoundError:
        print("  No existing RxCUI to Set ID mapping found")
        return {}

def load_pi_documents() -> dict:
    """Load Set ID → NDCs from DailyMed documents."""
    print("Loading DailyMed documents...")
    set_id_to_ndcs = defaultdict(list)
    
    with open(DATA_DIR / "dailymed_documents.json", 'r') as f:
        docs = json.load(f)
    
    for doc in docs:
        set_id = doc.get("fda_set_id")
        ndcs = doc.get("ndc_codes", [])
        if set_id and ndcs:
            set_id_to_ndcs[set_id] = ndcs
    
    print(f"  Loaded {len(set_id_to_ndcs):,} Set IDs with NDCs")
    return dict(set_id_to_ndcs)

def load_ndc_bridge_entities() -> dict:
    """Load NDC bridge entities to get entity IDs and RxCUIs."""
    print("Loading NDC bridge entities...")
    ndc_entities = {}
    
    with open(DATA_DIR / "ndc_bridge_entities.jsonl", 'r') as f:
        for line in f:
            e = json.loads(line)
            ndc_code = e.get("name", "")
            entity_id = e["id"]
            
            # Get RxCUI if available
            rxcui = None
            for v in e.get("values", []):
                if v.get("property") == RXCUI_PROP:
                    rxcui = v.get("value")
                    break
            
            if ndc_code:
                ndc_entities[ndc_code] = {
                    "entity_id": entity_id,
                    "rxcui": rxcui
                }
    
    print(f"  Loaded {len(ndc_entities):,} NDC entities")
    return ndc_entities

def generate_complete_mapping(ndc_to_rxcui: dict, rxcui_to_ndcs: dict, 
                              rxcui_to_setids: dict, set_id_to_ndcs: dict,
                              ndc_entities: dict) -> dict:
    """Generate the complete NDC → RxCUI → Set ID mapping."""
    print("\nGenerating complete mapping...")
    
    # Build comprehensive mapping
    mapping = {
        "ndc_summary": {
            "total_ndcs": 0,
            "ndcs_with_rxcui": 0,
            "ndcs_with_setid": 0,
            "rxcui_count": len(rxcui_to_ndcs),
            "unique_set_ids": 0
        },
        "ndc_list": [],
        "set_id_summary": {
            "total_set_ids": 0,
            "set_ids_with_ndcs": 0,
            "avg_ndcs_per_set_id": 0
        },
        "set_id_list": []
    }
    
    # OPTIMIZATION: Build a reverse lookup for DailyMed NDCs
    print("  Building DailyMed NDC index...")
    dailymed_ndc_to_setid = {}
    for set_id, ndcs in set_id_to_ndcs.items():
        for ndc in ndcs:
            # Store all variants for matching
            ndc_norm = normalize_ndc(ndc)
            dailymed_ndc_to_setid[ndc_norm] = set_id
            dailymed_ndc_to_setid[ndc.replace("-", "")] = set_id
            dailymed_ndc_to_setid[ndc] = set_id
    
    print(f"  Indexed {len(dailymed_ndc_to_setid):,} DailyMed NDC variants")
    
    # Process NDCs
    ndc_to_setid = {}
    set_id_to_ndc_list = defaultdict(set)
    set_ids_seen = set()
    
    print("  Processing NDCs...")
    processed = 0
    
    for ndc_code, rxcui in ndc_to_rxcui.items():
        ndc_normalized = normalize_ndc(ndc_code)
        
        ndc_info = {
            "ndc_original": ndc_code,
            "ndc_normalized": ndc_normalized,
            "rxcui": rxcui,
            "set_id": None,
            "in_daily_med": False
        }
        
        mapping["ndc_summary"]["total_ndcs"] += 1
        
        if rxcui:
            ndc_info["has_rxcui"] = True
            mapping["ndc_summary"]["ndcs_with_rxcui"] += 1
            
            # Get Set ID from RxCUI mapping
            set_ids = rxcui_to_setids.get(str(rxcui), [])
            if set_ids:
                set_id = set_ids[0]
                ndc_to_setid[ndc_normalized] = set_id
                ndc_info["set_id"] = set_id
                set_ids_seen.add(set_id)
                set_id_to_ndc_list[set_id].add(ndc_normalized)
                mapping["ndc_summary"]["ndcs_with_setid"] += 1
        
        # OPTIMIZATION: Check DailyMed using pre-built index instead of nested loop
        daily_med_set_id = dailymed_ndc_to_setid.get(ndc_normalized)
        if daily_med_set_id:
            ndc_info["in_daily_med"] = True
            ndc_info["daily_med_set_id"] = daily_med_set_id
        
        mapping["ndc_list"].append(ndc_info)
        
        processed += 1
        if processed % 50000 == 0:
            print(f"    Processed {processed:,}/{mapping['ndc_summary']['total_ndcs']:,} NDCs...")
    
    # Calculate Set ID summary
    mapping["ndc_summary"]["unique_set_ids"] = len(set_ids_seen)
    mapping["set_id_summary"]["total_set_ids"] = len(set_id_to_ndcs)
    mapping["set_id_summary"]["set_ids_with_ndcs"] = len(set_id_to_ndc_list)
    
    if set_id_to_ndc_list:
        total_ndcs_in_sets = sum(len(ndcs) for ndcs in set_id_to_ndc_list.values())
        mapping["set_id_summary"]["avg_ndcs_per_set_id"] = total_ndcs_in_sets / len(set_id_to_ndc_list)
    
    # Build Set ID list
    print("  Building Set ID list...")
    for set_id, ndcs in set_id_to_ndc_list.items():
        set_info = {
            "set_id": set_id,
            "ndc_count": len(ndcs),
            "ndc_codes": sorted(list(ndcs)),
            "rxcuis": set()
        }
        
        # Get RxCUIs for this Set ID
        for ndc in ndcs:
            rxcui = ndc_to_rxcui.get(ndc)
            if rxcui:
                set_info["rxcuis"].add(rxcui)
        
        set_info["rxcuis"] = list(set_info["rxcuis"])
        mapping["set_id_list"].append(set_info)
    
    # Sort Set ID list by NDC count (descending)
    mapping["set_id_list"].sort(key=lambda x: x["ndc_count"], reverse=True)
    
    # Sort NDC list by original NDC code
    mapping["ndc_list"].sort(key=lambda x: x["ndc_original"])
    
    return mapping

def main():
    print("=" * 80)
    print("COMPLETE NDC TO SET ID MAPPING REPORT")
    print("=" * 80)
    
    # Load data
    ndc_to_rxcui, rxcui_to_ndcs = load_ndc_bridge()
    rxcui_to_setids = load_rxcui_to_setid()
    set_id_to_ndcs = load_pi_documents()
    ndc_entities = load_ndc_bridge_entities()
    
    # Generate mapping
    mapping = generate_complete_mapping(
        ndc_to_rxcui, rxcui_to_ndcs, 
        rxcui_to_setids, set_id_to_ndcs,
        ndc_entities
    )
    
    # Print summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    
    ndc_summary = mapping["ndc_summary"]
    set_id_summary = mapping["set_id_summary"]
    
    print(f"\nNDC Summary:")
    print(f"  Total NDCs: {ndc_summary['total_ndcs']:,}")
    print(f"  NDCs with RxCUI: {ndc_summary['ndcs_with_rxcui']:,} ({ndc_summary['ndcs_with_rxcui']/ndc_summary['total_ndcs']*100 if ndc_summary['total_ndcs'] > 0 else 0:.1f}%)")
    print(f"  NDCs with Set ID: {ndc_summary['ndcs_with_setid']:,} ({ndc_summary['ndcs_with_setid']/ndc_summary['total_ndcs']*100 if ndc_summary['total_ndcs'] > 0 else 0:.1f}%)")
    print(f"  Unique RxCUIs: {ndc_summary['rxcui_count']:,}")
    print(f"  Unique Set IDs: {ndc_summary['unique_set_ids']:,}")
    
    print(f"\nSet ID Summary:")
    print(f"  Total Set IDs in DailyMed: {set_id_summary['total_set_ids']:,}")
    print(f"  Set IDs with NDCs: {set_id_summary['set_ids_with_ndcs']:,}")
    print(f"  Average NDCs per Set ID: {set_id_summary['avg_ndcs_per_set_id']:.2f}")
    
    # Print sample data
    print(f"\nSample NDCs (first 10):")
    for ndc_info in mapping["ndc_list"][:10]:
        print(f"  NDC: {ndc_info['ndc_original']} (normalized: {ndc_info['ndc_normalized']})")
        print(f"    RxCUI: {ndc_info['rxcui']}")
        print(f"    Set ID: {ndc_info['set_id']}")
        print(f"    In DailyMed: {ndc_info['in_daily_med']}")
    
    print(f"\nSample Set IDs (top 10 by NDC count):")
    for set_info in mapping["set_id_list"][:10]:
        print(f"  Set ID: {set_info['set_id']}")
        print(f"    NDC Count: {set_info['ndc_count']:,}")
        print(f"    RxCUIs: {', '.join(str(r) for r in set_info['rxcuis'][:3])}{'...' if len(set_info['rxcuis']) > 3 else ''}")
        print(f"    Sample NDCs: {', '.join(set_info['ndc_codes'][:3])}{'...' if len(set_info['ndc_codes']) > 3 else ''}")
    
    # Save complete mapping
    output_file = DATA_DIR / "complete_ndc_setid_mapping.json"
    with open(output_file, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "ndc_summary": ndc_summary,
                "set_id_summary": set_id_summary
            },
            "mapping": mapping
        }, f, indent=2)
    
    print(f"\n✅ Complete mapping saved to {output_file}")
    
    # Save simplified CSV for easy viewing
    csv_file = DATA_DIR / "complete_ndc_setid_mapping.csv"
    with open(csv_file, 'w') as f:
        f.write("NDC_Original,NDC_Normalized,RxCUI,Set_ID,In_DailyMed\n")
        for ndc_info in mapping["ndc_list"]:
            f.write(f"{ndc_info['ndc_original']},{ndc_info['ndc_normalized']},{ndc_info['rxcui']},{ndc_info['set_id']},{ndc_info['in_daily_med']}\n")
    
    print(f"✅ CSV export saved to {csv_file}")

if __name__ == "__main__":
    main()
