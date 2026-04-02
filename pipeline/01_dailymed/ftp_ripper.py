#!/usr/bin/env python3
# DailyMed Multi-Part Download Script (Rx + OTC)

import os
import requests
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

# Configuration
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DAILYMED_DIR = f"{BASE_DIR}/data/dailymed"
RAW_DIR = f"{DAILYMED_DIR}/raw"
EXTRACTED_DIR = f"{DAILYMED_DIR}/extracted"
TARGET_XML_DIR = f"{DAILYMED_DIR}/xml_only"
ARCHIVE_DIR = f"{DAILYMED_DIR}/archive"

# Create directories
for dir_path in [DAILYMED_DIR, RAW_DIR, EXTRACTED_DIR, TARGET_XML_DIR, ARCHIVE_DIR]:
    os.makedirs(dir_path, exist_ok=True)

class DailyMedDownloader:
    def __init__(self):
        self.base_url = "https://dailymed-data.nlm.nih.gov/public-release-files/"
        # Rx archives (6 parts)
        self.rx_parts = [
            "dm_spl_release_human_rx_part1.zip",
            "dm_spl_release_human_rx_part2.zip",
            "dm_spl_release_human_rx_part3.zip",
            "dm_spl_release_human_rx_part4.zip",
            "dm_spl_release_human_rx_part5.zip",
            "dm_spl_release_human_rx_part6.zip"
        ]
        # OTC archives (11 parts)
        self.otc_parts = [
            "dm_spl_release_human_otc_part1.zip",
            "dm_spl_release_human_otc_part2.zip",
            "dm_spl_release_human_otc_part3.zip",
            "dm_spl_release_human_otc_part4.zip",
            "dm_spl_release_human_otc_part5.zip",
            "dm_spl_release_human_otc_part6.zip",
            "dm_spl_release_human_otc_part7.zip",
            "dm_spl_release_human_otc_part8.zip",
            "dm_spl_release_human_otc_part9.zip",
            "dm_spl_release_human_otc_part10.zip",
            "dm_spl_release_human_otc_part11.zip"
        ]
        # All parts combined
        self.all_parts = self.rx_parts + self.otc_parts
    
    def run(self):
        print("=== DailyMed Multi-Part Download (Rx + OTC) ===")
        print(f"Total parts to download: {len(self.all_parts)} (6 Rx + 11 OTC)")
        
        # Step 1: Archive existing XML files
        self.archive_existing_files()
        
        # Step 2: Download all parts
        self.download_all_parts()
        
        # Step 3: Extract all parts (first level)
        self.extract_all_parts()
        
        # Step 4: Extract inner zip files (second level)
        self.extract_inner_zips()
        
        # Step 5: Filter and move XML files to target directory
        self.filter_and_move_xml_files()
        
        # Step 6: Clean up zip files
        self.cleanup_zip_files()
        
        # Step 7: Clean up extracted directory
        self.cleanup_extracted_dir()
        
        print("=== Download Complete ===")
        print(f"New XML files are located in: {TARGET_XML_DIR}")
        print(f"Run the parser: python3 parser.py")
    
    def archive_existing_files(self):
        """Archive existing XML files in the target directory."""
        print("\n--- Archiving Existing Files ---")
        
        files = os.listdir(TARGET_XML_DIR)
        
        if not files:
            print(f"No existing files in {TARGET_XML_DIR} to archive.")
            return
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        archive_subdir = os.path.join(ARCHIVE_DIR, date_str)
        os.makedirs(archive_subdir, exist_ok=True)
        
        for file in files:
            src_path = os.path.join(TARGET_XML_DIR, file)
            dst_path = os.path.join(archive_subdir, file)
            
            try:
                shutil.move(src_path, dst_path)
                print(f"Archived: {file}")
            except Exception as e:
                print(f"Error archiving {file}: {e}")
        
        print(f"✅ Archived {len(files)} files to {archive_subdir}")
    
    def download_all_parts(self):
        """Download all parts (Rx + OTC)"""
        print("\n--- Downloading All Parts ---")
        
        for part in self.all_parts:
            self.download_part(part)
        
        print("✅ All parts downloaded")
    
    def download_part(self, part):
        """Download a single part"""
        part_path = os.path.join(RAW_DIR, part)
        
        if os.path.exists(part_path):
            print(f"✅ {part} already exists, skipping...")
            return part_path
        
        url = f"{self.base_url}{part}"
        print(f"Downloading {part}...")
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(part_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print(f"✅ Downloaded {part}")
            return part_path
            
        except Exception as e:
            print(f"❌ Error downloading {part}: {e}")
            return None
    
    def extract_all_parts(self):
        """Extract all parts to the same directory"""
        print("\n--- Extracting All Parts ---")
        
        for part in self.all_parts:
            part_path = os.path.join(RAW_DIR, part)
            if os.path.exists(part_path):
                self.extract_part(part_path)
        
        print("✅ All parts extracted")
    
    def extract_part(self, part_path):
        """Extract a single part"""
        print(f"Extracting {os.path.basename(part_path)}...")
        
        try:
            with zipfile.ZipFile(part_path, 'r') as zip_ref:
                zip_ref.extractall(EXTRACTED_DIR)
            
            print(f"✅ Extracted {os.path.basename(part_path)}")
            
        except Exception as e:
            print(f"❌ Error extracting {part_path}: {e}")
    
    def extract_inner_zips(self):
        """Find and extract all inner zip files."""
        print("\n--- Extracting Inner Zips ---")
        
        inner_zip_count = 0
        extracted_files_count = 0
        
        for root, dirs, files in os.walk(EXTRACTED_DIR):
            for file in files:
                if file.lower().endswith('.zip'):
                    inner_zip_path = os.path.join(root, file)
                    print(f"  Extracting inner zip: {file}...")
                    
                    try:
                        with zipfile.ZipFile(inner_zip_path, 'r') as zip_ref:
                            zip_ref.extractall(root)
                        
                        os.remove(inner_zip_path)
                        
                        inner_zip_count += 1
                        extracted_files_count += 1 
                        
                        if inner_zip_count % 1000 == 0:
                            print(f"  Processed {inner_zip_count} inner zips...")
                            
                    except Exception as e:
                        print(f"❌ Error extracting inner zip {file}: {e}")
        
        print(f"✅ Extracted {inner_zip_count} inner zips")
    
    def filter_and_move_xml_files(self):
        """Move XML files from extracted dir to target dir and delete non-XML files."""
        print("\n--- Filtering and Moving XML Files ---")
        
        xml_count = 0
        non_xml_count = 0
        
        for root, dirs, files in os.walk(EXTRACTED_DIR):
            for file in files:
                src_path = os.path.join(root, file)
                
                if file.lower().endswith('.xml'):
                    dst_path = os.path.join(TARGET_XML_DIR, file)
                    
                    if os.path.exists(dst_path):
                        base, ext = os.path.splitext(file)
                        count = 1
                        while os.path.exists(dst_path):
                            new_name = f"{base}_{count}{ext}"
                            dst_path = os.path.join(TARGET_XML_DIR, new_name)
                            count += 1
                    
                    try:
                        shutil.move(src_path, dst_path)
                        xml_count += 1
                        if xml_count % 1000 == 0:
                            print(f"  Moved {xml_count} XML files...")
                    except Exception as e:
                        print(f"Error moving {file}: {e}")
                else:
                    try:
                        os.remove(src_path)
                        non_xml_count += 1
                    except Exception as e:
                        print(f"Error deleting {file}: {e}")
        
        print(f"✅ Moved {xml_count} XML files to {TARGET_XML_DIR}")
        print(f"✅ Deleted {non_xml_count} non-XML files")
    
    def cleanup_zip_files(self):
        """Clean up zip files to save space"""
        print("\n--- Cleaning Up Zip Files ---")
        
        for part in self.all_parts:
            part_path = os.path.join(RAW_DIR, part)
            if os.path.exists(part_path):
                os.remove(part_path)
                print(f"Removed {part}")
        
        print("✅ Cleanup complete")
        
    def cleanup_extracted_dir(self):
        """Remove the empty extracted directory."""
        print("\n--- Cleaning Up Extracted Directory ---")
        
        try:
            if os.path.exists(EXTRACTED_DIR):
                shutil.rmtree(EXTRACTED_DIR)
                print(f"✅ Removed {EXTRACTED_DIR}")
        except Exception as e:
            print(f"Error removing extracted directory: {e}")

if __name__ == "__main__":
    downloader = DailyMedDownloader()
    try:
        downloader.run()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
