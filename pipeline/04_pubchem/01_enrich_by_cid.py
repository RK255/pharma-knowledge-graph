#!/usr/bin/env python3
"""
PubChem CID Enricher v6 - GRC-20 v4 Compliant
Matches Ingredient (IN) nodes to PubChem CIDs via name matching.

Input:
  - rxnorm_entities.jsonl (from 02_rxnorm pipeline)

Output:
  - pubchem_cid_mapping.json (RxCUI → CID mapping)
  - pubchem_enrichment_entities.jsonl (GRC-20 entities)
  - pubchem_enrichment_relations.jsonl (GRC-20 relations)

Usage:
    python 01_enrich_by_cid.py [--auto]
"""

import os
import json
import gzip
import pickle
import sys
import argparse
import ftplib
from datetime import datetime
from typing import Dict, List, Set

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from pharma_schema import PharmaSchema, generate_uuid
from shared_state import save_source_selection

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

FTP_HOST = "ftp.ncbi.nlm.nih.gov"
FTP_PATH = "/pubchem/Compound/Extras/CID-Synonym-filtered.gz"


def get_ftp_file_date() -> str:
    """Get modification date of CID-Synonym file from FTP."""
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login()
        ftp.cwd("/pubchem/Compound/Extras")
        files = []
        ftp.retrlines('LIST CID-Synonym-filtered.gz', files.append)
        ftp.quit()
        
        if files:
            parts = files[0].split()
            date_str = f"{parts[5]} {parts[6]} {parts[7]}"
            try:
                file_date = datetime.strptime(date_str, "%b %d %H:%M")
                file_date = file_date.replace(year=datetime.now().year)
            except ValueError:
                try:
                    file_date = datetime.strptime(date_str, "%b %d %Y")
                except ValueError:
                    file_date = datetime.now()
            return file_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"  Warning: Could not get FTP date: {e}")
    
    return datetime.now().strftime("%Y-%m-%d")


def download_pubchem_file() -> tuple:
    """Download CID-Synonym-filtered.gz if not present."""
    print("\n[3/6] Checking PubChem synonym file...")
    
    os.makedirs(PUBCHEM_DIR, exist_ok=True)
    local_file = os.path.join(PUBCHEM_DIR, "CID-Synonym-filtered.gz")
    
    ftp_date = get_ftp_file_date()
    
    if os.path.exists(local_file):
        local_size = os.path.getsize(local_file) / (1024*1024*1024)
        print(f"  File exists: {local_size:.2f} GB")
        print(f"  FTP date: {ftp_date}")
        return local_file, ftp_date
    
    print(f"  Downloading CID-Synonym-filtered.gz ({ftp_date})...")
    print("  This may take several minutes...")
    
    try:
        with ftplib.FTP(FTP_HOST) as ftp:
            ftp.login()
            with open(local_file, 'wb') as f:
                ftp.retrbinary(f"RETR {FTP_PATH}", f.write)
        print(f"  Downloaded: {os.path.getsize(local_file)/(1024*1024*1024):.2f} GB")
    except Exception as e:
        print(f"  Error downloading: {e}")
        raise
    
    return local_file, ftp_date


def load_in_nodes_from_jsonl(jsonl_file: str) -> List[Dict]:
    """Extract IN (Ingredient) nodes from rxnorm_entities.jsonl."""
    print(f"\n[2/6] Loading IN nodes from {os.path.basename(jsonl_file)}...")
    
    schema = PharmaSchema()
    tty_prop = schema.prop("tty")
    rxcui_prop = schema.prop("rxcui")
    
    in_type = schema.type_id("Ingredient")
    
    in_nodes = []
    
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                entity = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # Check if this is an Ingredient type
            types = entity.get("types", [])
            if in_type not in types:
                continue
            
            entity_id = entity.get("id")
            name = entity.get("name")
            rxcui = None
            
            # Find rxcui in values
            for value in entity.get("values", []):
                if value.get("property") == rxcui_prop:
                    rxcui = value.get("value")
                    break
            
            if name and rxcui:
                in_nodes.append({
                    "entity_id": entity_id,
                    "rxcui": rxcui,
                    "name": name
                })
    
    print(f"  Found {len(in_nodes):,} IN (Ingredient) nodes")
    return in_nodes


