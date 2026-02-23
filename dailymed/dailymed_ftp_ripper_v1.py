#!/usr/bin/env python3
# DailyMed Multi-Part Download Script

import os
import requests
import zipfile
from pathlib import Path
from datetime import datetime

# Configuration
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DAILYMED_DIR = f"{BASE_DIR}/data/dailymed"
RAW_DIR = f"{DAILYMED_DIR}/raw"
EXTRACTED_DIR = f"{DAILYMED_DIR}/extracted"

# Create directories
for dir_path in [DAILYMED_DIR, RAW_DIR, EXTRACTED_DIR]:
    os.makedirs(dir_path, exist_ok=True)

class DailyMedDownloader:
    def __init__(self):
        self.base_url = "https://dailymed-data.nlm.nih.gov/public-release-files/"
        self.parts = [
            "dm_spl_release_human_rx_part1.zip",
            "dm_spl_release_human_rx_part2.zip",
            "dm_spl_release_human_rx_part3.zip",
            "dm_spl_release_human_rx_part4.zip",
            "dm_spl_release_human_rx_part5.zip",
            "dm_spl_release_human_rx_part6.zip"
        ]
    
    def run(self):
        print("=== DailyMed Multi-Part Download ===")
        
        # Download all parts
        self.download_all_parts()
        
        # Extract all parts
        self.extract_all_parts()
        
        # Clean up zip files
        self.cleanup_zip_files()
        
        print("=== Download Complete ===")
    
    def download_all_parts(self):
        """Download all 6 parts of the DailyMed release"""
        print("\n--- Downloading All Parts ---")
        
        for part in self.parts:
            self.download_part(part)
        
        print("✅ All parts downloaded")
    
    def download_part(self, part):
        """Download a single part"""
        part_path = os.path.join(RAW_DIR, part)
        
        # Check if already downloaded
        if os.path.exists(part_path):
            print(f"✅ {part} already exists, skipping...")
            return part_path
        
        # Download the part
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
        
        for part in self.parts:
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
    
    def cleanup_zip_files(self):
        """Clean up zip files to save space"""
        print("\n--- Cleaning Up Zip Files ---")
        
        for part in self.parts:
            part_path = os.path.join(RAW_DIR, part)
            if os.path.exists(part_path):
                os.remove(part_path)
                print(f"Removed {part}")
        
        print("✅ Cleanup complete")

if __name__ == "__main__":
    downloader = DailyMedDownloader()
    try:
        downloader.run()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
