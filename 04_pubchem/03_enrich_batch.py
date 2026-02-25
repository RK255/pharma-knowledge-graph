#!/usr/bin/env python3
"""
PubChem Property Enricher v1.2
This script builds on the existing PubChem enricher to add additional chemical properties to nodes with CIDs in Neo4j.
It presents available enrichment options, downloads updated files when needed, and maintains provenance tracking.

Author: GLM 4.6
Date: 2026-02-14
"""

import os
import json
import gzip
import hashlib
import ftplib
import datetime
import pandas as pd
import pickle
import re
import sys
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
FTP_BASE_PATH = "/pubchem/Compound/Extras"

# Define core chemical properties with their corresponding property names and descriptions
# These are the most valuable properties for pharmaceutical knowledge graphs
CORE_PROPERTIES = {
    "SMILES": {"property_name": "smiles", "description": "Simplified Molecular Input Line Entry System"},
    "InChI-Key": {"property_name": "inchikey", "description": "International Chemical Identifier Key"},
    "IUPAC": {"property_name": "iupac_name", "description": "International Union of Pure and Applied Chemistry name"},
    "Molecular-Weight": {"property_name": "molecular_weight", "description": "Molecular weight of the compound"},
    "Date": {"property_name": "pubchem_date", "description": "Date the compound was added to PubChem"},
    "PMID": {"property_name": "pmid", "description": "PubMed IDs referencing this compound"},
    "Title": {"property_name": "pubchem_title", "description": "Title of the compound in PubChem"},
    "Preferred": {"property_name": "preferred_name", "description": "Preferred name for the compound"},
    "SID": {"property_name": "sid", "description": "Substance IDs associated with this compound"},
    "Parent": {"property_name": "parent_cid", "description": "Parent compound ID"}
}