def build_synonym_mapping(synonym_file: str) -> Dict[str, str]:
    """Build synonym → CID mapping from CID-Synonym-filtered.gz."""
    print("\n[4/6] Building synonym → CID mapping...")
    
    cache_file = os.path.join(PUBCHEM_DIR, "synonym_to_cid_cache.pkl")
    
    # Check cache
    if os.path.exists(cache_file):
        file_mtime = os.path.getmtime(synonym_file)
        cache_mtime = os.path.getmtime(cache_file)
        if cache_mtime >= file_mtime:
            print(f"  Loading cached mapping...")
            with open(cache_file, 'rb') as f:
                mapping = pickle.load(f)
            print(f"  Loaded {len(mapping):,} synonyms from cache")
            return mapping
    
    # Build from scratch
    print("  Building mapping from file (this takes a few minutes)...")
    synonym_to_cid = {}
    
    with gzip.open(synonym_file, 'rt', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                cid = parts[0]
                synonym = parts[1].lower()
                if synonym not in synonym_to_cid:
                    synonym_to_cid[synonym] = cid
            
            if (i + 1) % 10000000 == 0:
                print(f"    Processed {i+1:,} lines, {len(synonym_to_cid):,} unique synonyms...")
    
    print(f"  Built mapping with {len(synonym_to_cid):,} synonyms")
    
    # Cache it
    print(f"  Caching to {os.path.basename(cache_file)}...")
    with open(cache_file, 'wb') as f:
        pickle.dump(synonym_to_cid, f)
    
    return synonym_to_cid


def match_in_nodes_to_cids(in_nodes: List[Dict], synonym_to_cid: Dict[str, str]) -> tuple:
    """Match IN nodes to PubChem CIDs by name."""
    print("\n[5/6] Matching IN nodes to CIDs...")
    
    matched = []
    unmatched = []
    
    for node in in_nodes:
        name_lower = node['name'].lower()
        if name_lower in synonym_to_cid:
            matched.append({
                **node,
                'pubchem_cid': synonym_to_cid[name_lower],
                'match_type': 'exact_name'
            })
        else:
            unmatched.append(node)
    
    print(f"  Matched: {len(matched):,}")
    print(f"  Unmatched: {len(unmatched):,}")
    
    return matched, unmatched


def export_results(matched: List[Dict], unmatched: List[Dict], pubchem_date: str) -> None:
    """Export results as GRC-20 JSONL and mapping JSON."""
    print("\n[6/6] Exporting results...")
    
    schema = PharmaSchema()
    
    entities = []
    relations = []
    
    # Create provenance entity
    provenance = schema.create_provenance_entity(
        source_name="PubChem",
        date_accessed=pubchem_date
    )
    entities.append(provenance)
    provenance_id = provenance["id"]
    print(f"  Created provenance: {provenance_id}")
    
    # Build CID mapping for JSON export
    cid_mapping = {}
    
    for m in matched:
        cid = m['pubchem_cid']
        rxcui = m['rxcui']
        
        # Store mapping
        cid_mapping[rxcui] = {
            'cid': cid,
            'entity_id': m['entity_id'],
            'name': m['name'],
            'match_type': m['match_type']
        }
        
        # Create PubChem CID entity (deterministic ID from CID)
        pubchem_entity_id = generate_uuid(seed=f"pubchem_cid_{cid}")
        
        pubchem_entity = schema.create_entity(
            entity_type="PubChemCompound",
            name=f"CID:{cid}",
            entity_id=pubchem_entity_id,
        )
        
        # Add pubchem_cid property
        pubchem_entity["values"].append({
            "property": schema.prop("pubchem_cid"),
            "value": cid
        })
        
        entities.append(pubchem_entity)
        
        # Create has_pubchem relation from Ingredient to PubChem compound
        relation = schema.create_relation(
            from_entity_id=m['entity_id'],
            relation_type="has_pubchem",
            to_entity_id=pubchem_entity_id,
        )
        relations.append(relation)
        
        # Add provenance relation
        prov_rel = schema.add_provenance_relation(pubchem_entity_id, "PubChem")
        relations.append(prov_rel)
    
    # Export entities
    entities_file = os.path.join(OUTPUT_DIR, "pubchem_entities.jsonl")
    with open(entities_file, 'w', encoding='utf-8') as f:
        for entity in entities:
            f.write(json.dumps(entity) + '\n')
    
    # Export relations
    relations_file = os.path.join(OUTPUT_DIR, "pubchem_relations.jsonl")
    with open(relations_file, 'w', encoding='utf-8') as f:
        for relation in relations:
            f.write(json.dumps(relation) + '\n')
    
    # Export mapping JSON
    mapping_output = {
        "exported_at": datetime.now().isoformat(),
        "pubchem_release_date": pubchem_date,
        "stats": {
            "total_in_nodes": len(matched) + len(unmatched),
            "matched": len(matched),
            "unmatched": len(unmatched),
        },
        "provenance_entity_id": provenance_id,
        "cid_mapping": cid_mapping,
    }
    
    mapping_file = os.path.join(OUTPUT_DIR, "pubchem_cid_mapping.json")
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping_output, f, indent=2)
    
    # Export unmatched list (first 1000 for debugging)
    unmatched_file = os.path.join(OUTPUT_DIR, "pubchem_unmatched.json")
    with open(unmatched_file, 'w', encoding='utf-8') as f:
        json.dump({
            "count": len(unmatched),
            "sample": [{"rxcui": u['rxcui'], "name": u['name']} for u in unmatched[:1000]]
        }, f, indent=2)
    
    # Calculate sizes
    entities_size = os.path.getsize(entities_file) / 1024 / 1024
    relations_size = os.path.getsize(relations_file) / 1024 / 1024
    mapping_size = os.path.getsize(mapping_file) / 1024 / 1024
    
    print(f"\n  ✅ Exported:")
    print(f"     pubchem_entities.jsonl: {entities_size:.1f} MB ({len(entities):,} entities)")
    print(f"     pubchem_relations.jsonl: {relations_size:.1f} MB ({len(relations):,} relations)")
    print(f"     pubchem_cid_mapping.json: {mapping_size:.1f} MB")
    print(f"     pubchem_unmatched.json")


