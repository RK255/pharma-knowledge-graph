#!/usr/bin/env python3
"""
PubChem Property Fetcher v2 - GRC-20 Compliant
Fetches chemical properties for matched CIDs with full menu system.
Outputs GRC-20 compliant JSON.

Author: GLM 5
Date: 2026-02-26
"""

import os
import json
import gzip
import ftplib
import pickle
import sys
import argparse
from datetime import datetime

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
from pharma_schema import PharmaSchema

# Configuration
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
PUBCHEM_DIR = f"{RAW_DATA_DIR}/pubchem"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

FTP_HOST = "ftp.ncbi.nlm.nih.gov"
FTP_BASE_PATH = "/pubchem/Compound/Extras"

# Core chemical properties
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
    "MeSH": {"property_name": "mesh_classes", "description": "MeSH pharmacological classes (CID→MeSH)", "gzipped": False, "multi_value": True},
}

# Additional files (name-based matching)
ADDITIONAL_FILES = {
    "MeSH-Pharm": {"property_name": "mesh_pharm", "description": "MeSH pharmacological classes (name→MeSH)", "gzipped": False, "by_name": True},
}

# Files to ignore (source files only - .pkl are cache files)
IGNORE_PATTERNS = ['.md5', '.xml', 'README', 'Drug-Names', '.pkl', 'Synonym-filtered']


