#!/usr/bin/env python3
"""
GRC-20 Pipeline Preflight Configuration
========================================
Interactive menu to set pipeline options before run.
"""

import json
import os
import sys
from pathlib import Path

# Add schema path for schema access if needed
sys.path.insert(0, str(Path(__file__).parent / '00_schema'))
from pharma_schema import PharmaSchema

# Paths
BASE_DIR = Path(__file__).parent.parent.parent.parent  # Navigate to project root
DATA_DIR = BASE_DIR / 'data' / 'grc20_v2'
CONFIG_FILE = DATA_DIR / 'pipeline_config.json'
RAW_DATA_DIR = BASE_DIR / 'data' / 'raw_data'
RXNORM_DIR = RAW_DATA_DIR / 'extracted_rrf'

def get_rxnorm_sources():
    """Find available RxNorm zip files."""
    sources = {}
    
    if not RAW_DATA_DIR.exists():
        print(f"Warning: Raw data directory not found: {RAW_DATA_DIR}")
        return sources
        
    # Look ONLY for zip files
    for item in RAW_DATA_DIR.iterdir():
        if item.is_file() and item.suffix == '.zip' and "RxNorm" in item.name:
            sources[item.name] = f"{item.name}"
            
    return sources

def select_rxnorm_source(sources):
    """Interactive menu for RxNorm source selection."""
    print("\n" + "="*70)
    print("RXNORM SOURCE SELECTION")
    print("="*70)
    
    if not sources:
        print("⚠️  No RxNorm zip files found in data/raw_data/")
        print("   Please download an RxNorm RRF release zip first.")
        return None
    
    source_keys = sorted(sources.keys())
    
    print("Available RxNorm releases:")
    for i, key in enumerate(source_keys, 1):
        print(f"  [{i}] {sources[key]}")
        
    print("\n(Pipeline will automatically extract if necessary)")
    print("Select source [1-{}]: ".format(len(source_keys)), end='', flush=True)
    
    try:
        choice = int(input())
        if 1 <= choice <= len(source_keys):
            selected_key = source_keys[choice - 1]
            print(f"Selected: {selected_key}")
            return selected_key
        else:
            print("Invalid choice. Using default (first available).")
            return source_keys[0]
    except (ValueError, EOFError):
        # Handle non-interactive or invalid input
        print("No valid input. Using default (first available).")
        return source_keys[0]

def select_dailymed_mode():
    """Interactive menu for DailyMed acquisition mode."""
    print("\n" + "="*70)
    print("DAILYMED DATA ACQUISITION")
    print("="*70)
    
    print("  [1] Use existing local data (Skip download)")
    print("      - Faster. Uses files in data/dailymed/extracted/")
    
    print("  [2] Download and extract latest release")
    print("      - Slower. Fetches latest archive from dailymed-data.nlm.nih.gov")
    
    print("\nSelect mode [1-2] (default: 1): ", end='', flush=True)
    
    try:
        choice = input().strip()
        if choice == '2':
            print("Selected: Download latest release")
            return 'download'
        else:
            print("Selected: Use existing local data")
            return 'existing'
    except (EOFError, KeyboardInterrupt):
        print("No input. Defaulting to existing local data.")
        return 'existing'

def select_run_mode():
    """Interactive menu for Run Mode (Full vs Limited)."""
    print("\n" + "="*70)
    print("RUN MODE")
    print("="*70)
    
    print("  [1] Full Run")
    print("      - Processes all available documents.")
    print("      - Recommended for production builds.")
    
    print("  [2] Limited Run (Test)")
    print("      - Processes a subset of documents.")
    print("      - Useful for testing and development.")
    
    print("\nSelect mode [1-2] (default: 1): ", end='', flush=True)
    
    mode_choice = None
    limit = None
    
    try:
        choice = input().strip()
        if choice == '2':
            print("\nSelected: Limited Run (Test)")
            print("Enter the number of documents to process (e.g., 100): ", end='', flush=True)
            try:
                limit = int(input())
                if limit > 0:
                    print(f"Processing limit set to: {limit}")
                    mode_choice = 'limited'
                else:
                    print("Invalid limit. Defaulting to full run.")
                    mode_choice = 'full'
            except ValueError:
                print("Invalid input. Defaulting to full run.")
                mode_choice = 'full'
        else:
            print("Selected: Full Run")
            mode_choice = 'full'
            
    except (EOFError, KeyboardInterrupt):
        print("No input. Defaulting to full run.")
        mode_choice = 'full'
        
    return mode_choice, limit

def save_config(config):
    """Save configuration to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"\n✅ Configuration saved to {CONFIG_FILE}")

def main():
    print("="*70)
    print("GRC-20 PIPELINE CONFIGURATION")
    print("="*70)
    
    # Check if we are running in force mode (e.g., to reset config)
    # We can check for a CLI arg or environment variable, but for now
    # let's just check if the script was called with an argument.
    force_reconfig = len(sys.argv) > 1 and sys.argv[1] == '--force'

    # Load existing config if it exists
    existing_config = {}
    config_exists = CONFIG_FILE.exists()
    
    if config_exists:
        try:
            with open(CONFIG_FILE, 'r') as f:
                existing_config = json.load(f)
            if not force_reconfig:
                print(f"[INFO] Using existing configuration: {CONFIG_FILE}")
                print("[INFO] To reconfigure, run this script with --force or delete the config file.")
                # Print current config for user info
                print(f"  RxNorm Source: {existing_config.get('rxnorm_source')}")
                print(f"  DailyMed Mode: {existing_config.get('dailymed_mode')}")
                print(f"  Run Mode: {existing_config.get('run_mode')}")
                if existing_config.get('run_mode') == 'limited':
                    print(f"  Document Limit: {existing_config.get('document_limit')}")
                return # Exit early
        except:
            pass
    
    if config_exists and force_reconfig:
        print("[INFO] Force reconfiguration requested.")
    
    config = {}
    
    # 1. RxNorm Source Selection
    rxnorm_sources = get_rxnorm_sources()
    rxnorm_choice = select_rxnorm_source(rxnorm_sources)
    
    if rxnorm_choice:
        config['rxnorm_source'] = rxnorm_choice
    else:
        print("⚠️  Could not determine RxNorm source. Pipeline may fail.")
        config['rxnorm_source'] = None
    
    # 2. DailyMed Acquisition Mode
    dailymed_choice = select_dailymed_mode()
    config['dailymed_mode'] = dailymed_choice
    
    # 3. Run Mode and Document Limit
    run_mode, doc_limit = select_run_mode()
    config['run_mode'] = run_mode
    config['document_limit'] = doc_limit
    
    # Save
    save_config(config)
    
    print("\n" + "="*70)
    print("CONFIGURATION COMPLETE")
    print("="*70)
    print("You can now run the main pipeline.")
    print("This configuration will be used until you change it.")
    if run_mode == 'limited':
        print(f"LIMITED RUN ACTIVE: Will process {doc_limit} documents.")

if __name__ == "__main__":
    main()