def main(auto: bool = False):
    print("=" * 70)
    print("PUBCHEM CID ENRICHMENT v6")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Find RxNorm entities file
    print("\n[1/6] Finding RxNorm entities file...")
    
    rxnorm_file = os.path.join(OUTPUT_DIR, "rxnorm_entities.jsonl")
    if not os.path.exists(rxnorm_file):
        print(f"  ERROR: {rxnorm_file} not found")
        print("  Run 02_rxnorm pipeline first")
        return
    
    print(f"  Using: {rxnorm_file}")
    
    # Step 2: Load IN nodes
    in_nodes = load_in_nodes_from_jsonl(rxnorm_file)
    
    if not in_nodes:
        print("  No IN nodes found!")
        return
    
    # Step 3: Get PubChem synonym file
    synonym_file, pubchem_date = download_pubchem_file()
    
    # Save selection
    save_source_selection("PubChem_CIDSynonym", synonym_file, metadata={"source_date": pubchem_date})
    
    # Step 4: Build synonym mapping
    synonym_to_cid = build_synonym_mapping(synonym_file)
    
    # Step 5: Match IN nodes to CIDs
    matched, unmatched = match_in_nodes_to_cids(in_nodes, synonym_to_cid)
    
    # Step 6: Export results
    export_results(matched, unmatched, pubchem_date)
    
    print("\n" + "=" * 70)
    print("ENRICHMENT COMPLETE")
    print("=" * 70)
    print(f"Matched: {len(matched):,} / {len(matched)+len(unmatched):,} ({100*len(matched)/(len(matched)+len(unmatched)):.1f}%)")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PubChem CID Enrichment v6")
    parser.add_argument("--auto", action="store_true", help="Auto-select latest files")
    args = parser.parse_args()
    main(auto=args.auto)
