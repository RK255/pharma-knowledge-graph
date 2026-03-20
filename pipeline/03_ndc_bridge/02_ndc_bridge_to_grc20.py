#!/usr/bin/env python3
"""
NDC Bridge to GRC-20 Converter v4.0
===================================
Converts NDC-to-RxCUI mappings to GRC-20 format using PharmaSchema v4.

Input:
  - ndc_to_rxcui.json (NDC → RxCUI mapping, from 01_extract_ndcs.py)
  - rxnorm_entities.jsonl (RxCUI → entity_id mapping, from 02_rxnorm pipeline)

Output:
  - ndc_bridge_entities.jsonl (GRC-20 NDC entities)
  - ndc_bridge_relations.jsonl (maps_to_rxcui relations)
  - ndc_bridge_summary.json (statistics)

Usage:
    python 02_ndc_bridge_to_grc20.py
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set

# Add schema path
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from pharma_schema import PharmaSchema, generate_uuid

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/raw_data"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

NDC_TO_RXCUI_FILE = f"{DATA_DIR}/ndc_to_rxcui.json"
RXNORM_ENTITIES_FILE = f"{OUTPUT_DIR}/rxnorm_entities.jsonl"


def load_rxnorm_entity_mapping(jsonl_file: str) -> Dict[str, str]:
    """
    Load RxCUI → entity_id mapping from rxnorm_entities.jsonl.
    
    Returns dict mapping rxcui (string) to entity_id (UUID string).
    """
    print(f"  Loading from {jsonl_file}...")
    
    rxcui_to_entity = {}
    
    # Property ID for rxcui (from schema)
    rxcui_property_id = "c6f36f8a8e22546ea7618ac008d2f91e"
    
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                entity = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            entity_id = entity.get("id")
            if not entity_id:
                continue
            
            # Find rxcui in values
            for value in entity.get("values", []):
                if value.get("property") == rxcui_property_id:
                    rxcui = value.get("value")
                    if rxcui:
                        rxcui_to_entity[rxcui] = entity_id
                    break
    
    return rxcui_to_entity


def main():
    print("=" * 70)
    print("NDC BRIDGE TO GRC-20 v4.0")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    schema = PharmaSchema()
    
    # [1] Load NDC → RxCUI mapping
    print("\n[1/4] Loading NDC → RxCUI mapping...")
    
    if not os.path.exists(NDC_TO_RXCUI_FILE):
        print(f"  ERROR: {NDC_TO_RXCUI_FILE} not found")
        print("  Run 01_extract_ndcs.py first")
        return
    
    with open(NDC_TO_RXCUI_FILE, 'r') as f:
        ndc_data = json.load(f)
    
    raw_ndc_to_rxcui = ndc_data.get('ndc_to_rxcui', {})
    
    # Handle string or list format
    ndc_to_rxcui: Dict[str, List[str]] = {}
    for ndc, rxcuis in raw_ndc_to_rxcui.items():
        ndc_to_rxcui[ndc] = [rxcuis] if isinstance(rxcuis, str) else rxcuis
    
    source_date = ndc_data.get('source_date', 'unknown')
    print(f"  Loaded {len(ndc_to_rxcui):,} NDCs")
    print(f"  Source date: {source_date}")
    
    # [2] Load RxCUI → entity_id from RxNorm entities
    print("\n[2/4] Loading RxNorm entity mapping...")
    
    if not os.path.exists(RXNORM_ENTITIES_FILE):
        print(f"  ERROR: {RXNORM_ENTITIES_FILE} not found")
        print("  Run 02_rxnorm/01_rxnorm_to_grc20.py first")
        return
    
    rxcui_to_entity = load_rxnorm_entity_mapping(RXNORM_ENTITIES_FILE)
    print(f"  Loaded {len(rxcui_to_entity):,} RxCUI → entity mappings")
    
    # [3] Build NDC entities and relations
    print("\n[3/4] Building GRC-20 entities and relations...")
    
    entities = []
    relations = []
    
    # Create provenance entity using "RxNorm" source (RXNSAT is part of RxNorm)
    provenance = schema.create_provenance_entity(
        source_name="RxNorm",
        date_accessed=source_date
    )
    provenance_id = provenance["id"]
    entities.append(provenance)
    print(f"  Created provenance: {provenance_id}")
    
    # Get property IDs
    ndc_code_prop = schema.prop("ndc_code")
    
    # Stats
    stats = {
        "total_ndcs": len(ndc_to_rxcui),
        "entities_created": 0,
        "relations_created": 0,
        "ndcs_linked": 0,
        "ndcs_unlinked": 0,
        "rxcuis_not_found": set(),
    }
    
    # Process each NDC
    for ndc, rxcuis in ndc_to_rxcui.items():
        # Create NDC entity
        entity_type = "NDC"
        
        # Generate deterministic ID from NDC code
        entity_id = generate_uuid(seed=f"ndc_{ndc}")
        
        entity = schema.create_entity(
            entity_type=entity_type,
            name=ndc,
            entity_id=entity_id,
        )
        
        # Add ndc_code property
        entity["values"].append({
            "property": ndc_code_prop,
            "value": ndc
        })
        
        entities.append(entity)
        stats["entities_created"] += 1
        
        # Create maps_to_rxcui relations
        linked = False
        for rxcui in rxcuis:
            rx_entity_id = rxcui_to_entity.get(rxcui)
            if rx_entity_id:
                # Create relation with deterministic ID
                relation_id = generate_uuid(seed=f"ndc_maps_to_{ndc}_{rxcui}")
                
                relation = schema.create_relation(
                    from_entity_id=entity_id,
                    relation_type="maps_to_rxcui",
                    to_entity_id=rx_entity_id,
                    relation_id=relation_id,
                )
                relations.append(relation)
                stats["relations_created"] += 1
                linked = True
            else:
                stats["rxcuis_not_found"].add(rxcui)
        
        if linked:
            stats["ndcs_linked"] += 1
        else:
            stats["ndcs_unlinked"] += 1
        
        if stats["entities_created"] % 50000 == 0:
            print(f"  Processed {stats['entities_created']:,} NDCs...")
    
    # Add provenance relations for NDC entities
    print(f"  Adding provenance relations...")
    for entity in entities[1:]:  # Skip provenance entity
        prov_rel = schema.add_provenance_relation(entity["id"], "RxNorm")
        relations.append(prov_rel)
    
    stats["rxcuis_not_found"] = len(stats["rxcuis_not_found"])
    
    print(f"\n  Statistics:")
    print(f"    NDC entities created: {stats['entities_created']:,}")
    print(f"    Relations created: {stats['relations_created']:,}")
    print(f"    NDCs linked to RxNorm: {stats['ndcs_linked']:,}")
    print(f"    NDCs unlinked: {stats['ndcs_unlinked']:,}")
    print(f"    RxCUIs not found: {stats['rxcuis_not_found']:,}")
    
    # [4] Export
    print(f"\n[4/4] Exporting to {OUTPUT_DIR}...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Export entities
    entities_file = f"{OUTPUT_DIR}/ndc_bridge_entities.jsonl"
    with open(entities_file, 'w', encoding='utf-8') as f:
        for entity in entities:
            f.write(json.dumps(entity) + '\n')
    
    # Export relations
    relations_file = f"{OUTPUT_DIR}/ndc_bridge_relations.jsonl"
    with open(relations_file, 'w', encoding='utf-8') as f:
        for relation in relations:
            f.write(json.dumps(relation) + '\n')
    
    # Export summary
    summary = {
        "exported_at": datetime.now().isoformat(),
        "schema_version": schema.metadata.get("version", "4.0.0"),
        "source": "ndc_to_rxcui.json + rxnorm_entities.jsonl",
        "source_date": source_date,
        "stats": stats,
    }
    
    summary_file = f"{OUTPUT_DIR}/ndc_bridge_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    # Calculate sizes
    entities_size = os.path.getsize(entities_file) / 1024 / 1024
    relations_size = os.path.getsize(relations_file) / 1024 / 1024
    
    print(f"  ✅ Exported:")
    print(f"     ndc_bridge_entities.jsonl: {entities_size:.1f} MB ({len(entities):,} entities)")
    print(f"     ndc_bridge_relations.jsonl: {relations_size:.1f} MB ({len(relations):,} relations)")
    print(f"     ndc_bridge_summary.json")
    
    print("\n" + "=" * 70)
    print("CONVERSION COMPLETE")
    print("=" * 70)
    print(f"Total entities: {len(entities):,}")
    print(f"Total relations: {len(relations):,}")
    print(f"Linked NDCs: {stats['ndcs_linked']:,} ({100*stats['ndcs_linked']/stats['total_ndcs']:.1f}%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
