#!/usr/bin/env python3
"""
PubChem Property Enricher v5.1 - Redis Provenance
Supports both gzipped and plain text files, including CID-MeSH and MeSH-Pharm.

Author: GLM 4.6
Date: 2026-02-24
"""

import os
import json
import gzip
import hashlib
import ftplib
import datetime
import pickle
import sys

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

FTP_HOST = "ftp.ncbi.nlm.nih.gov"
FTP_BASE_PATH = "/pubchem/Compound/Extras"

# Core chemical properties - these are the useful ones
CORE_PROPERTIES = {
    "SMILES": {"property_name": "smiles", "description": "Simplified Molecular Input Line Entry System", "gzipped": True},
    "InChI-Key": {"property_name": "inchikey", "description": "International Chemical Identifier Key", "gzipped": True},
    "IUPAC": {"property_name": "iupac_name", "description": "IUPAC chemical name", "gzipped": True},
    "Molecular-Weight": {"property_name": "molecular_weight", "description": "Molecular weight", "gzipped": True},
    "Mass": {"property_name": "exact_mass", "description": "Exact molecular mass", "gzipped": True},
    "Date": {"property_name": "pubchem_date", "description": "Date added to PubChem", "gzipped": True},
    "PMID": {"property_name": "pmid", "description": "PubMed IDs", "gzipped": True},
    "Title": {"property_name": "pubchem_title", "description": "PubChem title", "gzipped": True},
    "Preferred": {"property_name": "preferred_name", "description": "Preferred name", "gzipped": True},
    "SID": {"property_name": "sid", "description": "Substance IDs", "gzipped": True},
    "Parent": {"property_name": "parent_cid", "description": "Parent compound ID", "gzipped": True},
    "Component": {"property_name": "components", "description": "Mixture components", "gzipped": True},
    # Non-gzipped special files
    "MeSH": {"property_name": "mesh_classes", "description": "MeSH pharmacological classes (CID→MeSH)", "gzipped": False, "multi_value": True},
}

# Additional files (name-based matching)
ADDITIONAL_FILES = {
    "MeSH-Pharm": {"property_name": "mesh_pharm", "description": "MeSH pharmacological classes (name→MeSH)", "gzipped": False, "by_name": True},
}

# Files to ignore (checksums, xml, etc.)
IGNORE_PATTERNS = ['.md5', '.xml', 'README', 'Drug-Names']