class PubChemPropertyFetcher:
    def __init__(self):
        self.schema = PharmaSchema()
        self.cid_mapping = {}
        self.name_nodes = {}
        self.selected_options = []
        self.available_options = {}
        self.pubchem_dates = {}
        self.mapping_file = None
        self.mapping_provenance = None
        
    def run(self):
        print("=" * 70)
        print("PUBCHEM PROPERTY FETCHER v2 - GRC-20")
        print("=" * 70)
        
        try:
            self.load_cid_mapping()
            self.discover_available_options()
            self.present_enrichment_options()
            
            if self.selected_options:
                results = {}
                for option_key in self.selected_options:
                    option = self.available_options[option_key]
                    result = self.process_enrichment_option(option_key, option)
                    if result:
                        results[option_key] = result
                
                self.export_results(results)
            else:
                print("No enrichment options selected. Exiting.")
                
        except KeyboardInterrupt:
            print("\n⚠️ Process interrupted")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
    def find_cid_mapping_file(self):
        """Find available CID mapping files"""
        mapping_files = []
        
        if os.path.exists(OUTPUT_DIR):
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("pubchem_cid_mapping") and f.endswith(".json") and "unmatched" not in f:
                    full_path = os.path.join(OUTPUT_DIR, f)
                    mtime = os.path.getmtime(full_path)
                    mapping_files.append((f, full_path, mtime))
        
        mapping_files.sort(key=lambda x: x[2], reverse=True)
        return mapping_files
        
    def load_cid_mapping(self):
        """Load CID mapping from step 1"""
        print("\n--- Loading CID Mapping ---")
        
        mapping_files = self.find_cid_mapping_file()
        
        if not mapping_files:
            raise FileNotFoundError("No pubchem_cid_mapping.json found. Run 01_enrich_by_cid.py first.")
        
        print(f"Found {len(mapping_files)} mapping file(s):")
        for i, (name, path, mtime) in enumerate(mapping_files, 1):
            size_mb = os.path.getsize(path) / 1024 / 1024
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  [{i}] {name} ({size_mb:.2f} MB, {mtime_str})")
        
        selected = mapping_files[0]
        print(f"\nUsing: {selected[0]}")
        self.mapping_file = selected[1]
        
        with open(self.mapping_file, 'r') as f:
            data = json.load(f)
        
        self.cid_mapping = data.get('cid_mapping', {})
        self.mapping_provenance = data.get('provenance_entity')
        
        for rxcui, info in self.cid_mapping.items():
            name_lower = info.get('name', '').lower()
            if name_lower:
                self.name_nodes[name_lower] = {
                    'rxcui': rxcui,
                    'cid': info['cid']
                }
        
        print(f"✅ Loaded {len(self.cid_mapping):,} CID mappings")
        print(f"✅ Built name lookup with {len(self.name_nodes):,} entries")
        
    def _should_ignore(self, filename):
        for pattern in IGNORE_PATTERNS:
            if pattern in filename:
                return True
        return False
        
    def _get_ftp_file_date(self, filename):
        if filename in self.pubchem_dates:
            return self.pubchem_dates[filename]
            
        try:
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                ftp.cwd(FTP_BASE_PATH)
                files = []
                ftp.retrlines(f'LIST {filename}', files.append)
                ftp.quit()
                
                if files:
                    parts = files[0].split()
                    date_str = f"{parts[5]} {parts[6]} {parts[7]}"
                    try:
                        file_date = datetime.strptime(date_str, "%b %d %H:%M")
                        file_date = file_date.replace(year=datetime.now().year)
                        result = file_date.strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            file_date = datetime.strptime(date_str, "%b %d %Y")
                            result = file_date.strftime("%Y-%m-%d")
                        except ValueError:
                            result = datetime.now().strftime("%Y-%m-%d")
                    
                    self.pubchem_dates[filename] = result
                    return result
        except Exception as e:
            print(f"  ⚠️ Could not get FTP date: {e}")
            
        return datetime.now().strftime("%Y-%m-%d")
        
    def discover_available_options(self):
        print("\n--- Discovering Available Options ---")
        
        if os.path.exists(PUBCHEM_DIR):
            for file in os.listdir(PUBCHEM_DIR):
                if self._should_ignore(file):
                    continue
                    
                if file.startswith('CID-'):
                    self._add_option_from_file(file, is_cid_file=True)
                elif file in ADDITIONAL_FILES:
                    self._add_option_from_file(file, is_cid_file=False)
        
        self._check_ftp_options()
        
        print(f"✅ Found {len(self.available_options)} available options")
        
    def _add_option_from_file(self, filename, is_cid_file=True):
        """Add an option from a local SOURCE file (.gz or plain text, NOT .pkl)"""
        # Extract property name - remove CID- prefix and .gz extension
        if is_cid_file:
            property_name = filename.replace('CID-', '').replace('.gz', '')
        else:
            property_name = filename.replace('.gz', '')
            
        if property_name in self.available_options:
            return
            
        config = CORE_PROPERTIES.get(property_name, ADDITIONAL_FILES.get(property_name, {}))
        
        gzipped = config.get('gzipped', filename.endswith('.gz'))
        
        # Source file path (the .gz or plain text file we found)
        source_file = os.path.join(PUBCHEM_DIR, filename)
        
        # Cache file path (always .pkl, same property name)
        cache_file = os.path.join(PUBCHEM_DIR, f"CID-{property_name}.pkl" if is_cid_file else f"{property_name}.pkl")
        
        # Check if cache exists
        has_cache = os.path.exists(cache_file)
        
        self.available_options[property_name] = {
            "property_name": config.get("property_name", f"pubchem_{property_name.lower()}"),
            "description": config.get("description", f"PubChem {property_name} data"),
            "source_file": source_file,  # The actual .gz or plain text file
            "cache_file": cache_file,
            "has_cache": has_cache,
            "ftp_file": f"CID-{property_name}.gz" if gzipped else f"CID-{property_name}",
            "available_locally": True,
            "available_on_ftp": False,
            "gzipped": gzipped,
            "multi_value": config.get("multi_value", False),
            "by_name": config.get("by_name", False),
        }
        
    def _check_ftp_options(self):
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
                    
                    if self._should_ignore(filename):
                        continue
                    
                    if filename.startswith('CID-'):
                        property_name = filename.replace('CID-', '').replace('.gz', '')
                        gzipped = filename.endswith('.gz')
                        
                        if property_name not in self.available_options:
                            config = CORE_PROPERTIES.get(property_name, {})
                            cache_file = os.path.join(PUBCHEM_DIR, f"CID-{property_name}.pkl")
                            
                            self.available_options[property_name] = {
                                "property_name": config.get("property_name", f"pubchem_{property_name.lower()}"),
                                "description": config.get("description", f"PubChem {property_name}"),
                                "source_file": None,
                                "cache_file": cache_file,
                                "has_cache": os.path.exists(cache_file),
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
            
        recommended = ['MeSH', 'SMILES', 'InChI-Key', 'MeSH-Pharm']
        
        print("\n★ Recommended for Pharmaceutical Knowledge Graph:")
        idx = 1
        rec_options = []
        for key in recommended:
            if key in self.available_options:
                rec_options.append(key)
                opt = self.available_options[key]
                status_parts = []
                if opt["available_locally"]:
                    status_parts.append("✓ local")
                if opt["has_cache"]:
                    status_parts.append("✓ cached")
                if opt["available_on_ftp"]:
                    status_parts.append("FTP")
                status = " ".join(status_parts) or "?"
                print(f"  {idx}. {key}: {opt['description']} [{status}]")
                idx += 1
        
        print("\nCore Chemical Properties:")
        core_options = []
        for key, opt in self.available_options.items():
            if key in recommended or key not in CORE_PROPERTIES:
                continue
            core_options.append(key)
            status_parts = []
            if opt["available_locally"]:
                status_parts.append("✓ local")
            if opt["has_cache"]:
                status_parts.append("✓ cached")
            if opt["available_on_ftp"]:
                status_parts.append("FTP")
            status = " ".join(status_parts) or "?"
            print(f"  {idx}. {key}: {opt['description']} [{status}]")
            idx += 1
            
        if any(k in self.available_options for k in ADDITIONAL_FILES):
            print("\nAdditional Properties:")
            add_options = []
            for key in ADDITIONAL_FILES:
                if key in self.available_options and key not in recommended:
                    add_options.append(key)
                    opt = self.available_options[key]
                    status_parts = []
                    if opt["available_locally"]:
                        status_parts.append("✓ local")
                    if opt["has_cache"]:
                        status_parts.append("✓ cached")
                    if opt["available_on_ftp"]:
                        status_parts.append("FTP")
                    status = " ".join(status_parts) or "?"
                    print(f"  {idx}. {key}: {opt['description']} [{status}]")
                    idx += 1
        else:
            add_options = []
                
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
                    self.selected_options = list(CORE_PROPERTIES.keys())
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
            cache_file = option.get("cache_file")
            has_cache = cache_file and os.path.exists(cache_file)
            
            # Always try cache first
            if has_cache:
                print(f"\n✅ Using cached mapping: {os.path.basename(cache_file)}")
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                print(f"   Loaded {len(data):,} entries from cache")
                
                if option.get("by_name"):
                    return self.match_name_nodes_to_properties(data, option_key, option)
                else:
                    return self.match_cid_nodes_to_properties(data, option_key, option)
            
            # No cache - need source file
            source_file = option.get("source_file")
            gzipped = option.get("gzipped", True)
            
            print(f"\n--- Source File ---")
            print(f"   File: {os.path.basename(source_file) if source_file else 'Not available locally'}")
            print(f"   Gzipped: {gzipped}")
            
            if not source_file or not os.path.exists(source_file):
                # Try to download from FTP
                source_file = self.download_from_ftp(option)
                if not source_file:
                    print(f"❌ Could not get source file. Skipping {option_key}")
                    return None
            
            if option.get("by_name"):
                return self.process_name_based_file(source_file, option_key, option)
            else:
                data = self.build_mapping_from_source(source_file, option_key, option)
                if not data:
                    print(f"❌ Failed to build mapping")
                    return None
                return self.match_cid_nodes_to_properties(data, option_key, option)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def download_from_ftp(self, option):
        """Download source file from FTP"""
        filename = option["ftp_file"]
        print(f"\n--- Downloading from FTP ---")
        print(f"   File: {filename}")
        
        os.makedirs(PUBCHEM_DIR, exist_ok=True)
        local_path = os.path.join(PUBCHEM_DIR, filename)
        
        try:
            ftp_path = f"{FTP_BASE_PATH}/{filename}"
            
            with ftplib.FTP(FTP_HOST) as ftp:
                ftp.login()
                with open(local_path, 'wb') as f:
                    ftp.retrbinary(f"RETR {ftp_path}", f.write)
                        
            print(f"✅ Downloaded: {os.path.getsize(local_path)/(1024*1024):.1f} MB")
            option["source_file"] = local_path
            option["available_locally"] = True
            return local_path
                
        except Exception as e:
            print(f"❌ Download failed: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)
            return None
        
    def build_mapping_from_source(self, source_file, option_key, option):
        """Build CID->property mapping from source file"""
        print(f"\n--- Building Mapping ---")
        
        gzipped = option.get("gzipped", source_file.endswith('.gz'))
        multi_value = option.get("multi_value", False)
        
        # Cache file path
        cache_file = source_file.replace('.gz', '') + ".pkl"
        
        print(f"   Source: {os.path.basename(source_file)}")
        print(f"   Format: {'gzip' if gzipped else 'plain text'}")
        
        data = {}
        processed = 0
        
        open_func = gzip.open if gzipped else open
        mode = 'rt' if gzipped else 'r'
        
        try:
            with open_func(source_file, mode, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    processed += 1
                    if processed % 1000000 == 0:
                        print(f"   {processed:,} entries...")
                        
                    parts = line.strip().split('\t')
                    if len(parts) < 2:
                        continue
                        
                    key = parts[0]
                    
                    if multi_value:
                        values = parts[1:]
                        if key not in data:
                            data[key] = values
                        else:
                            data[key].extend(values)
                    else:
                        value = parts[1]
                        if key not in data:
                            data[key] = value
                            
        except Exception as e:
            print(f"❌ Error at line {processed}: {e}")
            raise
            
        print(f"✅ Built mapping with {len(data):,} entries")
        
        # Cache for future use
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
            print(f"✅ Cached to {os.path.basename(cache_file)}")
        except Exception as e:
            print(f"⚠️ Could not cache: {e}")
            
        return data
        
    def process_name_based_file(self, source_file, option_key, option):
        """Process files that map name -> properties (like MeSH-Pharm)"""
        print(f"\n--- Processing Name-Based File ---")
        
        gzipped = option.get("gzipped", False)
        open_func = gzip.open if gzipped else open
        mode = 'rt' if gzipped else 'r'
        
        matched = {}
        processed = 0
        
        try:
            with open_func(source_file, mode, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    processed += 1
                    if processed % 100000 == 0:
                        print(f"   {processed:,} lines, {len(matched):,} matches...")
                        
                    parts = line.strip().split('\t')
                    if len(parts) < 2:
                        continue
                        
                    name = parts[0].lower()
                    values = parts[1:]
                    
                    if name in self.name_nodes:
                        node_info = self.name_nodes[name]
                        rxcui = node_info['rxcui']
                        
                        matched[rxcui] = {
                            'cid': node_info['cid'],
                            'name': name,
                            option['property_name']: "|".join(values)
                        }
                        
            print(f"✅ Matched {len(matched):,} nodes")
            return matched
                
        except Exception as e:
            print(f"❌ Error: {e}")
            raise
        
    def match_cid_nodes_to_properties(self, cid_to_property, option_key, option):
        print(f"\n--- Matching CIDs ---")
        
        matched = {}
        unmatched = 0
        
        for rxcui, info in self.cid_mapping.items():
            cid = str(info['cid'])
            
            if cid in cid_to_property:
                value = cid_to_property[cid]
                
                if isinstance(value, list):
                    value = "|".join(value)
                
                matched[rxcui] = {
                    'cid': info['cid'],
                    'name': info['name'],
                    option['property_name']: value
                }
            else:
                unmatched += 1
                
        print(f"✅ Matched: {len(matched):,}")
        print(f"❌ Unmatched: {unmatched:,}")
        
        return matched
        
    def match_name_nodes_to_properties(self, name_to_property, option_key, option):
        """Match name-based properties from cached mapping"""
        print(f"\n--- Matching Names ---")
        
        matched = {}
        unmatched = 0
        
        for name_lower, node_info in self.name_nodes.items():
            if name_lower in name_to_property:
                value = name_to_property[name_lower]
                
                if isinstance(value, list):
                    value = "|".join(value)
                
                matched[node_info['rxcui']] = {
                    'cid': node_info['cid'],
                    'name': name_lower,
                    option['property_name']: value
                }
            else:
                unmatched += 1
                
        print(f"✅ Matched: {len(matched):,}")
        print(f"❌ Unmatched: {unmatched:,}")
        
        return matched
        
    def export_results(self, results):
        """Export results as GRC-20 JSON"""
        print(f"\n{'='*70}")
        print("Exporting Results")
        print(f"{'='*70}")
        
        for option_key in self.selected_options:
            option = self.available_options[option_key]
            if option.get("available_on_ftp") or option.get("ftp_file"):
                self._get_ftp_file_date(option["ftp_file"])
        
        provenance = self.schema.create_provenance(
            source="PubChem Compound Properties",
            citation=f"PubChem Compound Database, National Center for Biotechnology Information. https://pubchem.ncbi.nlm.nih.gov/",
            date_accessed=datetime.now().strftime("%Y-%m-%d"),
            source_url="https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/",
            provenance_type="AUTOMATED",
        )
        provenance_id = provenance["entity_id"]
        
        enriched_cids = {}
        for rxcui, info in self.cid_mapping.items():
            enriched_cids[rxcui] = {
                'cid': info['cid'],
                'entity_id': info['entity_id'],
                'name': info['name'],
                'match_type': info['match_type'],
                'properties': {}
            }
        
        stats = {"total": len(enriched_cids)}
        for option_key, matched in results.items():
            prop_name = self.available_options[option_key]["property_name"]
            count = 0
            for rxcui, data in matched.items():
                if rxcui in enriched_cids:
                    enriched_cids[rxcui]['properties'][prop_name] = data.get(prop_name, '')
                    count += 1
            stats[f"with_{prop_name}"] = count
            print(f"  {prop_name}: {count:,} enriched")
        
        output = {
            "space": "pharma",
            "version": "1.0.0",
            "exported_at": datetime.now().isoformat(),
            "schema_version": self.schema.metadata.get("version", "1.0.0"),
            "source": os.path.basename(self.mapping_file),
            "pubchem_dates": self.pubchem_dates,
            "provenance_entity": provenance_id,
            "cid_mapping_provenance": self.mapping_provenance,
            "selected_properties": self.selected_options,
            "stats": stats,
            "enriched_cids": enriched_cids,
        }
        
        output_file = os.path.join(OUTPUT_DIR, "pubchem_properties.json")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        size_mb = os.path.getsize(output_file) / 1024 / 1024
        print(f"\n✅ Exported to {output_file} ({size_mb:.2f} MB)")
        print(f"✅ Provenance: {provenance_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PubChem Property Fetcher v2 - GRC-20")
    args = parser.parse_args()
    
    fetcher = PubChemPropertyFetcher()
    fetcher.run()
