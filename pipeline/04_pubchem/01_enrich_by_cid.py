#!/usr/bin/env python3
"""
PubChem CID Enricher v5 - GRC-20 Compliant
Matches Ingredient nodes to PubChem CIDs via name matching.
Outputs GRC-20 compliant JSON with proper FTP date provenance.

Usage:
    python 01_enrich_by_cid.py                  # Interactive file selection
    python 01_enrich_by_cid.py --auto           # Use latest file
"""

import os
import json
import gzip
import pickle
import sys
import argparse
import hashlib
from datetime import datetime

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
from pharma_schema import PharmaSchema

# Configuration
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

# PubChem FTP details
FTP_HOST = "ftp.ncbi.nlm.nih.gov"
FTP_PATH = "/pubchem/Compound/Extras/CID-Synonym-filtered.gz"


def find_rxnorm_entities_file(auto_select=False):
    """Find available rxnorm_entities.json files"""
    print("\n[1/6] Selecting RxNorm entities file...")
    
    entity_files = []
    
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            if f.startswith("rxnorm_entities") and f.endswith(".json"):
                full_path = os.path.join(OUTPUT_DIR, f)
                mtime = os.path.getmtime(full_path)
                entity_files.append((f, full_path, mtime))
    
    entity_files.sort(key=lambda x: x[2], reverse=True)
    
    if not entity_files:
        raise FileNotFoundError("No rxnorm_entities.json files found")
    
    print(f"  Found {len(entity_files)} entity file(s):")
    for i, (name, path, mtime) in enumerate(entity_files, 1):
        size_mb = os.path.getsize(path) / 1024 / 1024
        mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        print(f"    [{i}] {name} ({size_mb:.1f} MB, {mtime_str})")
    
    if auto_select or len(entity_files) == 1:
        selected = entity_files[0]
        print(f"\n  Using: {selected[0]}")
        return selected[1]
    
    try:
        choice = input(f"\n  Select file [1-{len(entity_files)}]: ").strip()
        if not choice:
            choice = "1"
        idx = int(choice) - 1
        if 0 <= idx < len(entity_files):
            return entity_files[idx][1]
    except (ValueError, IndexError):
        pass
    
    print(f"  Using: {entity_files[0][0]}")
    return entity_files[0][1]


def extract_in_nodes(entities_file):
    """Extract IN (Ingredient) nodes from rxnorm_entities.json"""
    print(f"\n[2/6] Extracting IN nodes from {os.path.basename(entities_file)}...")
    
    with open(entities_file, 'r') as f:
        data = json.load(f)
    
    schema = PharmaSchema()
    tty_attr = schema.attr("tty")
    name_attr = schema.attr("name")
    rxcui_attr = schema.attr("rxcui")
    
    in_nodes = []
    for entity in data.get("entities", []):
        tty = None
        name = None
        rxcui = None
        
        for triple in entity.get("triples", []):
            attr = triple.get("attribute")
            val = triple.get("value", {})
            if isinstance(val, dict):
                val = val.get("value")
            
            if attr == tty_attr:
                tty = val
            elif attr == name_attr:
                name = val
            elif attr == rxcui_attr:
                rxcui = val
        
        if tty == "IN" and name and rxcui:
            in_nodes.append({
                "entity_id": entity["entity"],
                "rxcui": rxcui,
                "name": name
            })
    
    print(f"  Found {len(in_nodes):,} IN nodes")
    return in_nodes, entities_file


def get_ftp_file_date():
    """Get the modification date of the CID-Synonym file from FTP"""
    import ftplib
    
    print("  Querying FTP for file date...")
    
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login()
        ftp.cwd("/pubchem/Compound/Extras")
        
        files = []
        ftp.retrlines('LIST CID-Synonym-filtered.gz', files.append)
        ftp.quit()
        
        if files:
            # Parse FTP LIST output: -r--r--r-- 1 ftp anonymous 946112519 Feb 25 06:54 CID-Synonym-filtered.gz
            parts = files[0].split()
            # Date format: "Feb 25 06:54" or "Feb 25 2024"
            date_str = f"{parts[5]} {parts[6]} {parts[7]}"
            
            # Try to parse the date
            try:
                # Try format with time (Feb 25 06:54)
                file_date = datetime.strptime(date_str, "%b %d %H:%M")
                # FTP dates without year mean current year
                file_date = file_date.replace(year=datetime.now().year)
            except ValueError:
                try:
                    # Try format with year (Feb 25 2024)
                    file_date = datetime.strptime(date_str, "%b %d %Y")
                except ValueError:
                    file_date = datetime.now()
            
            print(f"  FTP file date: {file_date.strftime('%Y-%m-%d %H:%M')}")
            return file_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"  Could not get FTP date: {e}")
    
    return datetime.now().strftime("%Y-%m-%d")


