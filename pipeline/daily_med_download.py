#!/usr/bin/env python3
"""
DailyMed Multi-Part Download Script v2
========================================
Improvements:
- Parallel downloads for speed.
- Resumable downloads (using Range headers).
- Idempotent extraction (skip existing files).
- Integration with pipeline config.
"""

import os
import requests
import zipfile
import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
# These paths are relative to this script's location
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent.parent.parent
DAILYMED_DIR = BASE_DIR / "data" / "dailymed"
RAW_DIR = DAILYMED_DIR / "raw"
EXTRACTED_DIR = DAILYMED_DIR / "extracted"
CONFIG_FILE = BASE_DIR / "data" / "grc20_v2" / "pipeline_config.json"

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
        print("="*70)
        print("DAILYMED DATA ACQUISITION")
        print("="*70)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Download all parts
        self.download_all_parts()
        
        # Extract all parts
        self.extract_all_parts()
        
        # Clean up zip files
        self.cleanup_zip_files()
        
        print("\n" + "="*70)
        print("DOWNLOAD & EXTRACTION COMPLETE")
        print("="*70)
        print(f"Extracted files are in: {EXTRACTED_DIR}")
    
    def download_all_parts(self):
        """Download all 6 parts of the DailyMed release in parallel."""
        print("\n--- Starting Parallel Download ---")
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all download tasks
            futures = {executor.submit(self.download_part, part): part for part in self.parts}
            
            for future in as_completed(futures):
                part = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"❌ Error downloading {part}: {e}")
        
        print("✅ All parts downloaded")

    def download_part(self, part):
        """Download a single part with resume capability."""
        part_path = os.path.join(RAW_DIR, part)
        url = f"{self.base_url}{part}"
        
        print(f"Checking {part}...")
        
        # Check if file exists and get its size for resume
        initial_size = 0
        if os.path.exists(part_path):
            initial_size = os.path.getsize(part_path)
            print(f"  Resuming from byte {initial_size}...")
        else:
            print(f"  Starting new download...")
        
        try:
            # Add Range header for resuming
            headers = {'Range': f'bytes={initial_size}-'}
            
            with requests.get(url, stream=True, headers=headers) as response:
                response.raise_for_status()
                
                # Handle partial content (206) or full content (200)
                if response.status_code == 206:
                    mode = 'ab' # Append binary
                else:
                    mode = 'wb' # Write binary
                    initial_size = 0
                
                total_size = int(response.headers.get('content-length', 0)) + initial_size
                
                with open(part_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Verify final size
                final_size = os.path.getsize(part_path)
                print(f"  ✅ Downloaded {part} ({final_size} bytes)")
                
        except Exception as e:
            print(f"  ❌ Error downloading {part}: {e}")
            raise
    
    def extract_all_parts(self):
        """Extract all parts to the same directory, skipping existing files."""
        print("\n--- Extracting All Parts (Skipping existing files) ---")
        
        for part in self.parts:
            part_path = os.path.join(RAW_DIR, part)
            if os.path.exists(part_path):
                self.extract_part(part_path)
        
        print("✅ All parts extracted")
    
    def extract_part(self, part_path):
        """Extract a single part, skipping files that already exist."""
        part_name = os.path.basename(part_path)
        print(f"Checking {part_name}...")
        
        try:
            with zipfile.ZipFile(part_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                extracted_count = 0
                
                for file in file_list:
                    target_path = os.path.join(EXTRACTED_DIR, file)
                    # Skip if file already exists
                    if os.path.exists(target_path):
                        continue
                    # Skip directories
                    if file.endswith('/'):
                        os.makedirs(target_path, exist_ok=True)
                        continue
                    
                    # Extract file
                    with zip_ref.open(file) as source, open(target_path, 'wb') as target:
                        target.write(source.read())
                        extracted_count += 1
                
                if extracted_count > 0:
                    print(f"  ✅ Extracted {extracted_count} new files from {part_name}")
                else:
                    print(f"  ℹ️  All files from {part_name} already exist. Skipping.")
            
        except Exception as e:
            print(f"  ❌ Error extracting {part_path}: {e}")
    
    def cleanup_zip_files(self):
        """Clean up zip files to save space."""
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
        sys.exit(1)