class PubChemPropertyEnricher:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.provenance_ledger = {}
        self.cid_nodes = []
        self.selected_options = []
        self.available_options = {}
        self.ftp_files = {}
        
    def close(self):
        """Close the Neo4j driver connection"""
        if hasattr(self, 'driver'):
            self.driver.close()
        
    def run(self):
        """Main execution method"""
        print("=== PubChem Property Enricher v1.2 ===")
        try:
            # Step 1: Load provenance ledger
            self.load_provenance_ledger()
            
            # Step 2: Extract nodes with CIDs from Neo4j
            self.extract_cid_nodes()
            
            # Step 3: Discover available options from local files and FTP
            self.discover_available_options()
            
            # Step 4: Present available enrichment options
            self.present_enrichment_options()
            
            # Step 5: Process selected options
            if self.selected_options:
                for option_key in self.selected_options:
                    option = self.available_options[option_key]
                    self.process_enrichment_option(option_key, option)
            else:
                print("No enrichment options selected. Exiting.")
                
            # Step 6: Save provenance ledger
            self.save_provenance_ledger()
            
        except KeyboardInterrupt:
            print("\n⚠️ Process interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error during execution: {e}")
            import traceback
            traceback.print_exc()
        
    def load_provenance_ledger(self):
        """Load existing provenance ledger or create a new one"""
        print("\n--- Loading Provenance Ledger ---")
        if os.path.exists(LEDGER_FILE):
            try:
                with open(LEDGER_FILE, 'r') as f:
                    self.provenance_ledger = json.load(f)
                print(f"✅ Loaded existing provenance ledger with {len(self.provenance_ledger)} entries")
            except Exception as e:
                print(f"⚠️ Error loading provenance ledger: {e}")
                print("✅ Creating new provenance ledger")
                self.provenance_ledger = {}
        else:
            self.provenance_ledger = {}
            print("✅ Created new provenance ledger")
        
    def create_provenance_record(self, data_type, source, source_file, **kwargs):
        """Create a provenance record and return its hash"""
        # Base metadata
        metadata = {
            "data_type": data_type,
            "source": source,
            "source_file": source_file,
            "date_published": kwargs.get("date_published", "2026-02-14"),
            "date_accessed": datetime.datetime.now().strftime("%Y-%m-%d"),
        }
        
        # Add additional metadata
        for key, value in kwargs.items():
            if key not in ["date_published"]:
                metadata[key] = value
                
        # Create full citation based on source
        if source == "pubchem":
            metadata["full_citation"] = f"PubChem Database. National Center for Biotechnology Information. Data version unknown. Accessed on {metadata['date_accessed']}."
        else:
            metadata["full_citation"] = f"Data from {source}. Accessed on {metadata['date_accessed']}."
            
        # Create hash
        prov_hash = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        
        # Add to ledger
        self.provenance_ledger[prov_hash] = metadata
        
        return prov_hash
        
    def extract_cid_nodes(self):
        """Extract all nodes with PubChem CIDs from Neo4j"""
        print("\n--- Extracting Nodes with PubChem CIDs ---")
        try:
            with self.driver.session(database="neo4j") as session:
                result = session.run("""
                    MATCH (n:Ingredient)
                    WHERE n.pubchem_cid IS NOT NULL
                    RETURN n.rxcui AS rxcui, n.name AS name, n.pubchem_cid AS cid
                    ORDER BY n.rxcui
                """)
                self.cid_nodes = [{"rxcui": record["rxcui"], "name": record["name"], "cid": record["cid"]} for record in result]
            print(f"✅ Extracted {len(self.cid_nodes)} nodes with PubChem CIDs")
        except Exception as e:
            print(f"❌ Error extracting nodes with CIDs: {e}")
            raise
        
    def discover_available_options(self):
        """Discover available enrichment options from local files and FTP"""
        print("\n--- Discovering Available Enrichment Options ---")
        # First, check what's available locally
        self.discover_local_files()
        # Then, query FTP to see what's available for download
        self.discover_ftp_files()
        # Combine the information
        self.combine_available_options()
        
    def discover_local_files(self):
        """Discover available files in the local PubChem directory"""
        print("\n--- Checking Local Files ---")
        if not os.path.exists(PUBCHEM_DIR):
            print(f"❌ PubChem directory not found: {PUBCHEM_DIR}")
            return
            
        # Get all .gz and .pkl files
        local_files = []
        for file in os.listdir(PUBCHEM_DIR):
            if file.endswith('.gz') or file.endswith('.pkl'):
                local_files.append(file)
                
        print(f"✅ Found {len(local_files)} files locally")
        
        # Process local files
        for file in local_files:
            # Extract property name from filename
            if file.endswith('.gz'):
                property_name = file.replace('CID-', '').replace('.gz', '')
                file_path = os.path.join(PUBCHEM_DIR, file)
                cache_path = os.path.join(PUBCHEM_DIR, file.replace('.gz', '.pkl'))
            elif file.endswith('.pkl'):
                property_name = file.replace('CID-', '').replace('.pkl', '')
                file_path = None  # This is a cache file, not the source
                cache_path = os.path.join(PUBCHEM_DIR, file)
            else:
                continue
                
            # Check if this property is in our core properties
            if property_name in CORE_PROPERTIES:
                if property_name not in self.available_options:
                    self.available_options[property_name] = {
                        "property_name": CORE_PROPERTIES[property_name]["property_name"],
                        "description": CORE_PROPERTIES[property_name]["description"],
                        "local_file": file_path,
                        "cache_file": cache_path,
                        "ftp_file": f"CID-{property_name}.gz",
                        "available_locally": file_path is not None or os.path.exists(cache_path),
                        "available_on_ftp": False  # Will be updated later
                    }
                else:
                    # Update local file info if needed
                    if file_path:
                        self.available_options[property_name]["local_file"] = file_path
                        self.available_options[property_name]["cache_file"] = cache_path
                        self.available_options[property_name]["available_locally"] = True
        
    def discover_ftp_files(self):
        """Discover available files on the PubChem FTP server"""
        print("\n--- Querying FTP Server ---")
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                
                # Get directory listing
                files = []
                ftp.retrlines(f"LIST {FTP_BASE_PATH}", files.append)
                
                # Parse the directory listing
                for file_info in files:
                    # Skip directories
                    if file_info.startswith('d'):
                        continue
                        
                    # Extract filename
                    parts = file_info.split()
                    if len(parts) < 9:
                        continue
                        
                    filename = parts[-1]
                    
                    # We're interested in CID-*.gz files
                    if filename.startswith('CID-') and filename.endswith('.gz'):
                        # Extract property name
                        property_name = filename.replace('CID-', '').replace('.gz', '')
                        
                        # Store file info
                        self.ftp_files[property_name] = {
                            "filename": filename,
                            "file_info": file_info
                        }
                        
                        # Update available options if this is a core property
                        if property_name in CORE_PROPERTIES:
                            if property_name not in self.available_options:
                                self.available_options[property_name] = {
                                    "property_name": CORE_PROPERTIES[property_name]["property_name"],
                                    "description": CORE_PROPERTIES[property_name]["description"],
                                    "local_file": None,
                                    "cache_file": os.path.join(PUBCHEM_DIR, f"CID-{property_name}.pkl"),
                                    "ftp_file": filename,
                                    "available_locally": False,
                                    "available_on_ftp": True
                                }
                            else:
                                self.available_options[property_name]["available_on_ftp"] = True
                                if not self.available_options[property_name]["ftp_file"]:
                                    self.available_options[property_name]["ftp_file"] = filename
                                    
            print(f"✅ Found {len(self.ftp_files)} CID-*.gz files on FTP server")
        except Exception as e:
            print(f"⚠️ Could not query FTP server: {e}")
            print("⚠️ Will only use local files for enrichment")
        
    def combine_available_options(self):
        """Combine information from local files and FTP"""
        print("\n--- Combining Available Options ---")
        
        # Add non-core properties that are available locally
        if os.path.exists(PUBCHEM_DIR):
            for file in os.listdir(PUBCHEM_DIR):
                if file.startswith('CID-') and file.endswith('.gz'):
                    property_name = file.replace('CID-', '').replace('.gz', '')
                    
                    # Skip if already in available options
                    if property_name in self.available_options:
                        continue
                        
                    # Add as an additional option
                    self.available_options[property_name] = {
                        "property_name": f"pubchem_{property_name.lower()}",
                        "description": f"PubChem {property_name} data",
                        "local_file": os.path.join(PUBCHEM_DIR, file),
                        "cache_file": os.path.join(PUBCHEM_DIR, file.replace('.gz', '.pkl')),
                        "ftp_file": file,
                        "available_locally": True,
                        "available_on_ftp": False
                    }
                    
        print(f"✅ Combined {len(self.available_options)} available options")
        
    def present_enrichment_options(self):
        """Present available enrichment options to the user"""
        print("\n--- Available Enrichment Options ---")
        
        if not self.available_options:
            print("❌ No enrichment options available.")
            return
            
        # Separate core properties and additional properties
        core_options = {k: v for k, v in self.available_options.items() if k in CORE_PROPERTIES}
        additional_options = {k: v for k, v in self.available_options.items() if k not in CORE_PROPERTIES}
        
        # Display core properties first
        print("\nCore Chemical Properties (Recommended):")
        for i, (key, option) in enumerate(core_options.items(), 1):
            status = ""
            if option["available_locally"]:
                status = " (available locally)"
            elif option["available_on_ftp"]:
                status = " (available on FTP)"
            print(f"{i}. {key}: {option['description']}{status}")
            
        # Display additional properties if any
        if additional_options:
            print("\nAdditional Properties:")
            for i, (key, option) in enumerate(additional_options.items(), len(core_options) + 1):
                status = ""
                if option["available_locally"]:
                    status = " (available locally)"
                elif option["available_on_ftp"]:
                    status = " (available on FTP)"
                print(f"{i}. {key}: {option['description']}{status}")
                
        # Get user selection
        all_options = list(core_options.keys()) + list(additional_options.keys())
        
        while True:
            try:
                choice = input("\nSelect enrichment options (e.g., 1,3,5 or 'all' or 'core'): ").strip()
                
                if choice.lower() == 'all':
                    self.selected_options = all_options
                    break
                elif choice.lower() == 'core':
                    self.selected_options = list(core_options.keys())
                    break
                    
                # Parse comma-separated indices
                indices = [int(x.strip()) for x in choice.split(',')]
                
                # Convert indices to option keys
                self.selected_options = [all_options[i-1] for i in indices if 1 <= i <= len(all_options)]
                
                if self.selected_options:
                    break
                else:
                    print("No valid options selected. Please try again.")
                    
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas, 'all', or 'core'.")
            except KeyboardInterrupt:
                print("\n⚠️ Process interrupted by user")
                sys.exit(1)
                
        print(f"✅ Selected options: {', '.join(self.selected_options)}")
        
    def process_enrichment_option(self, option_key, option):
        """Process a single enrichment option"""
        print(f"\n--- Processing {option_key} Enrichment ---")
        
        try:
            # Step 1: Download or update the file if needed
            local_file = self.download_or_update_file(option)
            if not local_file:
                print(f"❌ Failed to get {option['ftp_file']}. Skipping {option_key} enrichment.")
                return
                
            # Step 2: Build or load CID to property mapping
            cid_to_property = self.get_cid_to_property_mapping(local_file, option_key)
            if not cid_to_property:
                print(f"❌ Failed to build mapping for {option_key}. Skipping.")
                return
                
            # Step 3: Match CID nodes to properties
            matched_nodes = self.match_cid_nodes_to_properties(cid_to_property, option_key)
            if not matched_nodes:
                print(f"❌ No matches found for {option_key}. Skipping.")
                return
                
            # Step 4: Import to Neo4j
            self.import_properties_to_neo4j(matched_nodes, option)
            
        except Exception as e:
            print(f"❌ Error processing {option_key} enrichment: {e}")
            import traceback
            traceback.print_exc()
        
    def download_or_update_file(self, option):
        """Download or update a PubChem file if needed"""
        filename = option["ftp_file"]
        print(f"\n--- Checking {filename} ---")
        
        local_file = option.get("local_file")
        cache_file = option.get("cache_file")
        
        # If we don't have a local file path, construct it
        if not local_file:
            local_file = os.path.join(PUBCHEM_DIR, filename)
            
        # If we don't have a cache file path, construct it
        if not cache_file:
            cache_file = os.path.join(PUBCHEM_DIR, filename.replace('.gz', '.pkl'))
            
        # Create directory if it doesn't exist
        os.makedirs(PUBCHEM_DIR, exist_ok=True)
        
        # Check if we need to download the file
        download_needed = True
        
        if os.path.exists(local_file):
            # If file exists locally, check if it's up-to-date
            if option["available_on_ftp"]:
                # Query PubChem FTP for release date
                print(f"Querying PubChem FTP for release date of {filename}...")
                ftp_path = f"{FTP_BASE_PATH}/{filename}"
                try:
                    release_date = self.get_pubchem_release_date(ftp_path)
                    print(f"✅ Found official release date: {release_date}")
                    
                    local_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(local_file)).strftime("%Y-%m-%d")
                    
                    if local_mtime == release_date:
                        print(f"✅ Local {filename} is already up-to-date (version {local_mtime}).")
                        download_needed = False
                    else:
                        print(f"Local file is from {local_mtime}, remote is from {release_date}. Update needed.")
                except Exception as e:
                    print(f"⚠️ Could not check release date: {e}")
                    print("⚠️ Assuming local file is up-to-date")
                    download_needed = False
            else:
                print(f"✅ Local {filename} exists and is not available on FTP (assuming up-to-date).")
                download_needed = False
        elif os.path.exists(cache_file):
            # If only cache file exists, we can't update without the source file
            print(f"✅ Only cache file exists for {filename}. Cannot update without source file.")
            download_needed = False
        else:
            # File doesn't exist locally, need to download
            print(f"Local file not found. Need to download {filename}.")
            
        # Download the file if needed
        if download_needed and option["available_on_ftp"]:
            try:
                print(f"Downloading {filename}...")
                ftp_path = f"{FTP_BASE_PATH}/{filename}"
                
                with ftplib.FTP(FTP_HOST) as ftp:
                    ftp.login()
                    with open(local_file, 'wb') as f:
                        ftp.retrbinary(f"RETR {ftp_path}", f.write)
                        
                # Set file modification time to release date
                try:
                    release_date = self.get_pubchem_release_date(ftp_path)
                    release_timestamp = datetime.datetime.strptime(release_date, "%Y-%m-%d").timestamp()
                    os.utime(local_file, (release_timestamp, release_timestamp))
                except Exception as e:
                    print(f"⚠️ Could not set file modification time: {e}")
                    
                print(f"✅ Successfully downloaded {filename}")
                
                # Remove cache file if it exists since we have a new data file
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    print(f"✅ Removed outdated cache file")
                    
                # Update option with new local file path
                option["local_file"] = local_file
                
            except Exception as e:
                print(f"❌ Error downloading file: {e}")
                if os.path.exists(local_file):
                    print(f"✅ Using existing local file: {local_file}")
                    download_needed = False
                else:
                    return None
        elif download_needed and not option["available_on_ftp"]:
            print(f"❌ Cannot download {filename} - not available on FTP and no local copy exists.")
            return None
            
        return local_file
        
    def get_pubchem_release_date(self, ftp_path):
        """Get the release date of a PubChem file"""
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                # Get file modification time
                mtime = ftp.sendcmd(f"MDTM {ftp_path}")
                # Parse the response: "213 20260213123456"
                date_str = mtime[4:12]  # Extract YYYYMMDD
                return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except Exception as e:
            print(f"⚠️ Could not get release date from FTP: {e}")
            # Fall back to today's date
            return datetime.datetime.now().strftime("%Y-%m-%d")
        
    def get_cid_to_property_mapping(self, filename, option_key):
        """Build or load a CID to property mapping from a PubChem file"""
        print(f"\n--- Building or Loading CID to {option_key} Mapping ---")
        
        # Check for cached mapping
        cache_file = os.path.join(PUBCHEM_DIR, os.path.basename(filename).replace('.gz', '.pkl'))
        
        if os.path.exists(cache_file):
            try:
                file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filename)).strftime("%Y-%m-%d")
                cache_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cache_file)).strftime("%Y-%m-%d")
                
                if file_mtime == cache_mtime:
                    print(f"✅ Loading cached CID to {option_key} mapping from {cache_file}")
                    with open(cache_file, 'rb') as f:
                        return pickle.load(f)
            except Exception as e:
                print(f"⚠️ Error loading cache: {e}")
                print("✅ Will rebuild mapping from scratch")
                
        print(f"Building CID to {option_key} mapping from scratch...")
        
        # Build the mapping
        cid_to_property = {}
        processed = 0
        
        try:
            with gzip.open(filename, 'rt', encoding='utf-8') as f:
                for line in f:
                    processed += 1
                    if processed % 1000000 == 0:
                        print(f"Processed {processed:,} entries...")
                        
                    # Parse the line
                    parts = line.strip().split('\t')
                    if len(parts) < 2:
                        continue
                        
                    cid = parts[0]
                    property_value = parts[1]
                    
                    # Add to mapping
                    if cid not in cid_to_property:
                        cid_to_property[cid] = property_value
                        
        except EOFError:
            # Handle corrupted gzip file
            print(f"❌ Error: The gzip file appears to be corrupted at entry {processed:,}.")
            print(f"❌ This usually indicates an incomplete download. Please re-run the script to re-download the file.")
            raise EOFError("Corrupted gzip file detected")
        except Exception as e:
            print(f"❌ Error processing file: {e}")
            raise
            
        print(f"✅ Built mapping with {len(cid_to_property):,} entries")
        
        # Cache the mapping
        try:
            print(f"✅ Saved CID to {option_key} mapping to cache: {cache_file}")
            with open(cache_file, 'wb') as f:
                pickle.dump(cid_to_property, f)
        except Exception as e:
            print(f"⚠️ Could not save cache: {e}")
            
        return cid_to_property
        
    def match_cid_nodes_to_properties(self, cid_to_property, option_key):
        """Match CID nodes to properties"""
        print(f"\n--- Matching CID Nodes to {option_key} Properties ---")
        
        matched_nodes = []
        unmatched_nodes = []
        
        for node in self.cid_nodes:
            cid = str(node['cid'])
            
            # Try exact match
            if cid in cid_to_property:
                # Create provenance record for this match
                prov_hash = self.create_provenance_record(
                    data_type="node_property",
                    source="pubchem",
                    source_file=f"CID-{option_key}.gz",
                    rxcui=node['rxcui'],
                    property_name=self.available_options[option_key]["property_name"],
                    property_value=cid_to_property[cid],
                    match_type="exact"
                )
                
                matched_nodes.append({
                    'rxcui': node['rxcui'],
                    'cid': cid,
                    'property_value': cid_to_property[cid],
                    'provenance': prov_hash
                })
            else:
                unmatched_nodes.append(node)
                
        print(f"✅ Matched {len(matched_nodes)} nodes to {option_key} properties")
        print(f"❌ Could not find {option_key} for {len(unmatched_nodes)} nodes")
        
        return matched_nodes
        
    def import_properties_to_neo4j(self, matched_nodes, option):
        """Import the matched properties to Neo4j"""
        print(f"\n--- Importing {option['property_name']} Properties to Neo4j ---")
        
        if not matched_nodes:
            print("⚠️ No properties to import")
            return
            
        # Create a single provenance record for the enrichment batch
        batch_prov_hash = self.create_provenance_record(
            data_type="batch_enrichment",
            source="pubchem",
            source_file=f"CID-{option['property_name'].upper()}.gz",
            enrichment_type=option['property_name'],
            enriched_nodes=len(matched_nodes),
            date_accessed=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        
        try:
            with self.driver.session(database="neo4j") as session:
                # Process in batches
                batch_size = 1000
                
                for i in range(0, len(matched_nodes), batch_size):
                    batch = matched_nodes[i:i+batch_size]
                    
                    # Use a parameterized query to avoid injection issues
                    property_name = option['property_name']
                    
                    # Update nodes with property and provenance
                    query = f"""
                        UNWIND $nodes AS node
                        MATCH (n:Ingredient {{rxcui: node.rxcui}})
                        SET n.pubchem_{property_name} = node.property_value,
                            n.pubchem_{property_name}_prov = node.provenance,
                            n.batch_{property_name}_prov = $batch_prov
                    """
                    
                    session.run(query, nodes=batch, batch_prov=batch_prov_hash)
                    
                    if (i + batch_size) % 5000 == 0 or i + batch_size >= len(matched_nodes):
                        print(f"Processed {min(i + batch_size, len(matched_nodes))}/{len(matched_nodes)} nodes")
                        
            print(f"✅ Enriched {len(matched_nodes)} nodes with {option['property_name']} properties")
            
        except Exception as e:
            print(f"❌ Error importing properties to Neo4j: {e}")
            import traceback
            traceback.print_exc()
        
    def save_provenance_ledger(self):
        """Save the provenance ledger"""
        print("\n--- Saving Provenance Ledger ---")
        
        try:
            os.makedirs(os.path.dirname(LEDGER_FILE), exist_ok=True)
            
            # Create a backup of the existing ledger
            if os.path.exists(LEDGER_FILE):
                backup_file = f"{LEDGER_FILE}.bak"
                with open(LEDGER_FILE, 'r') as src, open(backup_file, 'w') as dst:
                    dst.write(src.read())
                print(f"✅ Created backup of existing ledger: {backup_file}")
                
            # Save the updated ledger
            with open(LEDGER_FILE, 'w') as f:
                json.dump(self.provenance_ledger, f, indent=2)
                
            print(f"✅ Saved provenance ledger with {len(self.provenance_ledger)} entries")
            
            # Print summary
            print(f"\n=== Enrichment Complete ===")
            print(f"Total nodes with CIDs: {len(self.cid_nodes)}")
            print(f"Properties enriched: {', '.join(self.selected_options)}")
            print(f"Provenance entries added: {len(self.provenance_ledger)}")
            
        except Exception as e:
            print(f"❌ Error saving provenance ledger: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    try:
        enricher = PubChemPropertyEnricher()
        enricher.run()
    except KeyboardInterrupt:
        print("\n⚠️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'enricher' in locals():
            enricher.close()