def download_pubchem_file():
    """Download CID-Synonym-filtered.gz if not present, return (path, ftp_date)"""
    print("\n[3/6] Checking PubChem file...")
    
    os.makedirs(PUBCHEM_DIR, exist_ok=True)
    local_file = os.path.join(PUBCHEM_DIR, "CID-Synonym-filtered.gz")
    
    # Get FTP date first
    ftp_date = get_ftp_file_date()
    
    if os.path.exists(local_file):
        local_size = os.path.getsize(local_file) / (1024*1024*1024)  # GB
        print(f"  File exists: {local_file} ({local_size:.2f} GB)")
        return local_file, ftp_date
    
    print("  Downloading CID-Synonym-filtered.gz...")
    import ftplib
    try:
        with ftplib.FTP(FTP_HOST) as ftp:
            ftp.login()
            with open(local_file, 'wb') as f:
                ftp.retrbinary(f"RETR {FTP_PATH}", f.write)
        print(f"  Downloaded to {local_file}")
    except Exception as e:
        print(f"  Download failed: {e}")
        raise
    
    return local_file, ftp_date


def get_synonym_to_cid_mapping(synonym_file):
    """Build or load synonym to CID mapping from cached pickle"""
    print("\n[4/6] Building synonym mapping...")
    
    cache_file = os.path.join(PUBCHEM_DIR, "synonym_to_cid_cache.pkl")
    
    # Check if cache is valid
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
    print(f"  Caching to {cache_file}...")
    with open(cache_file, 'wb') as f:
        pickle.dump(synonym_to_cid, f)
    
    return synonym_to_cid


def match_in_nodes_to_cids(in_nodes, synonym_to_cid):
    """Match IN nodes to PubChem CIDs"""
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


def export_results(matched, unmatched, source_file, pubchem_date):
    """Export results as GRC-20 JSON"""
    print("\n[6/6] Exporting results...")
    
    schema = PharmaSchema()
    
    # Create provenance with PubChem release date
    provenance = schema.create_provenance(
        source="PubChem CID-Synonym",
        citation=f"PubChem Compound Database, National Center for Biotechnology Information. Release {pubchem_date}. https://pubchem.ncbi.nlm.nih.gov/",
        date_accessed=datetime.now().strftime("%Y-%m-%d"),
        source_url="https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/",
        provenance_type="AUTOMATED",
    )
    provenance_id = provenance["entity_id"]
    
    # Build CID mapping
    cid_mapping = {}
    for m in matched:
        cid_mapping[m['rxcui']] = {
            'cid': m['pubchem_cid'],
            'entity_id': m['entity_id'],
            'name': m['name'],
            'match_type': m['match_type']
        }
    
    # Build output
    output = {
        "space": "pharma",
        "version": "1.0.0",
        "exported_at": datetime.now().isoformat(),
        "schema_version": schema.metadata.get("version", "1.0.0"),
        "source": os.path.basename(source_file),
        "pubchem_release_date": pubchem_date,
        "stats": {
            "total_in_nodes": len(matched) + len(unmatched),
            "matched": len(matched),
            "unmatched": len(unmatched),
        },
        "provenance_entity": provenance_id,
        "cid_mapping": cid_mapping,
        "unmatched": [u['rxcui'] for u in unmatched[:1000]],
    }
    
    os.makedirs(os.path.dirname(OUTPUT_DIR), exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, "pubchem_cid_mapping.json")
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"  Exported to {output_file} ({size_mb:.2f} MB)")
    print(f"  PubChem release date: {pubchem_date}")
    
    if unmatched:
        unmatched_file = output_file.replace('.json', '_unmatched.json')
        with open(unmatched_file, 'w') as f:
            json.dump({
                "count": len(unmatched),
                "pubchem_release_date": pubchem_date,
                "unmatched": [{"rxcui": u['rxcui'], "name": u['name']} for u in unmatched]
            }, f, indent=2)
        print(f"  Unmatched list: {unmatched_file}")


def main(auto=False):
    print("=" * 70)
    print("PUBCHEM CID ENRICHMENT - GRC-20")
    print("=" * 70)
    
    # Step 1: Select RxNorm entities file
    entities_file = find_rxnorm_entities_file(auto_select=auto)
    
    # Step 2: Extract IN nodes
    in_nodes, source_file = extract_in_nodes(entities_file)
    
    if not in_nodes:
        print("No IN nodes found!")
        return
    
    # Step 3: Get PubChem file (with FTP date)
    synonym_file, pubchem_date = download_pubchem_file()
    
    # Step 4: Build synonym mapping
    synonym_to_cid = get_synonym_to_cid_mapping(synonym_file)
    
    # Step 5: Match IN nodes to CIDs
    matched, unmatched = match_in_nodes_to_cids(in_nodes, synonym_to_cid)
    
    # Step 6: Export results
    export_results(matched, unmatched, source_file, pubchem_date)
    
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PubChem CID Enrichment")
    parser.add_argument("--auto", action="store_true", help="Auto-select latest file")
    args = parser.parse_args()
    main(auto=args.auto)
