#!/usr/bin/env python3
"""
Clean RxNorm IN Node PubChem Enrichment with Optional Fuzzy Analysis
This script performs clean enrichment and then offers options for analyzing unmatched ingredients
"""

import os
import json
import hashlib
import gzip
import ftplib
import datetime
import pickle
import pandas as pd
import csv
import sys
import time
import random
from pathlib import Path
from neo4j import GraphDatabase
from collections import defaultdict
from glob import glob

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "BowserNodes"

# Data directories
BASE_DIR = "/home/kage/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
DATA_DIR = f"{BASE_DIR}/data/import_csvs"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
PROVENANCE_FILE = f"{BASE_DIR}/data/provenance/Granular_Provenance_Ledger.json"
CACHE_DIR = f"{BASE_DIR}/data/cache"

# PubChem FTP settings
PUBCHEM_FTP_SERVER = "ftp.ncbi.nlm.nih.gov"
PUBCHEM_FTP_PATH = "pubchem/Compound/Extras"

# Cache file paths
SYNONYM_CACHE_FILE = os.path.join(CACHE_DIR, "synonym_to_cid_cache.pkl")
IN_MAPPING_CACHE_FILE = os.path.join(CACHE_DIR, "in_cid_mapping_cache.pkl")

class CleanRxNormINEnricher:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.provenance_ledger = {}
        self.stats = {
            'total_in_nodes': 0,
            'nodes_enriched': 0,
            'nodes_not_found': 0,
            'provenance_entries': 0
        }
        
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        
    def close(self):
        """Close the Neo4j driver"""
        self.driver.close()
        
    def run(self):
        """Run the complete clean enrichment process"""
        print("=== Clean RxNorm IN Node PubChem Enrichment ===")
        
        # Step 1: Load provenance ledger
        self.load_provenance_ledger()
        
        # Step 2: Extract IN nodes from Neo4j
        in_nodes = self.extract_in_nodes()
        
        # Step 3: Download latest PubChem CID-Synonym file if needed
        synonym_file = self.download_latest_pubchem_synonym_file()
        
        # Step 4: Build or load synonym to CID mapping
        synonym_to_cid = self.get_synonym_to_cid_mapping(synonym_file)
        
        # Step 5: Match IN nodes to CIDs with exact matching only
        in_to_cid_mapping = self.match_in_nodes_to_cids_exact(in_nodes, synonym_to_cid)
        
        # Step 6: Save the mapping to cache
        self.save_in_cid_mapping_cache(in_to_cid_mapping)
        
        # Step 7: Export clean results
        self.export_clean_results(in_nodes, in_to_cid_mapping)
        
        # Step 8: Get user choice for fuzzy analysis
        analysis_choice = self.get_user_choice()
        
        # Step 9: Perform analysis based on user choice
        if analysis_choice == 2:
            self.analyze_unmatched_with_fuzzy(in_nodes, in_to_cid_mapping, synonym_to_cid, sample_size=20)
        elif analysis_choice == 3:
            self.analyze_unmatched_with_fuzzy(in_nodes, in_to_cid_mapping, synonym_to_cid, sample_size=None)
        
        # Step 10: Save provenance ledger
        self.save_provenance_ledger()
        
        print("\n=== Clean Enrichment Complete ===")
        print(f"Total IN nodes: {self.stats['total_in_nodes']}")
        print(f"Nodes enriched with CID: {self.stats['nodes_enriched']}")
        print(f"Nodes not found in PubChem: {self.stats['nodes_not_found']}")
        print(f"Provenance entries added: {self.stats['provenance_entries']}")
        
    def get_user_choice(self):
        """Get user choice for fuzzy analysis"""
        print("\n" + "="*60)
        print("FUZZY ANALYSIS OPTIONS")
        print("="*60)
        print("1. Skip analysis and proceed to finishing")
        print("2. Analyze 20 random unmatched ingredients")
        print("3. Perform full analysis of all unmatched ingredients")
        print("="*60)
        
        while True:
            try:
                choice = input("Enter your choice (1-3): ")
                choice = int(choice)
                if 1 <= choice <= 3:
                    return choice
                else:
                    print("Invalid choice. Please enter a number between 1 and 3.")
            except ValueError:
                print("Invalid input. Please enter a number between 1 and 3.")
        
    def load_provenance_ledger(self):
        """Load existing provenance ledger or create a new one"""
        print("\n--- Loading Provenance Ledger ---")
        
        if os.path.exists(PROVENANCE_FILE):
            with open(PROVENANCE_FILE, 'r') as f:
                self.provenance_ledger = json.load(f)
            print(f"✅ Loaded existing provenance ledger with {len(self.provenance_ledger)} entries")
        else:
            self.provenance_ledger = {}
            os.makedirs(os.path.dirname(PROVENANCE_FILE), exist_ok=True)
            print("✅ Created new provenance ledger")
            
    def extract_in_nodes(self):
        """Extract IN (Ingredient) nodes from Neo4j"""
        print("\n--- Extracting IN Nodes from Neo4j ---")
        
        in_nodes = []
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n:Tier1)
                WHERE 'IN' IN n.all_ttys
                RETURN n.rxcui AS rxcui, n.name AS name, n.provenance_rxnorm AS provenance_rxnorm
                ORDER BY n.name
            """)
            
            for record in result:
                in_nodes.append({
                    'rxcui': record['rxcui'],
                    'name': record['name'],
                    'rxcui_prov': record['provenance_rxnorm']
                })
        
        self.stats['total_in_nodes'] = len(in_nodes)
        print(f"✅ Extracted {len(in_nodes)} IN nodes from Neo4j")
        
        return in_nodes
        
    def get_local_file_mod_date(self, filepath):
        """Gets the modification date of a local file in YYYY-MM-DD format."""
        if not os.path.exists(filepath):
            return None
        mod_time = os.path.getmtime(filepath)
        return datetime.date.fromtimestamp(mod_time).isoformat()
        
    def get_pubchem_file_release_date(self, filename):
        """Query PubChem FTP for release date of a file"""
        print(f"Querying PubChem FTP for release date of {filename}...")
        try:
            ftp = ftplib.FTP(PUBCHEM_FTP_SERVER)
            ftp.login()
            ftp.cwd(PUBCHEM_FTP_PATH)
            
            for entry, properties in ftp.mlsd(facts=['modify']):
                if entry == filename:
                    mod_time_str = properties['modify']
                    release_date = datetime.datetime.strptime(mod_time_str, "%Y%m%d%H%M%S").date().isoformat()
                    print(f"✅ Found official release date: {release_date}")
                    return release_date
            
            return None
        except ftplib.all_errors as e:
            print(f"❌ FTP Error: {e}")
            return None
        finally:
            try:
                ftp.quit()
            except:
                pass
                
    def download_latest_pubchem_file(self, filename, local_dir):
        """Downloads the latest version of a file from the PubChem FTP server"""
        local_filepath = os.path.join(local_dir, filename)
        remote_release_date = self.get_pubchem_file_release_date(filename)
        
        if not remote_release_date:
            print("Could not get remote release date. Proceeding with local file if available.")
            if os.path.exists(local_filepath):
                return local_filepath
            return False
            
        local_mod_date = self.get_local_file_mod_date(local_filepath)
        
        if local_mod_date == remote_release_date:
            print(f"✅ Local {filename} is already up-to-date (version {remote_release_date}).")
            return local_filepath
            
        print(f"\nLocal file is from {local_mod_date or 'N/A'}, remote is from {remote_release_date}. Downloading latest version...")
        
        try:
            ftp = ftplib.FTP(PUBCHEM_FTP_SERVER)
            ftp.login()
            ftp.cwd(PUBCHEM_FTP_PATH)
            
            with open(local_filepath, 'wb') as local_file:
                ftp.retrbinary(f'RETR {filename}', local_file.write)
                
            print(f"✅ Successfully downloaded {filename}")
            ftp.quit()
            return local_filepath
        except ftplib.all_errors as e:
            print(f"❌ FTP Error during download: {e}")
            if os.path.exists(local_filepath):
                print("Using existing local file.")
                return local_filepath
            return False
            
    def download_latest_pubchem_synonym_file(self):
        """Download the latest PubChem CID-Synonym file"""
        print("\n--- Downloading Latest PubChem CID-Synonym File ---")
        
        filename = "CID-Synonym-filtered.gz"
        
        # Ensure PubChem directory exists
        os.makedirs(PUBCHEM_DIR, exist_ok=True)
        
        # Download the file
        filepath = self.download_latest_pubchem_file(filename, PUBCHEM_DIR)
        
        if filepath:
            print(f"✅ Using PubChem file: {filepath}")
            return filepath
        else:
            print("❌ Could not obtain PubChem CID-Synonym file")
            return None
            
    def get_synonym_to_cid_mapping(self, synonym_file):
        """Build or load a mapping from synonyms to CIDs from the PubChem file"""
        print("\n--- Building or Loading Synonym to CID Mapping ---")
        
        # Check if we have a valid cache
        if os.path.exists(SYNONYM_CACHE_FILE):
            file_mod_time = os.path.getmtime(SYNONYM_CACHE_FILE)
            synonym_file_mod_time = os.path.getmtime(synonym_file)
            
            if file_mod_time > synonym_file_mod_time:
                print(f"✅ Loading synonym to CID mapping from cache: {SYNONYM_CACHE_FILE}")
                with open(SYNONYM_CACHE_FILE, 'rb') as f:
                    return pickle.load(f)
        
        # Build the mapping from scratch
        print("Building synonym to CID mapping from scratch...")
        
        if not synonym_file or not os.path.exists(synonym_file):
            print("❌ PubChem synonym file not found")
            return {}
            
        synonym_to_cid = defaultdict(list)
        synonym_count = 0
        
        with gzip.open(synonym_file, 'rt', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    cid = parts[0]
                    synonym = parts[1].lower()
                    synonym_to_cid[synonym].append(cid)
                    synonym_count += 1
                    
                    # Progress reporting
                    if synonym_count % 1000000 == 0:
                        print(f"Processed {synonym_count:,} synonyms...")
                        
        print(f"✅ Built mapping with {synonym_count:,} synonyms for {len(synonym_to_cid):,} unique terms")
        
        # Save to cache
        with open(SYNONYM_CACHE_FILE, 'wb') as f:
            pickle.dump(synonym_to_cid, f)
        print(f"✅ Saved synonym to CID mapping to cache: {SYNONYM_CACHE_FILE}")
        
        return synonym_to_cid
        
    def match_in_nodes_to_cids_exact(self, in_nodes, synonym_to_cid):
        """Match IN nodes to CIDs using only exact synonym matching"""
        print("\n--- Matching IN Nodes to CIDs (Exact Matches Only) ---")
        
        in_to_cid_mapping = {}
        
        for node in in_nodes:
            rxcui = node['rxcui']
            name = node['name'].lower()
            
            # Only try exact match
            if name in synonym_to_cid:
                # Use the first CID if there are multiple
                cid = synonym_to_cid[name][0]
                
                # Create provenance record
                prov_hash = self.create_provenance_record(
                    data_type="node_property",
                    source="pubchem",
                    source_file="CID-Synonym-filtered.gz",
                    rxcui=rxcui,
                    property_name="pubchem_cid",
                    property_value=cid,
                    match_type="exact"
                )
                
                in_to_cid_mapping[rxcui] = {
                    'name': node['name'],
                    'rxcui_prov': node['rxcui_prov'],
                    'pubchem_cid': cid,
                    'pubchem_cid_prov': prov_hash
                }
                self.stats['nodes_enriched'] += 1
            else:
                self.stats['nodes_not_found'] += 1
                
        print(f"✅ Matched {self.stats['nodes_enriched']:,} IN nodes to CIDs")
        print(f"❌ Could not find CID for {self.stats['nodes_not_found']:,} IN nodes")
        
        return in_to_cid_mapping
        
    def save_in_cid_mapping_cache(self, in_to_cid_mapping):
        """Save the IN to CID mapping to cache"""
        print("\n--- Saving IN to CID Mapping Cache ---")
        
        with open(IN_MAPPING_CACHE_FILE, 'wb') as f:
            pickle.dump(in_to_cid_mapping, f)
        print(f"✅ Saved IN to CID mapping to cache: {IN_MAPPING_CACHE_FILE}")
        
    def create_provenance_record(self, data_type, source, source_file, **kwargs):
        """Create a provenance record and return its hash"""
        # Base metadata
        metadata = {
            "data_type": data_type,
            "source": source,
            "source_file": source_file,
            "date_accessed": datetime.date.today().isoformat(),
        }
        
        # Add additional metadata
        for key, value in kwargs.items():
            metadata[key] = value
            
        # Create full citation
        if source == "pubchem":
            release_date = kwargs.get("date_published", "unknown")
            metadata["full_citation"] = f"PubChem Database. National Center for Biotechnology Information. Data version {release_date}. Accessed on {metadata['date_accessed']}."
        else:
            metadata["full_citation"] = f"RxNorm (Prescribable Content). National Library of Medicine. Accessed on {metadata['date_accessed']}."
            
        # Create hash
        prov_hash = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        
        # Add to ledger
        self.provenance_ledger[prov_hash] = metadata
        self.stats['provenance_entries'] += 1
        
        return prov_hash
        
    def export_clean_results(self, in_nodes, in_to_cid_mapping):
        """Export clean results with separate files for matched and unmatched"""
        print("\n--- Exporting Clean Results ---")
        
        # Create output directory if it doesn't exist
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Create timestamp for filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        
        # Export matched nodes
        matched_file = os.path.join(DATA_DIR, f"clean_matched_{timestamp}.csv")
        with open(matched_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['rxcui', 'name', 'rxcui_prov', 'pubchem_cid', 'pubchem_cid_prov'])
            
            for rxcui, data in in_to_cid_mapping.items():
                writer.writerow([
                    rxcui, 
                    data['name'], 
                    data['rxcui_prov'], 
                    data['pubchem_cid'], 
                    data['pubchem_cid_prov']
                ])
                
        print(f"✅ Exported {len(in_to_cid_mapping):,} matched IN nodes to {matched_file}")
        
        # Export unmatched nodes
        unmatched_file = os.path.join(DATA_DIR, f"clean_unmatched_{timestamp}.csv")
        with open(unmatched_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['rxcui', 'name', 'rxcui_prov'])
            
            for node in in_nodes:
                if node['rxcui'] not in in_to_cid_mapping:
                    writer.writerow([
                        node['rxcui'],
                        node['name'],
                        node['rxcui_prov']
                    ])
                    
        print(f"✅ Exported {len(in_nodes) - len(in_to_cid_mapping):,} unmatched IN nodes to {unmatched_file}")
        
    def analyze_unmatched_with_fuzzy(self, in_nodes, in_to_cid_mapping, synonym_to_cid, sample_size=20):
        """Analyze unmatched ingredients with fuzzy matching"""
        print("\n--- Fuzzy Analysis of Unmatched Ingredients ---")
        
        # Get unmatched nodes
        unmatched_nodes = [node for node in in_nodes if node['rxcui'] not in in_to_cid_mapping]
        
        # Determine sample size
        if sample_size is None:
            # Full analysis
            analysis_nodes = unmatched_nodes
            print(f"Performing full analysis of all {len(unmatched_nodes)} unmatched ingredients...")
        else:
            # Sample analysis
            analysis_nodes = random.sample(unmatched_nodes, min(sample_size, len(unmatched_nodes)))
            print(f"Analyzing {len(analysis_nodes)} random unmatched ingredients with fuzzy matching...")
        
        # Try to import fuzzywuzzy
        try:
            from fuzzywuzzy import fuzz
            fuzzy_available = True
        except ImportError:
            print("❌ fuzzywuzzy not available. Install with: pip install fuzzywuzzy python-Levenshtein")
            fuzzy_available = False
        
        if fuzzy_available:
            print("\nFuzzy Matching Results:")
            print("-" * 80)
            
            # Progress tracking for full analysis
            if sample_size is None:
                print("This may take a while for large datasets...")
            
            matches_found = 0
            for i, node in enumerate(analysis_nodes):
                rxcui = node['rxcui']
                name = node['name'].lower()
                
                # Progress tracking for full analysis
                if sample_size is None and (i+1) % 100 == 0:
                    print(f"Processed {i+1}/{len(analysis_nodes)} ingredients...")
                
                # Try different fuzzy matching approaches
                best_exact = None
                best_normalized = None
                best_fuzzy = None
                
                # 1. Try exact match with normalized name
                normalized_name = name.replace("-", " ").replace("_", " ").strip()
                if normalized_name in synonym_to_cid:
                    best_normalized = {
                        'match': normalized_name,
                        'cid': synonym_to_cid[normalized_name][0],
                        'type': 'normalized_exact'
                    }
                    print(f"\nRxCUI: {rxcui}, Name: {node['name']}")
                    print(f"  ✓ Normalized exact match: '{normalized_name}' -> CID {best_normalized['cid']}")
                    matches_found += 1
                
                # 2. Try fuzzy matching
                best_score = 0
                best_match = None
                
                # Limit the search to a reasonable subset for performance
                synonyms_subset = list(synonym_to_cid.keys())[:100000]
                
                for synonym in synonyms_subset:
                    score = fuzz.ratio(name, synonym)
                    if score > best_score and score > 80:  # High threshold
                        best_score = score
                        best_match = (synonym, synonym_to_cid[synonym][0])
                
                if best_match:
                    best_fuzzy = {
                        'match': best_match[0],
                        'cid': best_match[1],
                        'score': best_score,
                        'type': f'fuzzy_{best_score}'
                    }
                    if not best_normalized:  # Only print if we haven't already printed a normalized match
                        print(f"\nRxCUI: {rxcui}, Name: {node['name']}")
                        print(f"  ? Fuzzy match ({best_score}%): '{best_match[0]}' -> CID {best_match[1]}")
                    matches_found += 1
                
                # 3. Check for partial word matches
                words = name.split()
                word_matches = []
                for word in words:
                    if len(word) > 3 and word in synonym_to_cid:  # Skip short words
                        word_matches.append({
                            'word': word,
                            'cid': synonym_to_cid[word][0]
                        })
                
                if word_matches:
                    # Fixed the f-string with nested quotes issue
                    match_strings = [f"{w['word']} -> CID {w['cid']}" for w in word_matches[:3]]
                    if not best_normalized and not best_fuzzy:  # Only print if we haven't already printed a match
                        print(f"\nRxCUI: {rxcui}, Name: {node['name']}")
                        print(f"  ? Word matches: {match_strings}")
                    matches_found += 1
                
                # If no good match found
                if not best_normalized and not best_fuzzy and not word_matches:
                    if sample_size is None and matches_found == 0 and i < 10:  # Show first 10 examples for full analysis
                        print(f"\nRxCUI: {rxcui}, Name: {node['name']}")
                        print("  ❌ No potential matches found")
                    elif sample_size is not None:  # Always show for sample analysis
                        print(f"\nRxCUI: {rxcui}, Name: {node['name']}")
                        print("  ❌ No potential matches found")
            
            print(f"\n✅ Analysis complete. Found potential matches for {matches_found} of {len(analysis_nodes)} ingredients.")
        
        # Save the analysis results
        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        if sample_size is None:
            analysis_file = os.path.join(DATA_DIR, f"full_fuzzy_analysis_{timestamp}.csv")
        else:
            analysis_file = os.path.join(DATA_DIR, f"sample_fuzzy_analysis_{timestamp}.csv")
        
        with open(analysis_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['rxcui', 'name', 'potential_matches'])
            
            for node in analysis_nodes:
                rxcui = node['rxcui']
                name = node['name']
                
                # Find potential matches
                matches = []
                normalized_name = name.lower().replace("-", " ").replace("_", " ").strip()
                
                if normalized_name in synonym_to_cid:
                    matches.append(f"Normalized: {normalized_name} -> CID {synonym_to_cid[normalized_name][0]}")
                
                # Add word matches
                words = name.lower().split()
                for word in words:
                    if len(word) > 3 and word in synonym_to_cid:
                        matches.append(f"Word: {word} -> CID {synonym_to_cid[word][0]}")
                
                writer.writerow([rxcui, name, "; ".join(matches)])
        
        print(f"✅ Saved fuzzy analysis to {analysis_file}")
                
    def save_provenance_ledger(self):
        """Save the provenance ledger to file"""
        print("\n--- Saving Provenance Ledger ---")
        
        try:
            with open(PROVENANCE_FILE, 'w') as f:
                json.dump(self.provenance_ledger, f, indent=2)
            print(f"✅ Saved provenance ledger with {len(self.provenance_ledger)} entries")
        except Exception as e:
            print(f"❌ Error saving provenance ledger: {e}")

def main():
    """Main function to run the clean enrichment process"""
    try:
        enricher = CleanRxNormINEnricher()
        enricher.run()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'enricher' in locals():
            enricher.close()

if __name__ == "__main__":
    main()