class PubChemPropertyEnricher:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.provenance = ProvenanceLedger()
        self.cid_nodes = []
        self.name_nodes = {}
        self.selected_options = []
        self.available_options = {}
        
    def close(self):
        if hasattr(self, 'driver'):
            self.driver.close()
        
    def run(self):
        print("=== PubChem Property Enricher v5.1 (Redis Provenance) ===")
        stats = self.provenance.get_stats()
        print(f"Provenance: {stats['total_entries']:,} existing entries in Redis")
        
        try:
            self.extract_nodes()
            self.discover_available_options()
            self.present_enrichment_options()
            
            if self.selected_options:
                for option_key in self.selected_options:
                    option = self.available_options[option_key]
                    self.process_enrichment_option(option_key, option)
            else:
                print("No enrichment options selected. Exiting.")
                
            print("\n=== Enrichment Complete ===")
            stats = self.provenance.get_stats()
            print(f"Total provenance entries: {stats['total_entries']:,}")
            
        except KeyboardInterrupt:
            print("\n⚠️ Process interrupted")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
    def extract_nodes(self):
        print("\n--- Extracting Nodes ---")
        try:
            with self.driver.session(database="neo4j") as session:
                result = session.run("""
                    MATCH (n:Ingredient)
                    WHERE n.pubchem_cid IS NOT NULL
                    RETURN n.rxcui AS rxcui, n.name AS name, n.pubchem_cid AS cid
                    ORDER BY n.rxcui
                """)
                self.cid_nodes = [{"rxcui": r["rxcui"], "name": r["name"], "cid": str(r["cid"])} for r in result]
                
                result2 = session.run("""
                    MATCH (n:Ingredient)
                    WHERE n.pubchem_cid IS NOT NULL
                    RETURN n.rxcui AS rxcui, toLower(n.name) AS name, n.pubchem_cid AS cid
                """)
                for r in result2:
                    self.name_nodes[r["name"]] = {"rxcui": r["rxcui"], "cid": str(r["cid"])}
                    
            print(f"✅ Extracted {len(self.cid_nodes):,} nodes with CIDs")
            print(f"✅ Built name lookup with {len(self.name_nodes):,} entries")
        except Exception as e:
            print(f"❌ Error extracting nodes: {e}")
            raise
        
    def _should_ignore(self, filename):
        """Check if file should be ignored"""
        for pattern in IGNORE_PATTERNS:
            if pattern in filename:
                return True
        return False
        
    def discover_available_options(self):
        print("\n--- Discovering Available Options ---")
        
        # Check local files
        if os.path.exists(PUBCHEM_DIR):
            for file in os.listdir(PUBCHEM_DIR):
                if self._should_ignore(file):
                    continue
                    
                if file.startswith('CID-'):
                    self._add_option_from_file(file, is_cid_file=True)
                elif file in ADDITIONAL_FILES:
                    self._add_option_from_file(file, is_cid_file=False)
        
        # Check FTP for additional options
        self._check_ftp_options()
        
        print(f"✅ Found {len(self.available_options)} available options")
        
    def _add_option_from_file(self, filename, is_cid_file=True):
        """Add an option from a local file"""
        if is_cid_file:
            property_name = filename.replace('CID-', '').replace('.gz', '').replace('.pkl', '')
        else:
            property_name = filename.replace('.gz', '').replace('.pkl', '')
            
        if property_name in self.available_options:
            return
            
        config = CORE_PROPERTIES.get(property_name, ADDITIONAL_FILES.get(property_name, {}))
        
        gzipped = config.get('gzipped', filename.endswith('.gz'))
        ftp_file = f"CID-{property_name}.gz" if gzipped and is_cid_file else (f"CID-{property_name}" if is_cid_file else property_name)
        
        self.available_options[property_name] = {
            "property_name": config.get("property_name", f"pubchem_{property_name.lower()}"),
            "description": config.get("description", f"PubChem {property_name} data"),
            "local_file": os.path.join(PUBCHEM_DIR, filename),
            "cache_file": os.path.join(PUBCHEM_DIR, f"CID-{property_name}.pkl" if is_cid_file else f"{property_name}.pkl"),
            "ftp_file": ftp_file,
            "available_locally": True,
            "available_on_ftp": False,
            "gzipped": gzipped,
            "multi_value": config.get("multi_value", False),
            "by_name": config.get("by_name", False),
        }
        
    def _check_ftp_options(self):
        """Check FTP for options not available locally"""
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                files = []
                ftp.retrlines(f"LIST {FTP_BASE_PATH}", files.append)
                
                for f in files:
                    parts = f.split()
                    if len(parts) < 9:
                        continue
                    filename = parts[-1]
                    
                    # Skip ignored patterns
                    if self._should_ignore(filename):
                        continue
                    
                    if filename.startswith('CID-'):
                        property_name = filename.replace('CID-', '').replace('.gz', '')
                        gzipped = filename.endswith('.gz')
                        
                        if property_name not in self.available_options:
                            config = CORE_PROPERTIES.get(property_name, {})
                            self.available_options[property_name] = {
                                "property_name": config.get("property_name", f"pubchem_{property_name.lower()}"),
                                "description": config.get("description", f"PubChem {property_name}"),
                                "local_file": None,
                                "cache_file": os.path.join(PUBCHEM_DIR, f"CID-{property_name}.pkl"),
                                "ftp_file": filename,
                                "available_locally": False,
                                "available_on_ftp": True,
                                "gzipped": gzipped,
                                "multi_value": config.get("multi_value", False),
                                "by_name": False,
                            }
                        else:
                            self.available_options[property_name]["available_on_ftp"] = True
                            
        except Exception as e:
            print(f"⚠️ Could not check FTP: {e}")
        
    def present_enrichment_options(self):
        print("\n" + "="*70)
        print("Available Enrichment Options")
        print("="*70)
        
        if not self.available_options:
            print("❌ No options available")
            return
            
        # Categorize
        recommended = ['MeSH', 'SMILES', 'InChI-Key', 'MeSH-Pharm']
        core = {k: v for k, v in self.available_options.items() if k in CORE_PROPERTIES}
        additional = {k: v for k, v in self.available_options.items() if k in ADDITIONAL_FILES}
        
        print("\n★ Recommended for Pharmaceutical Knowledge Graph:")
        idx = 1
        rec_options = []
        for key in recommended:
            if key in self.available_options:
                rec_options.append(key)
                opt = self.available_options[key]
                status = "✓ local" if opt["available_locally"] else ("FTP" if opt["available_on_ftp"] else "?")
                print(f"  {idx}. {key}: {opt['description']} [{status}]")
                idx += 1
        
        print("\nCore Chemical Properties:")
        core_options = []
        for key, opt in core.items():
            if key in recommended:
                continue
            core_options.append(key)
            status = "✓ local" if opt["available_locally"] else ("FTP" if opt["available_on_ftp"] else "?")
            print(f"  {idx}. {key}: {opt['description']} [{status}]")
            idx += 1
            
        if additional:
            print("\nAdditional Properties:")
            add_options = []
            for key, opt in additional.items():
                if key in recommended:
                    continue
                add_options.append(key)
                status = "✓ local" if opt["available_locally"] else ("FTP" if opt["available_on_ftp"] else "?")
                print(f"  {idx}. {key}: {opt['description']} [{status}]")
                idx += 1
                
        all_options = rec_options + core_options + add_options
        
        while True:
            try:
                choice = input("\nSelect (e.g., 1,3,5 or 'all' or 'recommended'): ").strip()
                
                if choice.lower() == 'all':
                    self.selected_options = all_options
                    break
                elif choice.lower() == 'recommended':
                    self.selected_options = rec_options
                    break
                elif choice.lower() == 'core':
                    self.selected_options = list(core.keys())
                    break
                    
                indices = [int(x.strip()) for x in choice.split(',')]
                self.selected_options = [all_options[i-1] for i in indices if 1 <= i <= len(all_options)]
                
                if self.selected_options:
                    break
                print("No valid options. Try again.")
                
            except ValueError:
                print("Invalid input. Enter numbers, 'all', 'recommended', or 'core'.")
            except KeyboardInterrupt:
                print("\n⚠️ Interrupted")
                sys.exit(1)
                
        print(f"\n✅ Selected: {', '.join(self.selected_options)}")
        
    def process_enrichment_option(self, option_key, option):
        print(f"\n{'='*70}")
        print(f"Processing: {option_key}")
        print(f"{'='*70}")
        
        try:
            local_file = self.download_or_update_file(option)
            if not local_file:
                print(f"❌ Could not get file. Skipping {option_key}")
                return
                
            if option.get("by_name"):
                self.process_name_based_file(local_file, option_key, option)
            else:
                cid_to_property = self.get_cid_to_property_mapping(local_file, option_key, option)
                if not cid_to_property:
                    print(f"❌ Failed to build mapping")
                    return
                    
                matched_nodes = self.match_cid_nodes_to_properties(cid_to_property, option_key, option)
                if not matched_nodes:
                    print(f"❌ No matches")
                    return
                    
                self.import_properties_to_neo4j(matched_nodes, option, option_key)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
    def download_or_update_file(self, option):
        filename = option["ftp_file"]
        print(f"\n--- File: {filename} ---")
        
        local_file = option.get("local_file") or os.path.join(PUBCHEM_DIR, filename)
        cache_file = option.get("cache_file") or os.path.join(PUBCHEM_DIR, filename.replace('.gz', '') + ".pkl")
        
        os.makedirs(PUBCHEM_DIR, exist_ok=True)
        
        if os.path.exists(local_file):
            size = os.path.getsize(local_file) / 1024
            print(f"✅ Local file exists ({size:.1f} KB)")
            return local_file
            
        if option["available_on_ftp"]:
            try:
                print(f"Downloading {filename}...")
                ftp_path = f"{FTP_BASE_PATH}/{filename}"
                
                with ftplib.FTP(FTP_HOST) as ftp:
                    ftp.login()
                    with open(local_file, 'wb') as f:
                        ftp.retrbinary(f"RETR {ftp_path}", f.write)
                        
                print(f"✅ Downloaded: {os.path.getsize(local_file)/1024:.1f} KB")
                option["local_file"] = local_file
                return local_file
                
            except Exception as e:
                print(f"❌ Download failed: {e}")
                if os.path.exists(local_file):
                    os.remove(local_file)
                return None
        else:
            print(f"❌ File not available locally or on FTP")
            return None
        
    def get_cid_to_property_mapping(self, filename, option_key, option):
        print(f"\n--- Building Mapping ---")
        
        gzipped = option.get("gzipped", filename.endswith('.gz'))
        multi_value = option.get("multi_value", False)
        cache_file = filename.replace('.gz', '') + ".pkl"
        
        if os.path.exists(cache_file):
            file_mtime = os.path.getmtime(filename)
            cache_mtime = os.path.getmtime(cache_file)
            if cache_mtime >= file_mtime:
                print(f"Loading cached mapping...")
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
                    
        print(f"Building mapping from {'gzip' if gzipped else 'plain'} file...")
        cid_to_property = {}
        processed = 0
        
        open_func = gzip.open if gzipped else open
        mode = 'rt' if gzipped else 'r'
        
        try:
            with open_func(filename, mode, encoding='utf-8') as f:
                for line in f:
                    processed += 1
                    if processed % 1000000 == 0:
                        print(f"  {processed:,} entries...")
                        
                    parts = line.strip().split('\t')
                    if len(parts) < 2:
                        continue
                        
                    cid = parts[0]
                    
                    if multi_value:
                        values = parts[1:]
                        if cid not in cid_to_property:
                            cid_to_property[cid] = values
                        else:
                            cid_to_property[cid].extend(values)
                    else:
                        value = parts[1]
                        if cid not in cid_to_property:
                            cid_to_property[cid] = value
                            
        except Exception as e:
            print(f"❌ Error at line {processed}: {e}")
            raise
            
        print(f"✅ Built mapping with {len(cid_to_property):,} entries")
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(cid_to_property, f)
            print(f"✅ Cached to {cache_file}")
        except Exception as e:
            print(f"⚠️ Could not cache: {e}")
            
        return cid_to_property
        
    def process_name_based_file(self, filename, option_key, option):
        """Process files that map name -> properties (like MeSH-Pharm)"""
        print(f"\n--- Processing Name-Based File ---")
        
        gzipped = option.get("gzipped", False)
        open_func = gzip.open if gzipped else open
        mode = 'rt' if gzipped else 'r'
        
        matched_nodes = []
        processed = 0
        
        try:
            with open_func(filename, mode, encoding='utf-8') as f:
                for line in f:
                    processed += 1
                    if processed % 100000 == 0:
                        print(f"  {processed:,} lines, {len(matched_nodes):,} matches...")
                        
                    parts = line.strip().split('\t')
                    if len(parts) < 2:
                        continue
                        
                    name = parts[0].lower()
                    values = parts[1:]
                    
                    if name in self.name_nodes:
                        node_info = self.name_nodes[name]
                        
                        prov_hash = self.provenance.create_entry(
                            data_type="node_property",
                            source="pubchem",
                            source_file=os.path.basename(filename),
                            rxcui=node_info['rxcui'],
                            property_name=option["property_name"],
                            property_value=str(values[:3])[:100],
                            match_type="name_exact"
                        )
                        
                        matched_nodes.append({
                            'rxcui': node_info['rxcui'],
                            'cid': node_info['cid'],
                            'property_value': "|".join(values),
                            'provenance': prov_hash
                        })
                        
            print(f"✅ Matched {len(matched_nodes):,} nodes")
            
            if matched_nodes:
                self.import_properties_to_neo4j(matched_nodes, option, option_key)
                
        except Exception as e:
            print(f"❌ Error: {e}")
            raise
        
    def match_cid_nodes_to_properties(self, cid_to_property, option_key, option):
        print(f"\n--- Matching CIDs ---")
        
        matched_nodes = []
        unmatched = 0
        
        for node in self.cid_nodes:
            cid = node['cid']
            
            if cid in cid_to_property:
                value = cid_to_property[cid]
                
                if isinstance(value, list):
                    value = "|".join(value)
                
                prov_hash = self.provenance.create_entry(
                    data_type="node_property",
                    source="pubchem",
                    source_file=option["ftp_file"],
                    rxcui=node['rxcui'],
                    property_name=option["property_name"],
                    property_value=str(value)[:100],
                    match_type="cid_exact"
                )
                
                matched_nodes.append({
                    'rxcui': node['rxcui'],
                    'cid': cid,
                    'property_value': value,
                    'provenance': prov_hash
                })
            else:
                unmatched += 1
                
        print(f"✅ Matched: {len(matched_nodes):,}")
        print(f"❌ Unmatched: {unmatched:,}")
        
        return matched_nodes
        
    def import_properties_to_neo4j(self, matched_nodes, option, option_key):
        print(f"\n--- Importing to Neo4j ---")
        
        if not matched_nodes:
            print("⚠️ Nothing to import")
            return
            
        batch_prov_hash = self.provenance.create_entry(
            data_type="batch_enrichment",
            source="pubchem",
            source_file=option["ftp_file"],
            enrichment_type=option['property_name'],
            enriched_nodes=len(matched_nodes)
        )
        
        property_name = option['property_name']
        
        try:
            with self.driver.session(database="neo4j") as session:
                batch_size = 1000
                
                for i in range(0, len(matched_nodes), batch_size):
                    batch = matched_nodes[i:i+batch_size]
                    
                    query = f"""
                        UNWIND $nodes AS node
                        MATCH (n:Ingredient {{rxcui: node.rxcui}})
                        SET n.{property_name} = node.property_value,
                            n.{property_name}_prov = node.provenance
                    """
                    
                    session.run(query, nodes=batch)
                    
                    if (i + batch_size) % 5000 == 0 or i + batch_size >= len(matched_nodes):
                        print(f"  {min(i + batch_size, len(matched_nodes)):,}/{len(matched_nodes):,}")
                        
            print(f"✅ Enriched {len(matched_nodes):,} nodes with {property_name}")
            
        except Exception as e:
            print(f"❌ Import error: {e}")
            raise


if __name__ == "__main__":
    try:
        enricher = PubChemPropertyEnricher()
        enricher.run()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'enricher' in locals():
            enricher.close()
