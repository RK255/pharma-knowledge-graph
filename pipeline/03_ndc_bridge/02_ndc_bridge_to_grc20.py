#!/usr/bin/env python3
"""
NDC Bridge to GRC-20 Converter
==============================
Simple converter: ndc_to_rxcui.json + rxnorm_entities.json → ndc_bridge_entities.json

Input:
  - ndc_to_rxcui.json (NDC → RxCUI mapping, from 01_extract_ndcs.py)
  - rxnorm_entities.json (RxCUI → entity_id mapping, from 02_rxnorm pipeline)

Output:
  - ndc_bridge_entities.json (GRC-20 NDC entities with maps_to_rxcui relations)

Usage:
    python 02_ndc_bridge_to_grc20.py
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
from pharma_schema import PharmaSchema

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/raw_data"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

NDC_TO_RXCUI_FILE = f"{DATA_DIR}/ndc_to_rxcui.json"
RXNORM_ENTITIES_FILE = f"{OUTPUT_DIR}/rxnorm_entities.json"
OUTPUT_FILE = f"{OUTPUT_DIR}/ndc_bridge_entities.json"


def main():
    print("=" * 70)
    print("NDC BRIDGE TO GRC-20")
    print("=" * 70)
    
    schema = PharmaSchema()
    
    # [1] Load NDC → RxCUI mapping
    print("\n[1/4] Loading NDC → RxCUI mapping...")
    with open(NDC_TO_RXCUI_FILE, 'r') as f:
        ndc_data = json.load(f)
    
    raw_ndc_to_rxcui = ndc_data.get('ndc_to_rxcui', {})
    # Handle string or list format
    ndc_to_rxcui = {}
    for ndc, rxcuis in raw_ndc_to_rxcui.items():
        ndc_to_rxcui[ndc] = [rxcuis] if isinstance(rxcuis, str) else rxcuis
    
    print(f"  Loaded {len(ndc_to_rxcui):,} NDCs")
    print(f"  Source: {ndc_data.get('created', 'unknown')}")
    
    # [2] Load RxCUI → entity_id from RxNorm entities
    print("\n[2/4] Loading RxNorm entity mapping...")
    with open(RXNORM_ENTITIES_FILE, 'r') as f:
        rxnorm_data = json.load(f)
    
    rxcui_attr = schema.attr("rxcui")
    rxcui_to_entity = {}
    for entity in rxnorm_data.get("entities", []):
        for triple in entity.get("triples", []):
            if triple.get("attribute") == rxcui_attr:
                rxcui = triple.get("value", {}).get("value")
                if rxcui:
                    rxcui_to_entity[rxcui] = entity["entity"]
                break
    
    print(f"  Loaded {len(rxcui_to_entity):,} RxCUI → entity mappings")
    
    # [3] Build NDC entities and relations
    print("\n[3/4] Building NDC entities...")
    
    # Provenance
    provenance = schema.create_provenance(
        source="RxNorm RXNSAT",
        citation="NDC to RxCUI mapping from RxNorm RXNSAT.RRF. National Library of Medicine.",
        date_accessed=datetime.now().strftime("%Y-%m-%d"),
        source_url="https://rxnav.nlm.nih.gov",
    )
    provenance_id = provenance["entity_id"]
    
    entities = [provenance]
    relations = []
    
    # Use Ingredient as entity type (NdcProduct not in schema yet)
    entity_type = "Ingredient"
    
    stats = {"ndcs": 0, "relations": 0, "linked": 0}
    
    for ndc, rxcuis in ndc_to_rxcui.items():
        # Create NDC entity
        entity = schema.create_entity(entity_type=entity_type, name=ndc)
        entity_id = entity["entity"]
        
        entity["triples"].append(schema.triple(entity_id, "ndc_code", ndc))
        entity["triples"].append({
            "entity": entity_id,
            "attribute": schema.rel("has_provenance"),
            "value": {"type": 1, "value": provenance_id},
        })
        
        entities.append(entity)
        stats["ndcs"] += 1
        
        # Create maps_to_rxcui relations
        linked = False
        for rxcui in rxcuis:
            rx_entity = rxcui_to_entity.get(rxcui)
            if rx_entity:
                rel = schema.relation(entity_id, "maps_to_rxcui", rx_entity)
                relations.append({"space": "pharma", "entity": rel[0]["entity"], "triples": rel})
                stats["relations"] += 1
                linked = True
        
        if linked:
            stats["linked"] += 1
        
        if stats["ndcs"] % 50000 == 0:
            print(f"  Processed {stats['ndcs']:,} NDCs...")
    
    print(f"  Created {stats['ndcs']:,} NDC entities")
    print(f"  Created {stats['relations']:,} relations")
    print(f"  Linked {stats['linked']:,} NDCs to RxNorm")
    
    # [4] Export
    print(f"\n[4/4] Exporting to {OUTPUT_FILE}...")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    output = {
        "space": "pharma",
        "version": "2.0.0",
        "exported_at": datetime.now().isoformat(),
        "schema_version": schema.metadata.get("version", "1.0.0"),
        "source": "ndc_to_rxcui.json + rxnorm_entities.json",
        "stats": stats,
        "entities": entities + relations,
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    size_mb = os.path.getsize(OUTPUT_FILE) / 1024 / 1024
    print(f"  Exported {size_mb:.1f} MB ({len(output['entities']):,} entities)")
    
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
