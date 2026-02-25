#!/usr/bin/env python3
"""
PubChem CID Enricher v4 - Redis Provenance
Matches Ingredient nodes to PubChem CIDs via name matching.
Uses Redis for provenance tracking.
"""

import os
import json
import gzip
import hashlib
import ftplib
import datetime
import pandas as pd
import pickle
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from provenance_redis import ProvenanceLedger

from neo4j import GraphDatabase

# Configuration
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"

# PubChem FTP details
FTP_HOST = "ftp.ncbi.nlm.nih.gov"
FTP_PATH = "/pubchem/Compound/Extras/CID-Synonym-filtered.gz"


class PubChemEnricher:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.provenance = ProvenanceLedger()  # Redis-based
        self.in_nodes = []
        self.matched_nodes = []
        self.unmatched_nodes = []
        
    def close(self):
        self.driver.close()
        
    def run(self):
        print("=== PubChem CID Enricher v4 (Redis Provenance) ===")
        print(f"Provenance: {self.provenance.get_stats()['total_entries']:,} existing entries")
        
        # Step 1: Extract IN nodes from Neo4j
        self.extract_in_nodes()
        # Step 2: Download latest PubChem CID-Synonym file
        synonym_file = self.download_latest_pubchem_file()
        # Step 3: Build or load synonym to CID mapping
        synonym_to_cid = self.get_synonym_to_cid_mapping(synonym_file)
        # Step 4: Match IN nodes to PubChem CIDs
        self.match_in_nodes_to_cids(synonym_to_cid)
        # Step 5: Import to Neo4j
        self.import_to_neo4j()
        # Step 6: Export unmatched for review
        self.export_unmatched()
        
        print("\n=== Enrichment Complete ===")
        stats = self.provenance.get_stats()
        print(f"Total provenance entries: {stats['total_entries']:,}")
        
    def extract_in_nodes(self):
        """Extract all IN nodes from Neo4j"""
        print("\n--- Extracting IN Nodes ---")
        with self.driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (i:Ingredient {tty: 'IN'})
                RETURN i.rxcui AS rxcui, i.name AS name
            """)
            self.in_nodes = [{"rxcui": r["rxcui"], "name": r["name"]} for r in result]
        print(f"✅ Found {len(self.in_nodes):,} IN nodes")
        
    def download_latest_pubchem_file(self):
        """Download the latest PubChem CID-Synonym file"""
        print("\n--- Checking PubChem File ---")
        os.makedirs(PUBCHEM_DIR, exist_ok=True)
        local_file = os.path.join(PUBCHEM_DIR, "CID-Synonym-filtered.gz")
        
        if os.path.exists(local_file):
            local_size = os.path.getsize(local_file) / (1024*1024)
            print(f"✅ Local file exists: {local_file} ({local_size:.1f} MB)")
            return local_file
            
        print("Downloading CID-Synonym-filtered.gz...")
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                with open(local_file, 'wb') as f:
                    ftp.retrbinary(f"RETR {FTP_PATH}", f.write)
            print(f"✅ Downloaded to {local_file}")
        except Exception as e:
            print(f"❌ Download failed: {e}")
            raise
            
        return local_file
        
    def get_synonym_to_cid_mapping(self, synonym_file):
        """Build or load synonym to CID mapping"""
        print("\n--- Building Synonym Mapping ---")
        cache_file = os.path.join(PUBCHEM_DIR, "synonym_to_cid_cache.pkl")
        
        if os.path.exists(cache_file):
            file_mtime = os.path.getmtime(synonym_file)
            cache_mtime = os.path.getmtime(cache_file)
            if cache_mtime >= file_mtime:
                print(f"Loading cached mapping...")
                with open(cache_file, 'rb') as f:
                    mapping = pickle.load(f)
                print(f"✅ Loaded {len(mapping):,} synonyms")
                return mapping
                
        print("Building mapping from file (this may take a minute)...")
        synonym_to_cid = {}
        with gzip.open(synonym_file, 'rt', encoding='utf-8') as f:
            for i, line in enumerate(f):
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    cid = parts[0]
                    synonym = parts[1].lower()
                    if synonym not in synonym_to_cid:
                        synonym_to_cid[synonym] = cid
                if (i + 1) % 5000000 == 0:
                    print(f"  Processed {i+1:,} lines...")
                    
        print(f"✅ Built mapping with {len(synonym_to_cid):,} synonyms")
        
        # Cache it
        with open(cache_file, 'wb') as f:
            pickle.dump(synonym_to_cid, f)
        print(f"✅ Cached to {cache_file}")
        
        return synonym_to_cid
        
    def match_in_nodes_to_cids(self, synonym_to_cid):
        """Match IN nodes to PubChem CIDs"""
        print("\n--- Matching IN Nodes to CIDs ---")
        
        self.matched_nodes = []
        self.unmatched_nodes = []
        
        for node in self.in_nodes:
            name = node['name'].lower()
            if name in synonym_to_cid:
                # Create provenance entry in Redis
                prov_hash = self.provenance.create_entry(
                    data_type="node_property",
                    source="pubchem",
                    source_file="CID-Synonym-filtered.gz",
                    rxcui=node['rxcui'],
                    property_name="pubchem_cid",
                    property_value=synonym_to_cid[name],
                    match_type="exact_name"
                )
                
                self.matched_nodes.append({
                    'rxcui': node['rxcui'],
                    'name': node['name'],
                    'pubchem_cid': synonym_to_cid[name],
                    'provenance': prov_hash
                })
            else:
                self.unmatched_nodes.append(node)
                
        print(f"✅ Matched: {len(self.matched_nodes):,}")
        print(f"❌ Unmatched: {len(self.unmatched_nodes):,}")
        
    def import_to_neo4j(self):
        """Import matched nodes to Neo4j"""
        print("\n--- Importing to Neo4j ---")
        
        if not self.matched_nodes:
            print("Nothing to import")
            return
            
        # Create batch provenance
        batch_hash = self.provenance.create_entry(
            data_type="batch_enrichment",
            source="pubchem",
            source_file="CID-Synonym-filtered.gz",
            enrichment_type="pubchem_cid",
            enriched_nodes=len(self.matched_nodes)
        )
        
        with self.driver.session(database="neo4j") as session:
            batch_size = 1000
            for i in range(0, len(self.matched_nodes), batch_size):
                batch = self.matched_nodes[i:i+batch_size]
                
                query = """
                    UNWIND $nodes AS node
                    MATCH (i:Ingredient {rxcui: node.rxcui})
                    SET i.pubchem_cid = node.pubchem_cid,
                        i.pubchem_cid_prov = node.provenance,
                        i.pubchem_batch_prov = $batch_hash
                """
                session.run(query, nodes=batch, batch_hash=batch_hash)
                
                if (i + batch_size) % 5000 == 0 or i + batch_size >= len(self.matched_nodes):
                    print(f"  Imported {min(i + batch_size, len(self.matched_nodes)):,}/{len(self.matched_nodes):,}")
                    
        print(f"✅ Imported {len(self.matched_nodes):,} nodes")
        
    def export_unmatched(self):
        """Export unmatched nodes for review"""
        if self.unmatched_nodes:
            output_dir = f"{BASE_DIR}/data/import_csvs"
            os.makedirs(output_dir, exist_ok=True)
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            output_file = os.path.join(output_dir, f"unmatched_ingredients_{date_str}.csv")
            
            df = pd.DataFrame(self.unmatched_nodes)
            df.to_csv(output_file, index=False)
            print(f"✅ Exported {len(self.unmatched_nodes):,} unmatched to {output_file}")


if __name__ == "__main__":
    try:
        enricher = PubChemEnricher()
        enricher.run()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'enricher' in locals():
            enricher.close()
