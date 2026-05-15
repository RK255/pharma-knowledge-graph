#!/usr/bin/env python3
"""
NDC Bridge to GRC-20 Converter v5.1 (FIXED - merges NDC formats)
===============================================================
Converts enhanced NDC-to-RxCUI mappings, creating ONE entity per NDC 
with multiple format properties (NDC11 hyphens, NDC11 no hyphens, NDC10).
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from pharma_schema import PharmaSchema, generate_uuid

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/raw_data"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

NDC_TO_RXCUI_FILE = f"{DATA_DIR}/ndc_to_rxcui.json"
RXNORM_ENTITIES_FILE = f"{OUTPUT_DIR}/rxnorm_entities.jsonl"


def load_rxnorm_entity_mapping(jsonl_file: str, schema: PharmaSchema):
    """Load RxCUI → entity_id mapping"""
    rxcui_to_entity = {}
    rxcui_property_id = schema.properties.get("rxcui")
    
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entity = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            entity_id = entity.get("id")
            if not entity_id:
                continue
            
            for value in entity.get("values", []):
                if value.get("property") == rxcui_property_id:
                    rxcui = value.get("value")
                    if rxcui:
                        rxcui_to_entity[rxcui] = entity_id
                    break
    
    return rxcui_to_entity


def main():
    print("=" * 70)
    print("NDC BRIDGE TO GRC-20 v5.1 (Fixed - Single Entity per NDC)")
    print("=" * 70)
    
    schema = PharmaSchema()
    
    # [1] Load enhanced NDC mapping
    print("\n[1/4] Loading enhanced NDC → RxCUI mapping...")
    
    if not os.path.exists(NDC_TO_RXCUI_FILE):
        print(f"  ERROR: {NDC_TO_RXCUI_FILE} not found")
        return
    
    with open(NDC_TO_RXCUI_FILE, 'r') as f:
        ndc_data = json.load(f)
    
    rxcui_to_ndc_entries = ndc_data.get('rxcui_to_ndc_entries', {})
    source_date = ndc_data.get('source_date', 'unknown')
    
    # Count total entries before merge
    total_entries = sum(len(entries) for entries in rxcui_to_ndc_entries.values())
    
    print(f"  Loaded {len(rxcui_to_ndc_entries):,} RxCUIs")
    print(f"  Total entries (before merge): {total_entries:,}")
    
    # [2] Load RxNorm entity mapping
    print("\n[2/4] Loading RxNorm entity mapping...")
    
    rxcui_to_entity = load_rxnorm_entity_mapping(RXNORM_ENTITIES_FILE, schema)
    print(f"  Loaded {len(rxcui_to_entity):,} RxCUI → entity mappings")
    
    # [3] Build GRC-20 entities - MERGE formats per NDC
    print("\n[3/4] Building GRC-20 entities (merging formats per NDC)...")
    
    entities = []
    relations = []
    
    # Get property IDs
    ndc11_hyphens_prop = schema.prop("ndc11_hyphens")
    ndc11_no_hyphens_prop = schema.prop("ndc11_no_hyphens")
    ndc10_hyphens_prop = schema.prop("ndc10_hyphens")
    ndc_code_prop = schema.prop("ndc_code")
    
    provenance_id = schema.provenance_entities.get("RxNorm")
    if not provenance_id:
        provenance = schema.create_provenance_entity("RxNorm", date_accessed=source_date)
        provenance_id = provenance["id"]
        entities.append(provenance)
    
    stats = {
        "unique_ndcs": 0,
        "entities_created": 0,
        "relations_created": 0,
        "multi_format_count": 0,
        "formats_merged": 0,
    }
    
    # Process each RxCUI
    for rxcui, ndc_entries in rxcui_to_ndc_entries.items():
        rx_entity_id = rxcui_to_entity.get(rxcui)
        
        # MERGE: Group entries by NDC11_hyphens
        merged_by_ndc = {}
        
        for entry in ndc_entries:
            ndc11 = entry['ndc11_hyphens']
            
            if ndc11 not in merged_by_ndc:
                # First time seeing this NDC - initialize
                merged_by_ndc[ndc11] = {
                    'ndc11_hyphens': ndc11,
                    'ndc11_no_hyphens': entry.get('ndc11_no_hyphens'),
                    'ndc10_hyphens': entry.get('ndc10_hyphens'),
                    'sources': set(entry.get('sources', [])),
                }
                stats['unique_ndcs'] += 1
            else:
                # Merge additional formats
                existing = merged_by_ndc[ndc11]
                if entry.get('ndc11_no_hyphens'):
                    existing['ndc11_no_hyphens'] = entry['ndc11_no_hyphens']
                if entry.get('ndc10_hyphens'):
                    existing['ndc10_hyphens'] = entry['ndc10_hyphens']
                existing['sources'].update(entry.get('sources', []))
                stats['formats_merged'] += 1
        
        # Create ONE entity per merged NDC
        for ndc11, merged in merged_by_ndc.items():
            entity_id = generate_uuid(seed=f"ndc_{ndc11}")
            
            # Use NDC11 with hyphens as name
            entity = schema.create_entity(
                entity_type="NDC",
                name=ndc11,
                entity_id=entity_id,
            )
            
            # Add ndc_code property (main format)
            entity["values"].append({
                "property": ndc_code_prop,
                "value": ndc11
            })
            
            # Add ndc11_hyphens property
            entity["values"].append({
                "property": ndc11_hyphens_prop,
                "value": ndc11
            })
            
            # Add ndc11_no_hyphens if available
            if merged.get('ndc11_no_hyphens'):
                entity["values"].append({
                    "property": ndc11_no_hyphens_prop,
                    "value": merged['ndc11_no_hyphens']
                })
            
            # Add ndc10_hyphens if available
            if merged.get('ndc10_hyphens'):
                entity["values"].append({
                    "property": ndc10_hyphens_prop,
                    "value": merged['ndc10_hyphens']
                })
                stats['multi_format_count'] += 1
            
            entities.append(entity)
            stats['entities_created'] += 1
            
            # Create relation to RxCUI
            if rx_entity_id:
                relation_id = generate_uuid(seed=f"ndc_maps_to_{ndc11}_{rxcui}")
                relation = schema.create_relation(
                    from_entity_id=entity_id,
                    relation_type="maps_to_rxcui",
                    to_entity_id=rx_entity_id,
                    relation_id=relation_id,
                )
                relations.append(relation)
                stats['relations_created'] += 1
            
            if stats['entities_created'] % 50000 == 0:
                print(f"  Processed {stats['entities_created']:,} NDCs...")
    
    # Add provenance relations
    for entity in entities:
        prov_rel = schema.add_provenance_relation(entity["id"], "RxNorm")
        relations.append(prov_rel)
    
    print(f"\n  Statistics:")
    print(f"    Unique NDCs (after merge): {stats['unique_ndcs']:,}")
    print(f"    Entities created: {stats['entities_created']:,}")
    print(f"    Relations created: {stats['relations_created']:,}")
    print(f"    Formats merged: {stats['formats_merged']:,}")
    print(f"    Multi-format entities: {stats['multi_format_count']:,}")
    
    # [4] Export
    print(f"\n[4/4] Exporting...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    entities_file = f"{OUTPUT_DIR}/ndc_bridge_entities.jsonl"
    with open(entities_file, 'w', encoding='utf-8') as f:
        for entity in entities:
            f.write(json.dumps(entity) + '\n')
    
    relations_file = f"{OUTPUT_DIR}/ndc_bridge_relations.jsonl"
    with open(relations_file, 'w', encoding='utf-8') as f:
        for relation in relations:
            f.write(json.dumps(relation) + '\n')
    
    summary = {
        "exported_at": datetime.now().isoformat(),
        "schema_version": "5.1.0",
        "source": "ndc_to_rxcui.json (multi-format merged)",
        "source_date": source_date,
        "stats": stats,
    }
    
    with open(f"{OUTPUT_DIR}/ndc_bridge_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✓ Exported:")
    print(f"  ndc_bridge_entities.jsonl: {os.path.getsize(entities_file)/1024/1024:.1f} MB")
    print(f"  ndc_bridge_relations.jsonl: {os.path.getsize(relations_file)/1024/1024:.1f} MB")
    
    # Verify
    print(f"\n[Verification]")
    print(f"  Entities in file: {sum(1 for _ in open(entities_file)):,}")
    print(f"  Expected: {stats['unique_ndcs']:,}")
    
    print("\n" + "=" * 70)
    print("CONVERSION COMPLETE")
    print("=" * 70)
    print(f"Total unique NDC entities: {stats['unique_ndcs']:,}")
    print(f"With multiple formats: {stats['multi_format_count']:,}")


if __name__ == "__main__":
    main()
