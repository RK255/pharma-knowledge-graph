#!/usr/bin/env python3
import os
import json
import gzip
import hashlib
import ftplib
import datetime
import pandas as pd
import pickle
from neo4j import GraphDatabase
from collections import defaultdict

# Configuration
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
LEDGER_FILE = f"{BASE_DIR}/data/provenance/Granular_Provenance_Ledger.json"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"  # Replace with your actual password

# PubChem FTP details
FTP_HOST = "ftp.ncbi.nlm.nih.gov"
FTP_PATH = "/pubchem/Compound/Extras/CID-Synonym-filtered.gz"

class PubChemEnricher:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.provenance_ledger = {}
        self.in_nodes = []
        self.matched_nodes = []
        self.unmatched_nodes = []
        
    def close(self):
        self.driver.close()
        
    def run(self):
        print("=== Clean RxNorm IN Node PubChem Enrichment ===")
        # Step 1: Load provenance ledger
        self.load_provenance_ledger()
        # Step 2: Extract IN nodes from Neo4j
        self.extract_in_nodes()
        # Step 3: Download latest PubChem CID-Synonym file
        synonym_file = self.download_latest_pubchem_file()
        # Step 4: Build or load synonym to CID mapping
        synonym_to_cid = self.get_synonym_to_cid_mapping(synonym_file)
        # Step 5: Match IN nodes to PubChem CIDs
        self.match_in_nodes_to_cids(synonym_to_cid)
        # Step 6: Export matched data to CSV
        self.export_results()
        # Step 7: IMPORT TO NEO4J - NEW STEP
        self.import_to_neo4j()
        # Step 8: Save provenance ledger
        self.save_provenance_ledger()
        print("\n=== PubChem Enrichment Complete ===")
        
    def load_provenance_ledger(self):
        """Load existing provenance ledger or create a new one"""
        print("\n--- Loading Provenance Ledger ---")
        if os.path.exists(LEDGER_FILE):
            with open(LEDGER_FILE, 'r') as f:
                self.provenance_ledger = json.load(f)
            print(f"✅ Loaded existing provenance ledger with {len(self.provenance_ledger)} entries")
        else:
            self.provenance_ledger = {}
            os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
            print("✅ Created new provenance ledger")
            
    def create_provenance_record(self, data_type, source, source_file, **kwargs):
        """Create a provenance record and return its hash"""
        # Base metadata
        metadata = {
            "data_type": data_type,
            "source": source,
            "source_file": source_file,
            "date_published": "2026-02-13",
            "date_accessed": datetime.datetime.now().strftime("%Y-%m-%d"),
        }
        
        # Add additional metadata
        for key, value in kwargs.items():
            metadata[key] = value
            
        # Create full citation
        if source == "pubchem":
            metadata["full_citation"] = f"PubChem Database. National Center for Biotechnology Information. Data version unknown. Accessed on {metadata['date_accessed']}."
        else:
            metadata["full_citation"] = f"RxNorm (Prescribable Content). National Library of Medicine. Dataset released on {metadata['date_published']}. Accessed on {metadata['date_accessed']}."
            
        # Create hash
        prov_hash = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        
        # Add to ledger
        self.provenance_ledger[prov_hash] = metadata
        
        return prov_hash
        
    def extract_in_nodes(self):
        """Extract all IN nodes from Neo4j"""
        print("\n--- Extracting IN Nodes from Neo4j ---")
        with self.driver.session(database="neo4j") as session:
            result = session.run("""
                MATCH (n:Ingredient {primary_tty: 'IN'})
                RETURN n.rxcui AS rxcui, n.name AS name, n.provenance_rxnorm AS provenance_rxnorm
            """)
            self.in_nodes = [{"rxcui": record["rxcui"], "name": record["name"], "provenance_rxnorm": record["provenance_rxnorm"]} for record in result]
        print(f"✅ Extracted {len(self.in_nodes)} IN nodes from Neo4j")
        
    def download_latest_pubchem_file(self):
        """Download the latest PubChem CID-Synonym file"""
        print("\n--- Downloading Latest PubChem CID-Synonym File ---")
        # Create directory if it doesn't exist
        os.makedirs(PUBCHEM_DIR, exist_ok=True)
        
        # Set the local file path
        local_file = os.path.join(PUBCHEM_DIR, "CID-Synonym-filtered.gz")
        
        # Query PubChem FTP for release date
        print("Querying PubChem FTP for release date of CID-Synonym-filtered.gz...")
        release_date = self.get_pubchem_release_date()
        print(f"✅ Found official release date: {release_date}")
        
        # Check if local file exists and is up-to-date
        if os.path.exists(local_file):
            local_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(local_file)).strftime("%Y-%m-%d")
            if local_mtime == release_date:
                print(f"✅ Local CID-Synonym-filtered.gz is already up-to-date (version {local_mtime}).")
                print(f"✅ Using PubChem file: {local_file}")
                return local_file
                
        # Download the file
        print(f"Local file is from {local_mtime if os.path.exists(local_file) else 'N/A'}, remote is from {release_date}. Downloading latest version...")
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                with open(local_file, 'wb') as f:
                    ftp.retrbinary(f"RETR {FTP_PATH}", f.write)
                
                # Set file modification time to release date
                release_timestamp = datetime.datetime.strptime(release_date, "%Y-%m-%d").timestamp()
                os.utime(local_file, (release_timestamp, release_timestamp))
                
            print(f"✅ Successfully downloaded CID-Synonym-filtered.gz")
            print(f"✅ Using PubChem file: {local_file}")
            return local_file
        except Exception as e:
            print(f"❌ Error downloading file: {e}")
            if os.path.exists(local_file):
                print(f"✅ Using existing local file: {local_file}")
                return local_file
            else:
                raise FileNotFoundError("Failed to download CID-Synonym-filtered.gz and no local copy available")
                
    def get_pubchem_release_date(self):
        """Get the release date of the latest PubChem CID-Synonym file"""
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                # Get file modification time
                mtime = ftp.sendcmd(f"MDTM {FTP_PATH}")
                # Parse the response: "213 20260213123456"
                date_str = mtime[4:12]  # Extract YYYYMMDD
                return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except Exception as e:
            print(f"⚠️ Could not get release date from FTP: {e}")
            # Fall back to today's date
            return datetime.datetime.now().strftime("%Y-%m-%d")
            
    def get_synonym_to_cid_mapping(self, synonym_file):
        """Build or load a synonym to CID mapping from the PubChem file"""
        print("\n--- Building or Loading Synonym to CID Mapping ---")
        
        # Check for cached mapping
        cache_file = os.path.join(PUBCHEM_DIR, "synonym_to_cid_cache.pkl")
        if os.path.exists(cache_file):
            file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(synonym_file)).strftime("%Y-%m-%d")
            cache_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cache_file)).strftime("%Y-%m-%d")
            if file_mtime == cache_mtime:
                print(f"✅ Loading cached synonym to CID mapping from {cache_file}")
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
                
        print("Building synonym to CID mapping from scratch...")
        # Build the mapping
        synonym_to_cid = {}
        processed = 0
        try:
            with gzip.open(synonym_file, 'rt', encoding='utf-8') as f:
                for line in f:
                    processed += 1
                    if processed % 1000000 == 0:
                        print(f"Processed {processed:,} synonyms...")
                    
                    # Parse the line
                    parts = line.strip().split('\t')
                    if len(parts) < 2:
                        continue
                    
                    cid = parts[0]
                    synonym = parts[1].lower()
                    
                    # Add to mapping
                    if synonym not in synonym_to_cid:
                        synonym_to_cid[synonym] = cid
        except EOFError:
            # Handle corrupted gzip file
            print(f"❌ Error: The gzip file appears to be corrupted at synonym {processed:,}.")
            print(f"❌ This usually indicates an incomplete download. Please re-run the script to re-download the file.")
            raise EOFError("Corrupted gzip file detected")
        except Exception as e:
            print(f"❌ Error processing file: {e}")
            raise
            
        print(f"✅ Built mapping with {len(synonym_to_cid):,} synonyms for {len(set(synonym_to_cid.values())):,} unique CIDs")
        
        # Cache the mapping
        print(f"✅ Saved synonym to CID mapping to cache: {cache_file}")
        with open(cache_file, 'wb') as f:
            pickle.dump(synonym_to_cid, f)
            
        return synonym_to_cid
        
    def match_in_nodes_to_cids(self, synonym_to_cid):
        """Match IN nodes to PubChem CIDs"""
        print("\n--- Matching IN Nodes to CIDs (Exact Matches Only) ---")
        
        self.matched_nodes = []
        self.unmatched_nodes = []
        
        for node in self.in_nodes:
            name = node['name'].lower()
            # Try exact match
            if name in synonym_to_cid:
                # Create provenance record for this match
                prov_hash = self.create_provenance_record(
                    data_type="node_property",
                    source="pubchem",
                    source_file="CID-Synonym-filtered.gz",
                    rxcui=node['rxcui'],
                    property_name="pubchem_cid",
                    property_value=synonym_to_cid[name],
                    match_type="exact"
                )
                
                self.matched_nodes.append({
                    'rxcui': node['rxcui'],
                    'name': node['name'],
                    'rxcui_prov': node['provenance_rxnorm'],
                    'pubchem_cid': synonym_to_cid[name],
                    'pubchem_cid_prov': prov_hash
                })
            else:
                self.unmatched_nodes.append(node)
                
        print(f"✅ Matched {len(self.matched_nodes)} IN nodes to CIDs")
        print(f"❌ Could not find CID for {len(self.unmatched_nodes)} IN nodes")
        
    def export_results(self):
        """Export matched and unmatched nodes to CSV files"""
        print("\n--- Exporting Clean Results ---")
        
        # Create output directory
        output_dir = f"{BASE_DIR}/data/import_csvs"
        os.makedirs(output_dir, exist_ok=True)
        
        # Export matched nodes
        if self.matched_nodes:
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            matched_file = os.path.join(output_dir, f"clean_matched_{date_str}.csv")
            
            # Create DataFrame and export
            df = pd.DataFrame(self.matched_nodes)
            df.to_csv(matched_file, index=False)
            print(f"✅ Exported {len(self.matched_nodes)} matched IN nodes to {matched_file}")
            
        # Export unmatched nodes
        if self.unmatched_nodes:
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            unmatched_file = os.path.join(output_dir, f"clean_unmatched_{date_str}.csv")
            
            # Create DataFrame and export
            df = pd.DataFrame(self.unmatched_nodes)
            df.to_csv(unmatched_file, index=False)
            print(f"✅ Exported {len(self.unmatched_nodes)} unmatched IN nodes to {unmatched_file}")
            
    def import_to_neo4j(self):
        """Import the matched nodes with PubChem CID to Neo4j - NEW METHOD"""
        print("\n--- Importing PubChem Enrichment to Neo4j ---")
        
        if not self.matched_nodes:
            print("⚠️ No nodes to import")
            return
            
        # Create a single provenance record for the enrichment batch
        batch_prov_hash = self.create_provenance_record(
            data_type="batch_enrichment",
            source="pubchem",
            source_file="CID-Synonym-filtered.gz",
            enrichment_type="pubchem_cid",
            enriched_nodes=len(self.matched_nodes),
            date_accessed=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        
        with self.driver.session(database="neo4j") as session:
            # Process in batches
            batch_size = 1000
            for i in range(0, len(self.matched_nodes), batch_size):
                batch = self.matched_nodes[i:i+batch_size]
                
                # Update nodes with PubChem CID and provenance
                query = """
                    UNWIND $nodes AS node
                    MATCH (n:Ingredient {rxcui: node.rxcui})
                    SET n.pubchem_cid = node.pubchem_cid,
                        n.provenance_pubchem = node.pubchem_cid_prov,
                        n.batch_provenance = $batch_prov
                """
                session.run(query, nodes=batch, batch_prov=batch_prov_hash)
                
                if (i + batch_size) % 5000 == 0 or i + batch_size >= len(self.matched_nodes):
                    print(f"Processed {min(i + batch_size, len(self.matched_nodes))}/{len(self.matched_nodes)} nodes")
                    
        print(f"✅ Enriched {len(self.matched_nodes)} IN nodes with PubChem CIDs in Neo4j")
        
    def save_provenance_ledger(self):
        """Save the provenance ledger"""
        print("\n--- Saving Provenance Ledger ---")
        
        os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
        with open(LEDGER_FILE, 'w') as f:
            json.dump(self.provenance_ledger, f, indent=2)
            
        print(f"✅ Saved provenance ledger with {len(self.provenance_ledger)} entries")
        
        # Print summary
        matched_count = len([v for v in self.provenance_ledger.values() 
                           if v.get('data_type') == 'node_property' and v.get('property_name') == 'pubchem_cid'])
        
        print(f"\n=== Clean Enrichment Complete ===")
        print(f"Total IN nodes: {len(self.in_nodes)}")
        print(f"Nodes enriched with CID: {len(self.matched_nodes)}")
        print(f"Nodes not found in PubChem: {len(self.unmatched_nodes)}")
        print(f"Provenance entries added: {len(self.provenance_ledger)}")

if __name__ == "__main__":
    try:
        enricher = PubChemEnricher()
        enricher.run()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'enricher' in locals():
            enricher.close()
